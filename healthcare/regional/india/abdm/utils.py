import json
import uuid
from datetime import datetime

import requests

import frappe
from frappe.utils import add_to_date, format_date, getdate

from healthcare.regional.india.abdm.abdm_config import get_url


@frappe.whitelist()
def get_authorization_token():
	client_id, client_secret, auth_base_url = frappe.db.get_value(
		"ABDM Settings",
		{"company": frappe.defaults.get_user_default("Company"), "default": 1},
		["client_id", "client_secret", "auth_base_url"],
	)

	config = get_url("authorization")
	auth_base_url = auth_base_url.rstrip("/")
	url = auth_base_url + config.get("url")
	payload = {"clientId": client_id, "clientSecret": client_secret}
	if not auth_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Base URL not configured in ABDM Settings!",
		)

	req = frappe.new_doc("ABDM Request")
	req.request = json.dumps(payload, indent=4)
	req.url = url
	req.request_name = "Authorization Token"
	try:
		response = requests.request(
			method=config.get("method"),
			url=url,
			headers={"Content-Type": "application/json; charset=UTF-8"},
			data=json.dumps(payload),
		)
		response.raise_for_status()
		response = response.json()
		req.response = json.dumps(response, indent=4)
		req.status = "Granted"
		req.insert(ignore_permissions=True)
		return response.get("accessToken"), response.get("tokenType")

	except Exception as e:
		try:
			req.response = json.dumps(response.json(), indent=4)
		except json.decoder.JSONDecodeError:
			req.response = response.text
		req.traceback = e
		req.status = "Revoked"
		req.insert(ignore_permissions=True)
		traceback = f"Remote URL {url}\nPayload: {payload}\nTraceback: {e}"
		frappe.log_error(message=traceback, title="Cant create session")
		return auth_base_url, None


@frappe.whitelist()
def abdm_request(
	payload=None,
	url_key=None,
	req_type=None,
	rec_headers=None,
	to_be_enc=None,
	patient_name=None,
	access_token=None,
	token_type=None,
):
	if payload and isinstance(payload, str):
		payload = json.loads(payload)

	if req_type == "Health ID":
		url_type = "health_id_base_url"

	base_url = frappe.db.get_value(
		"ABDM Settings",
		{"company": frappe.defaults.get_user_default("Company"), "default": 1},
		[url_type],
	)
	if not base_url:
		frappe.throw(title="Not Configured", msg="Base URL not configured in ABDM Settings!")

	config = get_url(url_key)
	base_url = base_url.rstrip("/")
	url = base_url + config.get("url")
	# Check the abdm_config, if the data need to be encypted, encrypts message
	# Build payload with encrypted message
	if config.get("encrypted"):
		message = payload.get("to_encrypt")
		encrypted = get_encrypted_message(message)
		if "encrypted_msg" in encrypted and encrypted["encrypted_msg"]:
			payload[to_be_enc] = payload.pop("to_encrypt")
			payload[to_be_enc] = encrypted["encrypted_msg"]

	if not access_token:
		access_token, token_type = get_authorization_token()

	if not access_token:
		frappe.throw(
			title="Authorization Failed",
			msg="Access token generation for authorization failed, Please try again.",
		)

	authorization = ("Bearer " if token_type == "bearer" else "") + access_token
	headers = {
		"Content-Type": "application/json",
		"Accept": "application/json",
		"Authorization": authorization,
	}
	if rec_headers:
		if isinstance(rec_headers, str):
			rec_headers = json.loads(rec_headers)
		headers.update(rec_headers)
	req = frappe.new_doc("ABDM Request")
	req.status = "Requested"
	# TODO: skip saving or encrypt the data saved
	req.request = json.dumps(payload, indent=4)
	req.url = url
	req.request_name = url_key
	try:
		response = requests.request(
			method=config.get("method"), url=url, headers=headers, data=json.dumps(payload)
		)
		response.raise_for_status()
		if url_key == "get_card":
			pdf = response.content
			_file = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": "abha_card{}.png".format(patient_name),
					"attached_to_doctype": "Patient",
					"attached_to_name": patient_name,
					"attached_to_field": "abha_card",
					"is_private": 0,
					"content": pdf,
				}
			)
			_file.save()
			frappe.db.commit()
			return _file
		if response.json() and isinstance(response.json(), dict):
			req.response = json.dumps(response.json(), indent=4)
		else:
			req.response = response.text
		req.status = "Granted"
		req.insert(ignore_permissions=True)
		return response.json()

	except Exception as e:
		req.traceback = e
		if response.json() and isinstance(response.json(), dict):
			req.response = json.dumps(response.json(), indent=4)
		else:
			req.response = response.text
		req.status = "Revoked"
		req.insert(ignore_permissions=True)
		traceback = f"Remote URL {url}\nPayload: {payload}\nTraceback: {e}"
		frappe.log_error(message=traceback, title="Cant complete API call")
		return response.json()


def get_encrypted_message(message):
	base_url = frappe.db.get_value(
		"ABDM Settings",
		{"company": frappe.defaults.get_user_default("Company"), "default": 1},
		["health_id_base_url"],
	)

	config = get_url("auth_cert")
	url = base_url + config.get("url")
	req = frappe.new_doc("ABDM Request")
	req.status = "Requested"
	req.url = url
	req.request_name = "auth_cert"
	try:
		response = requests.request(
			method=config.get("method"), url=url, headers={"Content-Type": "application/json"}
		)

		response.raise_for_status()
		pub_key = response.text
		pub_key = (
			pub_key.replace("\n", "")
			.replace("-----BEGIN PUBLIC KEY-----", "")
			.replace("-----END PUBLIC KEY-----", "")
		)
		if pub_key:
			encrypted_msg = get_rsa_encrypted_message(message, pub_key)
			req.response = encrypted_msg
			req.status = "Granted"
		req.insert(ignore_permissions=True)
		encrypted = {"public_key": pub_key, "encrypted_msg": encrypted_msg}
		return encrypted

	except Exception as e:
		req.traceback = e
		req.response = json.dumps(response.json(), indent=4)
		req.status = "Revoked"
		req.insert(ignore_permissions=True)
		traceback = f"Remote URL {url}\nTraceback: {e}"
		frappe.log_error(message=traceback, title="Cant complete API call")
		return None


def get_rsa_encrypted_message(message, pub_key):
	# TODO:- Use cryptography
	from base64 import b64decode, b64encode

	from Crypto.Cipher import PKCS1_v1_5
	from Crypto.PublicKey import RSA

	message = bytes(message, "utf-8")
	pubkey = b64decode(pub_key)
	rsa_key = RSA.importKey(pubkey)
	cipher = PKCS1_v1_5.new(rsa_key)
	ciphertext = cipher.encrypt(message)
	emsg = b64encode(ciphertext)
	encrypted_msg = emsg.decode("UTF-8")
	return encrypted_msg


@frappe.whitelist()
def get_health_data(otp, txnId, auth_method, patient=None):
	confirm_w_otp_payload = {"to_encrypt": otp, "txnId": txnId}
	if auth_method == "AADHAAR_OTP":
		url_key = "confirm_w_aadhaar_otp"
	elif auth_method == "MOBILE_OTP":
		url_key = "confirm_w_mobile_otp"
	# returns X-Token
	response = abdm_request(confirm_w_otp_payload, url_key, "Health ID", "", "otp")
	abha_url = ""
	if response and response.get("token"):
		abha_url = get_abha_card(response["token"], patient)
		header = {"X-Token": "Bearer " + response["token"]}
		response = abdm_request("", "get_acc_info", "Health ID", header, "")
	return response, abha_url


# patient after_insert
def set_consent_attachment_details(doc, method=None):
	if frappe.db.exists(
		"ABDM Settings",
		{"company": frappe.defaults.get_user_default("Company"), "default": 1},
	):
		if doc.consent_for_aadhaar_use:
			file_name = frappe.db.get_value("File", {"file_url": doc.consent_for_aadhaar_use}, "name")
			if file_name:
				frappe.db.set_value(
					"File",
					file_name,
					{
						"attached_to_doctype": "Patient",
						"attached_to_name": doc.name,
						"attached_to_field": doc.consent_for_aadhaar_use,
					},
				)
		if doc.abha_card:
			abha_file_name = frappe.db.get_value(
				"File", {"file_url": doc.abha_card, "attached_to_name": None}, "name"
			)
			if abha_file_name:
				frappe.db.set_value(
					"File",
					abha_file_name,
					{
						"attached_to_doctype": "Patient",
						"attached_to_name": doc.name,
						"attached_to_field": doc.abha_card,
					},
				)


def get_abha_card(token, patient=None):
	header = {"X-Token": "Bearer " + token}
	response = abdm_request("", "get_card", "Health ID", header, "", patient_name=patient)
	return response.get("file_url")


# Milestone - 2
@frappe.whitelist()
def get_token_for_hiecm():
	settings = get_abdm_settings()

	if not settings.consent_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Consent Management Base URL not configured in ABDM Settings!",
		)

	config = get_url("hiecm_session")
	url = settings.consent_base_url + config.get("url")
	payload = {
		"clientId": settings.client_id,
		"clientSecret": settings.client_secret,
		"grantType": "client_credentials",
	}
	headers = {
		"Content-Type": "application/json; charset=UTF-8",
		"REQUEST-ID": generate_unique_id(),
		"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"X-CM-ID": settings.x_cm_id,
	}

	return request_and_post(url, payload, headers, config.get("method"), "Facility Access Token")


def generate_unique_id():
	return str(uuid.uuid4())


@frappe.whitelist()
def update_bridge_url():
	settings = get_abdm_settings()

	if not settings.consent_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Consent Management Base URL not configured in ABDM Settings!",
		)

	bridge_url = settings.bridge_url
	token = get_token_for_hiecm()
	config = get_url("update_bridge")

	authorization = ("Bearer " if token.get("tokenType") == "bearer" else "") + token.get(
		"accessToken"
	)
	url = settings.consent_base_url + config.get("url")
	payload = {"url": bridge_url}
	headers = {
		"Content-Type": "application/json",
		"REQUEST-ID": generate_unique_id(),
		"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"X-CM-ID": settings.x_cm_id,
		"Authorization": authorization,
	}

	try:
		response = request_and_post(url, payload, headers, config.get("method"), "Update Bridge URL")
		message = "Bridge URL updated"
		indicator = "Green"
		if response and response[0].get("error"):
			error = response[0].get("error")
			message = error.get("message")
			indicator = "Red"
		frappe.msgprint(message, alert=True, indicator=indicator)
	except Exception as e:
		frappe.log_error(message=e, title="Failed to Update Bridge URL")


@frappe.whitelist()
def register_bridge_service():
	settings = get_abdm_settings()

	if not settings.facility_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Facility Base URL not configured in ABDM Settings!",
		)

	token = get_token_for_hiecm()
	config = get_url("register_bridge")

	authorization = ("Bearer " if token.get("tokenType") == "bearer" else "") + token.get(
		"accessToken"
	)
	url = settings.facility_base_url + config.get("url")
	payload = {
		"facilityId": settings.facility_id,
		"facilityName": settings.facility_name,
		"HRP": [
			{
				"bridgeId": settings.client_id,
				"hipName": settings.facility_name,
				"type": "HIP",
				"active": True,
			}
		],
	}
	headers = {
		"Content-Type": "application/json",
		"Authorization": authorization,
	}

	try:
		response = request_and_post(
			url, payload, headers, config.get("method"), "Register Bridge Service"
		)
		message = "Bridge Service Registered"
		indicator = "Green"
		if response and response[0].get("error"):
			error = response[0].get("error")
			message = error.get("message")
			indicator = "Red"
		frappe.msgprint(message, alert=True, indicator=indicator)
	except Exception as e:
		frappe.log_error(message=e, title="Failed to Register Bridge Service")


@frappe.whitelist()
def get_bridge_by_service_id():
	settings = get_abdm_settings()

	if not settings.consent_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Consent Management Base URL not configured in ABDM Settings!",
		)

	token = get_token_for_hiecm()
	config = get_url("find_bridge_by_service_id")

	authorization = ("Bearer " if token.get("tokenType") == "bearer" else "") + token.get(
		"accessToken"
	)
	url = settings.consent_base_url + config.get("url") + f"/{settings.facility_id}"
	headers = {
		"Content-Type": "application/json",
		"Authorization": authorization,
		"REQUEST-ID": generate_unique_id(),
		"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"X-CM-ID": settings.x_cm_id,
	}

	try:
		response = request_and_post(
			url, None, headers, config.get("method"), "Find Bridge Service by Service ID"
		)
		return response
	except Exception as e:
		frappe.log_error(message=e, title="Failed to Get Bridge Details")


@frappe.whitelist()
def get_services_by_bridge_id():
	settings = get_abdm_settings()

	if not settings.consent_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Consent Management Base URL not configured in ABDM Settings!",
		)

	token = get_token_for_hiecm()
	config = get_url("find_services_by_bridge_id")

	authorization = ("Bearer " if token.get("tokenType") == "bearer" else "") + token.get(
		"accessToken"
	)
	url = settings.consent_base_url + config.get("url")
	headers = {
		"Content-Type": "application/json",
		"Authorization": authorization,
		"REQUEST-ID": generate_unique_id(),
		"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"X-CM-ID": settings.x_cm_id,
	}

	try:
		response = request_and_post(
			url, None, headers, config.get("method"), "Find Services by Bridge ID"
		)
		return response
	except Exception as e:
		frappe.log_error(message=e, title="Failed to Get Service by Bridge ID")


# HIP Initiated Linking
@frappe.whitelist()
def generate_hip_token(**args):
	settings = get_abdm_settings()

	if not settings.consent_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Consent Management Base URL not configured in ABDM Settings!",
		)

	args = frappe._dict(args)
	token = get_token_for_hiecm()
	config = get_url("hip_generate_token")

	authorization = ("Bearer " if token.get("tokenType") == "bearer" else "") + token.get(
		"accessToken"
	)
	url = settings.consent_base_url + config.get("url")
	payload = {
		"abhaNumber": args.abha_number.replace("-", ""),
		"abhaAddress": args.abha_address,
		"name": args.name,
		"gender": args.gender[0],
		"yearOfBirth": args.year_of_birth,
	}
	headers = {
		"Content-Type": "application/json",
		"REQUEST-ID": generate_unique_id(),
		"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"X-HIP-ID": settings.facility_id,
		"X-CM-ID": settings.x_cm_id,
		"Authorization": authorization,
	}

	try:
		response = request_and_post(
			url, payload, headers, config.get("method"), "Generate HIP Link Token"
		)
		return response
	except Exception as e:
		frappe.log_error(message=e, title="Failed to Generate HIP Token")


@frappe.whitelist()
def link_carecontext(doctype=None, docname=None):
	if not doctype:
		return

	doc = frappe.get_cached_doc(doctype, docname)
	if doc.patient:
		abha_number, abha_address = frappe.db.get_value(
			"Patient", doc.patient, ["abha_number", "abha_address"]
		)
		if not abha_number or not abha_address:
			frappe.throw(
				title="Missing ABHA Details",
				msg="Please provide both ABHA Number and ABHA Address to link the care context.4",
			)

		x_link_token = get_x_link_token(doc.patient)

		if not x_link_token:
			frappe.msgprint(
				"Please generate HIP link token because the patient HIP link token has expired or not generated",
				alert=True,
			)
			return frappe.get_cached_doc("Patient", doc.patient)

		settings = get_abdm_settings()

		if not settings.consent_base_url:
			frappe.throw(
				title="Not Configured",
				msg="Consent Management Base URL not configured in ABDM Settings!",
			)

		token = get_token_for_hiecm()
		config = get_url("link_carecontext")

		authorization = ("Bearer " if token.get("tokenType") == "bearer" else "") + token.get(
			"accessToken"
		)
		url = settings.consent_base_url + config.get("url")

		carecontext, display, hitype = get_carecontext(doc)
		payload = {
			"abhaNumber": abha_number.replace("-", ""),
			"abhaAddress": abha_address,
			"patient": [
				{
					"referenceNumber": doc.name,
					"display": display,
					"careContexts": carecontext,
					"hiType": hitype,
					"count": len(carecontext),
				}
			],
		}
		headers = {
			"Content-Type": "application/json",
			"REQUEST-ID": generate_unique_id(),
			"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
			"X-HIP-ID": settings.facility_id,
			"X-CM-ID": settings.x_cm_id,
			"Authorization": authorization,
			"X-LINK-TOKEN": x_link_token,
		}

		try:
			response = request_and_post(url, payload, headers, config.get("method"), "Link Carecontext")
			message = "Linking Carecontext Requested"
			indicator = "Green"
			if response and response[0].get("error"):
				error = response[0].get("error")
				message = error.get("message")
				indicator = "Red"
			frappe.msgprint(message, alert=True, indicator=indicator)
		except Exception as e:
			frappe.log_error(message=e, title="Failed to Link Carecontext")
	else:
		frappe.throw("Patient is mandatory to link the carecontext")


def request_and_post(url=None, payload=None, headers=None, method="POST", request_name=None):
	req = frappe.new_doc("ABDM Request")
	req.request = json.dumps(payload, indent=4)
	req.url = url
	req.request_name = request_name
	req.header = json.dumps(headers, indent=4)

	try:
		response = requests.request(
			method=method,
			url=url,
			headers=headers,
			data=json.dumps(payload) or None,
		)
		response.raise_for_status()
		try:
			response = response.json()
		except Exception as e:
			response = response.text

		req.response = json.dumps(response, indent=4) if response else ""
		req.status = "Granted"
		req.insert(ignore_permissions=True)
		return response

	except Exception as e:
		try:
			req.response = json.dumps(response.json(), indent=4)
		except json.decoder.JSONDecodeError:
			req.response = response.text
		req.traceback = e
		req.status = "Revoked"
		req.insert(ignore_permissions=True)
		traceback = f"Remote URL {url}\nPayload: {payload}\nTraceback: {e}"
		frappe.log_error(message=traceback, title="Failed to Initiate Request")
		return response.json() if response.json() else response.text


def get_abdm_settings():
	settings = frappe.db.exists(
		"ABDM Settings", {"company": frappe.defaults.get_user_default("Company"), "default": 1}
	)

	if not settings:
		return

	return frappe.get_cached_doc("ABDM Settings", settings)


def get_carecontext(doc):
	"""HItypes: Prescription,DiagnosticReport,OPConsultation,DischargeSummary,ImmunizationRecord,HealthDocumentRecord,WellnessRecord,Invoice"""
	carecontext = []
	display = None
	hitype = None
	if doc.doctype == "Patient Encounter":
		display = f"OPD Record-{format_date(doc.encounter_date, 'dd-mm-yyyy')}-{doc.name}"
		hitype = "OPConsultation"
		carecontext.append(
			{"referenceNumber": doc.name, "display": f"{doc.appointment_type} with {doc.practitioner_name}"}
		)
	if doc.doctype == "Medication Request":
		display = f"Medication Request-{format_date(doc.order_date, 'dd-mm-yyyy')}-{doc.name}"
		hitype = "Prescription"
		carecontext.append(
			{"referenceNumber": doc.name, "display": f"{doc.medication} ordered by {doc.practitioner_name}"}
		)
		# if doc.drug_prescription:
		# 	for i in doc.drug_prescription:
		# 		carecontext.append(
		# 			{"referenceNumber": i.name, "display": f"Medication Prescription: {i.medication}"}
		# 		)
		# if doc.lab_test_prescription:
		# 	for i in doc.lab_test_prescription:
		# 		carecontext.append(
		# 			{"referenceNumber": i.name, "display": f"Lab Test Prescription: {i.observation_template}"}
		# 		)
		# if doc.procedure_prescription:
		# 	for i in doc.procedure_prescription:
		# 		carecontext.append(
		# 			{"referenceNumber": i.name, "display": f"Proceedure Prescription: {i.procedure}"}
		# 		)
		# if doc.therapies:
		# 	for i in doc.therapies:
		# 		carecontext.append(
		# 			{"referenceNumber": i.name, "display": f"Therapy Prescription: {i.therapy_type}"}
		# 		)

	return carecontext, display, hitype


def get_x_link_token(patient=None):
	if not patient:
		return

	min_token_date = add_to_date(getdate(), months=-6)
	token = frappe.db.get_all(
		"ABDM Request",
		filters={
			"patient": patient,
			"token": ["is", "set"],
			"url": "/api/v3/hip/token/on-generate-token",
			"status": "Granted",
			"request_date": [">=", min_token_date],
		},
		pluck="token",
		order_by="request_date desc",
	)

	if token and len(token):
		return token[0]

	return


def post_abdm_request(**args):
	args = frappe._dict(args)
	if args:
		req = frappe.new_doc("ABDM Request")
		req.url = args.path
		req.request_name = args.request_name
		req.header = args.headers
		req.status = "Granted"
		if args.get("abha_address"):
			patient = frappe.db.exists("Patient", {"abha_address": args.get("abha_address")})
			if patient:
				req.patient = patient
		if args.get("notification") and args.get("notification").get("status") != "GRANTED":
			req.status = "Revoked"
		if args.get("error"):
			message = frappe._dict(args.get("error")).get("message")
			req.status = "Revoked"
			req.traceback = message
		if args.get("token"):
			req.token = args.get("token")
		req.response = json.dumps(args.data, indent=4)
		req.insert(ignore_permissions=True)
