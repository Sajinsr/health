import json
import uuid
from datetime import datetime

import requests

import frappe
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.utils import add_to_date, format_date, format_datetime, getdate, now

from healthcare.regional.india.abdm.abdm_config import get_url

NOW_TIME = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


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
	txn_id=None,
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
		if url_key in [
			"verify_abha_number_otp",
			"verify_abha_address_otp",
			"create_abha_w_aadhaar",
		]:
			message = payload["authData"]["otp"][to_be_enc]
		else:
			message = payload.get(to_be_enc)
		encrypted = get_encrypted_message(message)
		if encrypted and encrypted.get("encrypted_msg"):
			if url_key in [
				"verify_abha_number_otp",
				"verify_abha_address_otp",
				"create_abha_w_aadhaar",
			]:
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

	authorization = ("Bearer " if token_type == "bearer" else "") + access_token
	headers = {
		"Content-Type": "application/json",
		"REQUEST-ID": generate_unique_id(),
		"TIMESTAMP": NOW_TIME,
		"Authorization": authorization,
	}

	if url_key in ["get_card", "get_account_card"]:
		headers["Accept"] = "*/*"
	elif url_key == "get_suggestions" and txn_id:
		headers["Transaction_Id"] = txn_id
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
		"TIMESTAMP": NOW_TIME,
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

	return b64encode(encrypted).decode("utf-8")


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
		"TIMESTAMP": NOW_TIME,
		"X-CM-ID": settings.x_cm_id,
	}

	return request_and_post(url, payload, headers, config.get("method"), "Authorization Access Token")


def generate_unique_id():
	return str(uuid.uuid4())


def request_and_post(
	url=None,
	payload=None,
	headers=None,
	method="POST",
	request_name=None,
	patient=None,
	otp=None,
	otp_reference=None,
):
	req = frappe.new_doc("ABDM Request")
	req.request = json.dumps(payload, indent=4)
	req.url = url
	req.request_name = request_name
	req.header = json.dumps(headers, indent=4)
	req.request_id = headers.get("headers") or None
	req.otp = otp
	req.otp_reference = otp_reference
	req.patient = patient

	try:
		response = requests.request(
			method=method,
			url=url,
			headers=headers,
			data=json.dumps(payload) or None,
		)

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

		if isinstance(response, dict) or isinstance(response, list):
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
	"""Send unlinked care context discovery details to ABDM (HIP → CM)."""

	settings = get_abdm_settings()

	if not settings or not settings.consent_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Consent Management Base URL not configured in ABDM Settings!",
		)

	token = get_token_for_hiecm()
	if not token or not token.get("accessToken"):
		frappe.throw("Unable to fetch valid access token for HIE-CM.")

	config = get_url("on_discover")
	url = settings.consent_base_url.rstrip("/") + config.get("url")

	auth_prefix = "Bearer " if token.get("tokenType", "").lower() == "bearer" else ""
	authorization = auth_prefix + token.get("accessToken")

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
		request_and_post(
			url=url,
			payload=payload,
			headers=headers,
			method=config.get("method"),
			request_name="User-Initiated On-Discover Request",
		)
	except Exception as e:
		frappe.log_error(
			message=frappe.get_traceback(),
			title="Failed to Process ABDM On-Discover Request",
		)
		raise e


@frappe.whitelist()
def on_init(abha_address=None, transaction_id=None, request_id=None, data=None):
	"""
	Processes ABDM On-Init API call after the init callback.
	Generates link-reference-number, triggers OTP to patient,
	and sends the response back to Consent Manager.
	"""

	try:
		# Validate required parameters
		if not (abha_address and transaction_id and request_id):
			frappe.throw("abha_address, transaction_id, and request_id are required for on_init.")

		settings = get_abdm_settings()
		if not settings or not settings.consent_base_url:
			frappe.throw(
				title="Not Configured",
				msg="Consent Management Base URL not configured in ABDM Settings!",
			)

		token = get_token_for_hiecm()
		if not token or not token.get("accessToken"):
			frappe.throw("Unable to fetch valid access token for HIE-CM.")

		config = get_url("on_init")
		url = settings.consent_base_url.rstrip("/") + config.get("url")

		auth_prefix = "Bearer " if token.get("tokenType", "").lower() == "bearer" else ""
		authorization = auth_prefix + token.get("accessToken")

		otp_expiry = add_to_date(now(), minutes=15)
		reference_number = generate_unique_id()

		payload = {
			"transactionId": transaction_id,
			"link": {
				"referenceNumber": reference_number,
				"authenticationType": "DIRECT",
				"meta": {
					"communicationMedium": "MOBILE",
					"communicationHint": "OTP",
					"communicationExpiry": format_datetime(otp_expiry, "yyyy-MM-ddTHH:mm:ss.SSS'Z'"),
				},
			},
			"response": {"requestId": request_id},
		}

		headers = {
			"Content-Type": "application/json",
			"REQUEST-ID": generate_unique_id(),
			"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
			"X-CM-ID": settings.x_cm_id,
			"Authorization": authorization,
		}

		# Send OTP to patient if exists
		patient = frappe.db.exists("Patient", {"abha_address": abha_address})
		otp = generate_otp()
		if patient:
			mobile_no = frappe.db.get_value("Patient", patient, "mobile")
			message = f"OTP to link your ABHA details is {otp}. This One Time Password will be valid for 10 mins. { settings.facility_name }"
			if mobile_no:
				if frappe.get_single_value("SMS Settings", "sms_gateway_url"):
					send_sms(mobile_no, message)
				else:
					frappe.log_error(
						message=f"Trying to send OTP to {mobile_no}.\nMessage:\n{message}",
						title="SMS not configured",
					)

		request_and_post(
			url,
			payload,
			headers,
			config.get("method"),
			"User-Initiated On-Init Request",
			patient,
			otp,
			reference_number,
		)

	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="On-Init Processing Failed")
		raise e


@frappe.whitelist()
def on_confirm(token=None, link_ref_number=None, request_id=None):
	"""
	Send care-context confirmation result to ABDM Consent Manager (CM).
	"""

	settings = get_abdm_settings()
	if not settings or not settings.consent_base_url:
		frappe.throw(
			title="Configuration Missing",
			msg="Consent Management Base URL not configured in ABDM Settings.",
		)

	auth_token = get_token_for_hiecm()
	if not auth_token or not auth_token.get("accessToken"):
		frappe.throw("Unable to fetch valid access token for HIE-CM.")

	config = get_url("on_confirm")
	url = settings.consent_base_url.rstrip("/") + config.get("url")

	auth_prefix = "Bearer " if auth_token.get("tokenType", "").lower() == "bearer" else ""
	authorization = auth_prefix + auth_token.get("accessToken")

	otp_request = validate_otp(token, link_ref_number)
	if not otp_request:
		payload = {
			{
				"code": "ABDM-9999",
				"message": "Invalid Reference Number / Token",
			}
		}
	else:
		otp_request_doc = frappe.get_doc("ABDM Request", otp_request)
		request_headers = json.loads(otp_request_doc.request or "{}")
		transaction_id = request_headers.get("transactionId")

		patient_details = []
		if transaction_id:
			init_request = frappe.db.exists(
				"ABDM Request",
				{
					"transaction_id": transaction_id,
					"url": "/abdm/callback/api/v3/hip/link/care-context/init",
					"patient": otp_request_doc.patient,
				},
			)

			if init_request:
				init_response = frappe.db.get_value("ABDM Request", init_request, "response")
				response_data = json.loads(init_response or "{}")
				patient_details = build_care_context_details(response_data.get("patient")) or []

				# test
				frappe.log_error(message=f"{patient_details}", title="Carecontext details")

		payload = {
			"patient": patient_details,
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
		request_and_post(
			url=url,
			payload=payload,
			headers=headers,
			method=config.get("method"),
			request_name="User-Initiated On-Confirm Request",
		)
	except Exception as e:
		frappe.log_error(
			message=frappe.get_traceback(), title="Failed to Process ABDM On-Confirm Request"
		)
		raise e


# Milestone-2 Dataflow
@frappe.whitelist()
def on_notify(request_id=None, consent_id=None):
	"""Acknowledges Consent Notification to ABDM HIE-CM (Consent Granted/Revoked/Expired)."""

	if not request_id or not consent_id:
		frappe.throw("Missing Request ID or Consent ID")

	try:
		settings = get_abdm_settings()
		if not settings or not settings.consent_base_url:
			frappe.throw(
				title="Configuration Missing",
				msg="Consent Management Base URL not configured in ABDM Settings.",
			)

		auth_token = get_token_for_hiecm()
		if not auth_token or not auth_token.get("accessToken"):
			frappe.throw("Unable to fetch valid access token for HIE-CM.")

		config = get_url("on_notify")
		url = settings.consent_base_url.rstrip("/") + config.get("url")

		auth_prefix = "Bearer " if auth_token.get("tokenType", "").lower() == "bearer" else ""
		authorization = auth_prefix + auth_token.get("accessToken")

		headers = {
			"Content-Type": "application/json",
			"REQUEST-ID": generate_unique_id(),
			"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
			"X-CM-ID": settings.x_cm_id,
			"Authorization": authorization,
		}

		payload = {
			"acknowledgement": {"status": "OK", "consentId": consent_id},
			"response": {"requestId": request_id},
		}

		try:
			request_and_post(
				url=url,
				payload=payload,
				headers=headers,
				method=config.get("method"),
				request_name="Data Flow On-Notify Request",
			)
		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(), title="Failed to Process ABDM On-Notify Request"
			)
			raise e

	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="Consent On-Notify Error")
		raise e


@frappe.whitelist()
def on_request(
	request_id=None, transaction_id=None, data_push_url=None, key_material=None, consent_id=None
):
	"""Acknowledges Health Information Request to ABDM HIE-CM."""

	if not request_id or not transaction_id:
		frappe.throw("Missing Request ID or Transaction ID")

	try:
		settings = get_abdm_settings()
		if not settings or not settings.consent_base_url:
			frappe.throw(
				title="Configuration Missing",
				msg="Consent Management Base URL not configured in ABDM Settings.",
			)

		auth_token = get_token_for_hiecm()
		if not auth_token or not auth_token.get("accessToken"):
			frappe.throw("Unable to fetch valid access token for HIE-CM.")

		config = get_url("on_notify")
		url = settings.consent_base_url.rstrip("/") + config.get("url")

		auth_prefix = "Bearer " if auth_token.get("tokenType", "").lower() == "bearer" else ""
		authorization = auth_prefix + auth_token.get("accessToken")

		headers = {
			"Content-Type": "application/json",
			"REQUEST-ID": generate_unique_id(),
			"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
			"X-CM-ID": settings.x_cm_id,
			"Authorization": authorization,
		}

		payload = {
			"hiRequest": {
				"transactionId": transaction_id,
				"sessionStatus": "ACKNOWLEDGED",
			},
			"response": {
				"requestId": request_id,
			},
		}

		try:
			request_and_post(
				url=url,
				payload=payload,
				headers=headers,
				method=config.get("method"),
				request_name="Data Flow On-Request Request",
			)
			if data_push_url:
				consent_doc = frappe.get_doc("ABDM Consent", consent_id)
				consent_doc.data_push_url = data_push_url
				consent_doc.key_material = json.dumps(key_material, indent=4)
				consent_doc.transaction_id = transaction_id
				consent_doc.save(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(), title="Failed to Process ABDM On-Request Request"
			)
			raise e

	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="Consent On-Request Error")
		raise e


def validate_otp(token, otp_reference):
	otp_verified = frappe.db.exists("ABDM Request", {"otp": token, "otp_reference": otp_reference})

	if not otp_verified:
		return False

	return otp_verified


def get_patient_details(abha_address=None):
	"""
	Return care context details for the given ABHA address.
	HI types: Prescription, DiagnosticReport, OPConsultation, DischargeSummary, ImmunizationRecord, HealthDocumentRecord, WellnessRecord, Invoice
	"""

	if not abha_address:
		return []

	patient = frappe.db.exists("Patient", {"abha_address": abha_address})

	if not patient:
		return []

	# Map doctypes to ABDM HI types
	doctype_map = {
		"Patient Encounter": "OPConsultation",
		"Medication Request": "Prescription",
		"Therapy Session": "WellnessRecord",
		"Diagnostic Report": "DiagnosticReport",
		"Discharge Summary": "DischargeSummary",
		"Patient Medical Record": "HealthDocumentRecord",
		"Sales Invoice": "Invoice",
	}

	details = []

	for doctype, hi_type in doctype_map.items():
		# records = frappe.db.get_all("FHIR Resource", filters={"patient": patient, "doctype": doctype}, fields=["*"])
		records = frappe.db.get_all(
			doctype,
			filters={"patient": patient, "docstatus": ["!=", 2]},
			fields=["*"],
			order_by="modified desc",
		)

		if not records:
			continue

		carecontexts = [
			{
				"referenceNumber": rec.name,
				"display": f"{doctype}/{rec.name}/{rec.patient}",
			}
			for rec in records
		]

		details.append(
			{
				"referenceNumber": patient,
				"display": f"{hi_type} Records",
				"careContexts": carecontexts,
				"hiType": hi_type,
				"count": len(carecontexts),
			}
		)

	return details


def build_care_context_details(data):
	"""
	Transform minimal care context data into detailed ABDM-compliant structure.
	Format matches the output of get_patient_details().
	"""

	doctype_map = {
		"OPConsultation": "Patient Encounter",
		"Prescription": "Medication Request",
		"WellnessRecord": "Therapy Session",
		"DiagnosticReport": "Diagnostic Report",
		"DischargeSummary": "Discharge Summary",
		"HealthDocumentRecord": "Patient Medical Record",
		"Invoice": "Sales Invoice",
	}

	details = []

	for item in data:
		patient_ref = item.get("referenceNumber")
		hi_type = item.get("hiType")
		care_contexts = item.get("careContexts", [])

		enriched_contexts = [
			{
				"referenceNumber": cc.get("referenceNumber"),
				"display": f"{doctype_map.get(hi_type)}/{cc.get('referenceNumber')}/{patient_ref}",
			}
			for cc in care_contexts
			if cc.get("referenceNumber")
		]

		details.append(
			{
				"referenceNumber": patient_ref,
				"display": f"{hi_type} Records",
				"careContexts": enriched_contexts,
				"hiType": hi_type,
				"count": len(enriched_contexts),
			}
		)

	return details


def get_carecontext(doc):
	"""HItypes: Prescription,DiagnosticReport,OPConsultation,DischargeSummary,ImmunizationRecord,HealthDocumentRecord,WellnessRecord,Invoice"""

	carecontext = []
	display = None
	hitype = None
	if doc.doctype == "Patient Encounter":
		display = f"OPD Record-{format_date(doc.encounter_date, 'dd-mm-yyyy')}-{doc.name}"
		hitype = "OPConsultation"
		carecontext.append(
			{
				"referenceNumber": doc.name,
				"display": f"{doc.appointment_type} with {doc.practitioner_name}",
			}
		)
	if doc.doctype == "Medication Request":
		display = f"Medication Request-{format_date(doc.order_date, 'dd-mm-yyyy')}-{doc.name}"
		hitype = "Prescription"
		carecontext.append(
			{
				"referenceNumber": doc.name,
				"display": f"{doc.medication} ordered by {doc.practitioner_name}",
			}
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
		req.is_callback = args.get("is_callback") or 0
		if args.get("abha_address"):
			patient = frappe.db.exists("Patient", {"abha_address": args.get("abha_address")})
			if patient:
				req.patient = patient
		if args.get("notification") and args.get("notification").get("status") in [
			"GRANTED",
			"SUCCESS",
		]:
			req.status = "Granted"
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
		if args.get("consent_id"):
			req.consent_id = args.get("consent_id")
		if args.get("data_push_url"):
			req.data_push_url = args.get("data_push_url")
		req.response = json.dumps(args.data, indent=4)
		req.insert(ignore_permissions=True)


def send_sms_notify(patient):
	if not patient:
		return

	mobile_no = frappe.db.get_value("Patient", patient, "mobile")

	if not mobile_no:
		frappe.msgprint(
			title="Not Configured",
			msg="Please add mobile number to send sms",
			indicator="red",
			alert=True,
		)
		return

	settings = get_abdm_settings()

	if not settings.consent_base_url:
		frappe.throw(
			title="Not Configured",
			msg="Consent Management Base URL not configured in ABDM Settings!",
		)

	token = get_token_for_hiecm()
	config = get_url("sms_notify")

	authorization = ("Bearer " if token.get("tokenType") == "bearer" else "") + token.get(
		"accessToken"
	)
	url = settings.consent_base_url + config.get("url")
	payload = {
		"notification": {
			"phoneNo": mobile_no,
			"hip": {
				"name": settings.facility_name,
				"id": settings.facility_id,
			},
		},
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


def generate_otp(length=6):
	"""
	Generates a numeric OTP of given length (default 6 digits)
	"""

	import secrets

	digits = "0123456789"
	otp = "".join(secrets.choice(digits) for _ in range(length))
	return otp
