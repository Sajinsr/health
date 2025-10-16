import json

import frappe
from frappe.utils import now_datetime

from healthcare.regional.india.abdm.utils import on_discover, post_abdm_request


@frappe.whitelist(allow_guest=True)
def discover():
	"""Handles ABDM User-Initiated Linking (HIP → Care Context Discovery Callback)"""

	try:
		data = json.loads(frappe.request.data or "{}")
		request_id = frappe.request.headers.get("REQUEST-ID")
		hip_id = frappe.request.headers.get("X-HIP-ID")
		timestamp = frappe.request.headers.get("TIMESTAMP")
		transaction_id = data.get("transactionId")

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

		# Extract patient ABHA address
		patient = data.get("patient", {})
		abha_address = patient.get("id") if patient else None

		# Log callback receipt
		post_abdm_request(
			path=frappe.request.path,
			headers=frappe.as_json(dict(frappe.request.headers), indent=2),
			request_name="Callback of User-Initiated Linking - Discover",
			abha_address=abha_address,
			error=data.get("error"),
			notification=data.get("notification"),
			transaction_id=transaction_id,
			company=frappe.get_cached_value("ABDM Settings", abdm_settings, "company"),
			request_id=request_id,
			data=data,
			is_callback=True,
		)

		# Process on-discover call
		if abha_address:
			try:
				on_discover(abha_address, transaction_id, request_id)
				return success_response(request_id, data)
			except Exception as e:
				frappe.log_error(message=frappe.get_traceback(), title="On-Discover Processing Failed")
				return error_response(request_id, str(e), status_code=500)
		else:
			return error_response(
				request_id,
				"Missing patient ABHA address in discovery request.",
				status_code=400,
			)

	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="Discover Callback Processing Error")
		return error_response(None, str(e), status_code=500)


def success_response(request_id, received_data):
	return {
		"timestamp": str(now_datetime()),
		"path": "/api/v3/hip/patient/care-context/discover",
		"status": "success",
		"status_code": 202,
		"requestId": request_id,
		"message": "Discovery callback processed successfully.",
		"received": received_data,
	}


def error_response(request_id, error_message, status_code=500):
	return {
		"timestamp": str(now_datetime()),
		"path": "/api/v3/hip/patient/care-context/discover",
		"status": "failed",
		"status_code": status_code,
		"error": error_message,
		"requestId": request_id,
	}
