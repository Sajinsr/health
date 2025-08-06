import json
import uuid
from datetime import datetime

import requests

import frappe
from frappe.utils import add_to_date, format_date, getdate, now

from healthcare.regional.india.abdm.abdm_config import get_url


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
	base_url = base_url
	url = base_url + config.get("url")
	# Check the abdm_config, if the data need to be encypted, encrypts message
	# Build payload with encrypted message
	if config.get("encrypted"):
		if url_key in ["verify_abha_number_otp", "verify_abha_address_otp", "create_abha_w_aadhaar"]:
			message = payload["authData"]["otp"][to_be_enc]
		else:
			message = payload.get(to_be_enc)
		encrypted = get_encrypted_message(message)
		if encrypted and encrypted.get("encrypted_msg"):
			if url_key in ["verify_abha_number_otp", "verify_abha_address_otp", "create_abha_w_aadhaar"]:
				payload["authData"]["otp"][to_be_enc] = encrypted["encrypted_msg"]
			else:
				payload[to_be_enc] = encrypted["encrypted_msg"]
	token = {}
	if not access_token:
		token = get_authorization_token()
		access_token, token_type = token.get("accessToken"), token.get("tokenType")

	if not access_token:
		msg = "Access token generation failed, Please try again."
		if token.get("traceback"):
			msg += f"<br><br>Traceback: {token.get('traceback')}"
		frappe.throw(
			title="Authorization Failed",
			msg=msg,
		)
	authorization = None
	authorization = ("Bearer " if token_type == "bearer" else "") + access_token
	headers = {
		"Content-Type": "application/json",
		"Accept": "application/json",
		"REQUEST-ID": generate_unique_id(),
		"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"Authorization": authorization,
	}

	if url_key in ["get_card", "get_account_card"]:
		headers["Accept"] = "*/*"
	if rec_headers:
		if isinstance(rec_headers, str):
			rec_headers = json.loads(rec_headers)
		headers.update(rec_headers)

	try:
		return request_and_post(url, payload, headers, config.get("method"), url_key, patient_name)

	except Exception as e:
		traceback = f"Remote URL {url}\nPayload: {payload}\nTraceback: {e}"
		frappe.log_error(message=traceback, title="Cant complete API call")
		return traceback


def get_encrypted_message(message):
	settings = get_abdm_settings()

	config = get_url("auth_cert")
	url = settings.health_id_base_url + config.get("url")

	token = get_authorization_token()

	authorization = ("Bearer " if token.get("tokenType") == "bearer" else "") + token.get(
		"accessToken"
	)
	headers = {
		"REQUEST-ID": generate_unique_id(),
		"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"Authorization": authorization,
	}
	try:
		response = request_and_post(url, None, headers, config.get("method"), "Auth Cert API")

		pub_key = response.get("publicKey") if isinstance(response, dict) else None
		if pub_key:
			encrypted_msg = get_rsa_encrypted_message(message, pub_key)

		encrypted = {"public_key": pub_key, "encrypted_msg": encrypted_msg}
		return encrypted

	except Exception as e:
		traceback = f"Remote URL {url}\nTraceback: {e}"
		frappe.log_error(message=traceback, title="Cant complete API call")
		return


def get_rsa_encrypted_message(message, pub_key):
	from base64 import b64decode, b64encode

	from cryptography.hazmat.backends import default_backend
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import padding

	pub_key_der = b64decode(pub_key)

	# Load public key
	public_key = serialization.load_der_public_key(pub_key_der, backend=default_backend())

	# Encrypt using OAEP with SHA-1
	encrypted = public_key.encrypt(
		message.encode("utf-8"),
		padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA1()), algorithm=hashes.SHA1(), label=None),
	)

	# Return base64 encoded encrypted message
	return b64encode(encrypted).decode("utf-8")


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
	response = abdm_request("", "get_account_card", "Health ID", header, "", patient_name=patient)
	return response


# Milestone - 2
@frappe.whitelist()
def get_authorization_token():
	settings = get_abdm_settings()

	if not settings.consent_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Consent Management Base URL not configured in ABDM Settings!",
		)

	config = get_url("authorization")
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

	return request_and_post(url, payload, headers, config.get("method"), "Authorization Access Token")


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
	token = get_authorization_token()
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
		indicator = "green"
		if response and response[0].get("error"):
			error = response[0].get("error")
			message = error.get("message")
			indicator = "red"
		frappe.msgprint(message, alert=True, indicator=indicator)
	except Exception as e:
		frappe.log_error(message=e, title="Failed to Update Bridge URL")


@frappe.whitelist()
def register_bridge_service(company=None):
	settings = get_abdm_settings(company)

	if not settings.facility_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Facility Base URL not configured in ABDM Settings!",
		)

	token = get_authorization_token()
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
		indicator = "green"
		if response and response[0].get("error"):
			error = response[0].get("error")
			message = error.get("message")
			indicator = "red"
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

	token = get_authorization_token()
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

	token = get_authorization_token()
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
	token = get_authorization_token()
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
		message = "Generate HIP Link Token Requested"
		indicator = "green"
		if response and response.get("error"):
			error = response.get("error")
			message = error.get("message")
			indicator = "red"
		frappe.msgprint(message, alert=True, indicator=indicator)
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
		company = doc.get("company") or None
		settings = get_abdm_settings(company)

		if not settings.consent_base_url:
			frappe.throw(
				title="Not Configured",
				msg="Consent Management Base URL not configured in ABDM Settings!",
			)

		token = get_authorization_token()
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
					"referenceNumber": doc.patient if doc.patient else doc.name,
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
			indicator = "green"

			if response and response.get("error"):
				error = response.get("error")
				message = error.get("message")
				indicator = "red"
			frappe.msgprint(message, alert=True, indicator=indicator)
		except Exception as e:
			frappe.log_error(message=str(e), title="Failed to Link Carecontext")
	else:
		frappe.throw("Patient is mandatory to link the carecontext")


# User Initiated Linking
@frappe.whitelist()
def on_discover(abha_address=None, transaction_id=None, request_id=None):
	settings = get_abdm_settings()

	if not settings.consent_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Consent Management Base URL not configured in ABDM Settings!",
		)

	token = get_authorization_token()
	config = get_url("on_discover")

	authorization = ("Bearer " if token.get("tokenType") == "bearer" else "") + token.get(
		"accessToken"
	)
	url = settings.consent_base_url + config.get("url")
	payload = {
		"transactionId": transaction_id,
		"patient": get_patient_details(abha_address),
		"matchedBy": ["MR"],
		"response": {"requestId": request_id},
	}
	headers = {
		"Content-Type": "application/json",
		"REQUEST-ID": generate_unique_id(),
		"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"X-CM-ID": settings.x_cm_id,
		"Authorization": authorization,
	}

	try:
		request_and_post(url, payload, headers, config.get("method"), "Process On-discover Request")
	except Exception as e:
		frappe.log_error(message=e, title="Failed to Process On-discover Request")


@frappe.whitelist()
def on_init(abha_address=None, transaction_id=None, request_id=None, data=None):
	settings = get_abdm_settings()

	if not settings.consent_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Consent Management Base URL not configured in ABDM Settings!",
		)

	token = get_authorization_token()
	config = get_url("on_init")

	authorization = ("Bearer " if token.get("tokenType") == "bearer" else "") + token.get(
		"accessToken"
	)
	url = settings.consent_base_url + config.get("url")
	otp_expiry = add_to_date(now(), minutes=15)
	payload = {
		"transactionId": transaction_id,
		"link": {
			"referenceNumber": generate_unique_id(),
			"authenticationType": "DIRECT",
			"meta": {
				"communicationMedium": "MOBILE",
				"communicationHint": "OTP",
				"communicationExpiry": otp_expiry.replace(" ", "T") + "Z",
			},
		},
		"response": {"requestId": request_id},
	}
	patient = frappe.db.exists("Patient", {"abha_address": abha_address})
	mobile_no = ""  # get_patient_mobile_number(patient, transaction_id)
	headers = {
		"Content-Type": "application/json",
		"REQUEST-ID": generate_unique_id(),
		"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"X-CM-ID": settings.x_cm_id,
		"Authorization": authorization,
	}

	try:
		response = request_and_post(
			url, payload, headers, config.get("method"), "Process On-discover Request"
		)
		# send_sms(patient, mobile_no)
		return response
	except Exception as e:
		frappe.log_error(message=e, title="Failed to Process On-discover Request")


def get_patient_details(abha_address=None):
	if not abha_address:
		return

	patient = frappe.db.exists("Patient", {"abha_address": abha_address})

	if not patient:
		return

	details = []
	"""HItypes: Prescription,DiagnosticReport,OPConsultation,DischargeSummary,ImmunizationRecord,HealthDocumentRecord,WellnessRecord,Invoice"""

	doctype_map = {
		"Patient Encounter": "OPConsultation",
		"Medication Request": "Prescription",
		"Therapy Session": "WellnessRecord",
		"Diagnostic Report": "DiagnosticReport",
		"Discharge Summary": "DischargeSummary",
		"Patient Medical Record": "HealthDocumentRecord",
		"Sales Invoice": "Invoice",
	}

	for i in doctype_map:
		records = frappe.db.get_all(
			i, filters={"patient": patient, "docstatus": ["!=", 2]}, fields=["*"]
		)
		# records = frappe.db.get_all("FHIR Resource", filters={"patient": patient, "doctype": i}, fields=["*"])

		carecontexts = []
		for rec in records:
			carecontexts.append(
				{
					"referenceNumber": rec.name,
					"display": f"{rec.name}/{i}/{rec.patient_name}",
				}
			)

		if len(carecontexts):
			details.append(
				{
					"referenceNumber": patient,
					"display": f"Record of {doctype_map[i]}",
					"careContexts": carecontexts,
					"hiType": doctype_map[i],
					"count": len(carecontexts),
				}
			)

	return details


def request_and_post(
	url=None, payload=None, headers=None, method="POST", request_name=None, patient=None
):
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
			if request_name in ["get_card", "get_account_card"]:
				from frappe.utils.file_manager import save_file

				file = save_file(
					f"abha_card-{patient}.png",
					response.content,
					"Patient",
					patient,
					df="abha_card",
					decode=False,
					is_private=0,
				)
				frappe.db.commit()
				response = file.file_url
			else:
				response = response.json()
		except Exception as e:
			response = response.text

		if isinstance(response, dict):
			req.response = json.dumps(response, indent=4)
		else:
			req.response = response
		req.status = "Granted"
		req.insert(ignore_permissions=True)
		return response

	except Exception as e:
		traceback = f"Remote URL {url}\nPayload: {payload}\nTraceback: {e}"
		frappe.log_error(message=traceback, title="Failed to Initiate Request")
		req.response = traceback
		req.traceback = e
		req.status = "Revoked"
		req.insert(ignore_permissions=True)
		return {"traceback": e}


def get_abdm_settings(company=None):
	settings = frappe.db.exists(
		"ABDM Settings",
		{"company": company or frappe.defaults.get_user_default("Company"), "default": 1},
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
			"request_name": "Callback of HIP Link Token",
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
		if args.get("transaction_id"):
			req.transaction_id = args.get("transaction_id")
		if args.get("request_id"):
			req.request_id = args.get("request_id")
		req.response = json.dumps(args.data, indent=4)
		req.insert(ignore_permissions=True)


def send_sms(patient, mobile_no):
	if not patient:
		return

	settings = get_abdm_settings()

	if not settings.consent_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Consent Management Base URL not configured in ABDM Settings!",
		)

	token = get_authorization_token()
	config = get_url("sms_notify")

	authorization = ("Bearer " if token.get("tokenType") == "bearer" else "") + token.get(
		"accessToken"
	)
	url = settings.consent_base_url + config.get("url")
	payload = {
		"requestId": generate_unique_id(),
		"timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"notification": {"phoneNo": mobile_no, "hip": {"name": "ess-hip", "id": "ess-hip"}},
	}

	headers = {
		"Content-Type": "application/json",
		"REQUEST-ID": generate_unique_id(),
		"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"X-CM-ID": settings.x_cm_id,
		"Authorization": authorization,
	}

	try:
		response = request_and_post(
			url, payload, headers, config.get("method"), "Process On-Notify Request"
		)
		return response
	except Exception as e:
		frappe.log_error(message=e, title="Failed to Process On-Notify Request")
