import json

import frappe
from frappe.utils import now_datetime

from healthcare.regional.india.abdm.utils import on_request, post_abdm_request


@frappe.whitelist()
def request():
	"""Handles ABDM Health Information Request Callback (CM → HIP)."""

	try:
		data = json.loads(frappe.request.data or "{}")
		request_id = frappe.request.headers.get("REQUEST-ID")
		hip_id = frappe.request.headers.get("X-HIP-ID")
		timestamp = frappe.request.headers.get("TIMESTAMP")

		hi_request = data.get("hiRequest", {})
		transaction_id = data.get("transactionId") or hi_request.get("transactionId")

		# Validate required headers and consent id
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

		consent_id = hi_request.get("consent").get("id") if hi_request.get("consent") else None

		if consent_id:
			# validate consent id
			if not frappe.db.exists("ABDM Consent", consent_id):
				return error_response(
					request_id,
					"Consent ID not found. Please verify the provided Consent ID in the payload.",
					status_code=403,
				)
			data_push_url = hi_request.get("dataPushUrl")
			key_material = hi_request.get("keyMaterial")

			post_abdm_request(
				path=frappe.request.path,
				headers=frappe.as_json(dict(frappe.request.headers), indent=2),
				request_name="Callback of Data Flow - Notify",
				error=data.get("error"),
				notification=data.get("notification"),
				company=frappe.get_cached_value("ABDM Settings", abdm_settings, "company"),
				request_id=request_id,
				data=data,
				transaction_id=transaction_id,
				consent_id=consent_id,
				data_push_url=data_push_url,
				is_callback=True,
			)

			# Process on-request call
			try:
				on_request(request_id, transaction_id, data_push_url, key_material, consent_id)
				return success_response(request_id, data, "Data Flow-Request callback processed successfully.")
			except Exception as e:
				frappe.log_error(message=frappe.get_traceback(), title="On-Request Processing Failed")
				return error_response(request_id, str(e), status_code=500)
		else:
			return error_response(
				request_id,
				"Missing Consent ID in Notify Request.",
				status_code=400,
			)

	except Exception as e:
		frappe.log_error(
			message=frappe.get_traceback(), title="Data Flow-Request Callback Processing Error"
		)
		return error_response(None, str(e), status_code=500)


def success_response(request_id, received_data, success_message):
	return {
		"timestamp": str(now_datetime()),
		"path": "/api/v3/hip/health-information/request",
		"status": "success",
		"status_code": 202,
		"requestId": request_id,
		"message": success_message,
		"received": received_data,
	}


def error_response(request_id, error_message, status_code=500):
	return {
		"timestamp": str(now_datetime()),
		"path": "/api/v3/hip/health-information/request",
		"status": "failed",
		"status_code": status_code,
		"error": error_message,
		"requestId": request_id,
	}
