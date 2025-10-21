import json

import frappe
from frappe.utils import now_datetime

from healthcare.regional.india.abdm.utils import on_confirm, on_init, post_abdm_request


@frappe.whitelist(allow_guest=True)
def init():
	"""Handles ABDM User-Initiated Linking (Care Context Init Callback)"""

	try:
		data = json.loads(frappe.request.data or "{}")
		request_id = frappe.request.headers.get("REQUEST-ID") or frappe.request.headers.get("request-id")
		hip_id = frappe.request.headers.get("X-HIP-ID") or frappe.request.headers.get("x-hip-id")
		timestamp = frappe.request.headers.get("TIMESTAMP")
		transaction_id = data.get("transactionId")
		abha_address = data.get("abhaAddress")

		# Validate required headers
		if not (request_id and hip_id and timestamp and transaction_id):
			return error_response(
				request_id,
				"Missing required headers or transactionId",
				status_code=400,
			)

		# Validate HIP registration
		abdm_settings = frappe.db.exists("ABDM Settings", {"facility_id": hip_id})
		if not abdm_settings:
			return error_response(
				request_id,
				"Invalid X-HIP-ID. Please verify facility registration.",
				status_code=403,
			)

		post_abdm_request(
			path=frappe.request.path,
			headers=frappe.as_json(dict(frappe.request.headers), indent=2),
			request_name="Callback of User-Initiated Linking - Init",
			abha_address=abha_address,
			error=data.get("error"),
			notification=data.get("notification"),
			transaction_id=transaction_id,
			company=frappe.get_cached_value("ABDM Settings", abdm_settings, "company"),
			request_id=request_id,
			data=data,
			is_callback=True,
		)

		# Process on-init call
		if abha_address:
			try:
				on_init(abha_address, transaction_id, request_id, data)
				return success_response(request_id, data, "/api/v3/hip/link/care-context/init")
			except Exception as e:
				frappe.log_error(message=frappe.get_traceback(), title="On-Init Processing Failed")
				return error_response(
					request_id, str(e), status_code=500, path="/api/v3/hip/link/care-context/init"
				)
		else:
			return error_response(
				request_id,
				"Missing ABHA address in init request.",
				status_code=400,
				path="/api/v3/hip/link/care-context/init",
			)

	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="Init Callback Processing Error")
		return error_response(None, str(e), status_code=500, path="/api/v3/hip/link/care-context/init")


@frappe.whitelist(allow_guest=True)
def confirm():
	"""
	HIP Callback endpoint to confirm care-context linking for a patient.
	Receives token and linkRefNumber and triggers on-confirm process.
	"""
	try:
		data = json.loads(frappe.request.data or "{}")
		request_id = frappe.request.headers.get("REQUEST-ID") or frappe.request.headers.get("request-id")
		hip_id = frappe.request.headers.get("X-HIP-ID") or frappe.request.headers.get("x-hip-id")
		timestamp = frappe.request.headers.get("TIMESTAMP")

		if not (request_id and hip_id and timestamp):
			return error_response(
				request_id, "Missing required headers", 400, "/api/v3/hip/link/care-context/confirm"
			)

		# Validate HIP registration
		abdm_settings = frappe.db.exists("ABDM Settings", {"facility_id": hip_id})
		if not abdm_settings:
			return error_response(
				request_id,
				"Invalid X-HIP-ID. Please verify facility registration.",
				403,
				"/api/v3/hip/link/care-context/confirm",
			)

		# Validate request body
		confirmation = data.get("confirmation")
		if not confirmation or not confirmation.get("token") or not confirmation.get("linkRefNumber"):
			return error_response(
				request_id,
				"Missing token or linkRefNumber in confirmation",
				400,
				"/api/v3/hip/link/care-context/confirm",
			)

		notification = {"status": "SUCCESS"}

		post_abdm_request(
			path=frappe.request.path,
			headers=frappe.as_json(dict(frappe.request.headers), indent=2),
			request_name="Callback of User-Initiated Linking - Confirm",
			error=data.get("error"),
			company=frappe.get_cached_value("ABDM Settings", abdm_settings, "company"),
			request_id=request_id,
			notification=notification,
			data=data,
			is_callback=True,
		)

		try:
			on_confirm(
				token=confirmation.get("token"),
				link_ref_number=confirmation.get("linkRefNumber"),
				request_id=request_id,
			)
			return success_response(request_id, data, "/api/v3/hip/link/care-context/confirm")
		except Exception as e:
			frappe.log_error(message=frappe.get_traceback(), title="On-Confirm Processing Failed")
			return error_response(request_id, str(e), 500, "/api/v3/hip/link/care-context/confirm")

	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="Confirm Callback Processing Error")
		return error_response(None, str(e), 500, "/api/v3/hip/link/care-context/confirm")


def success_response(request_id, received_data, path):
	return {
		"timestamp": str(now_datetime()),
		"path": path,
		"status": "success",
		"status_code": 202,
		"requestId": request_id,
		"message": "Init callback processed successfully.",
		"received": received_data,
	}


def error_response(request_id, error_message, status_code=500, path=None):
	return {
		"timestamp": str(now_datetime()),
		"path": path,
		"status": "failed",
		"status_code": status_code,
		"error": error_message,
		"requestId": request_id,
	}
