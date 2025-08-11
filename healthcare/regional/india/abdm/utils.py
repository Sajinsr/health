import json
import uuid
from datetime import datetime

import requests

import frappe

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
