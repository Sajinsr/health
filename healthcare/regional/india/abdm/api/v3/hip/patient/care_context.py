import json

import frappe
from frappe.utils import now_datetime

from healthcare.regional.india.abdm.utils import on_discover, post_abdm_request


@frappe.whitelist(allow_guest=True)
def discover():
	data = json.loads(frappe.request.data)
	if data:
		transaction_id = data.get("transactionId")
		request_id = frappe.request.headers.get("request-id")
		hip_id = frappe.request.headers.get("x-hip-id")
		exists = frappe.db.exists("ABDM Settings", {"facility_id": hip_id})
		# if not exists:
		# 	return {
		# 		"timestamp": str(now_datetime()),
		# 		"path": "/api/v3/hiecm/user-initiated-linking/patient/care-context/discover",
		# 		"status_code": 500,
		# 		"error": "X-HIP-ID is invalid, Please try again with correct X-HIP-ID",
		# 		"requestId": request_id,
		# 	}
		abha_address = None
		if data.get("patient"):
			abha_address = data.get("patient").get("id")
		args = {
			"path": frappe.request.path,
			"headers": frappe.as_json(frappe.request.headers, indent=2),
			"request_name": "Callback of User Initated Discover",
			"abha_address": abha_address,
			"error": data.get("error"),
			"notification": data.get("notification"),
			"transaction_id": transaction_id,
			"company": frappe.get_cached_value("ABDM Settings", exists, "company") if exists else None,
			"request_id": request_id,
			"data": data,
			"is_callback": True,
		}
		post_abdm_request(**args)
		response_message = {"status": "success", "received": data, "status_code": 202}

		if abha_address and transaction_id and request_id:
			try:
				on_discover(abha_address, transaction_id, request_id)
			except Exception as e:
				response_message = {
					"timestamp": str(now_datetime()),
					"path": "/api/v3/hiecm/user-initiated-linking/patient/care-context/discover",
					"status_code": 500,
					"error": e,
					"requestId": request_id,
				}
				frappe.log_error(message=e, title="Failed to Process on-discover")
		else:
			response_message = {
				"timestamp": str(now_datetime()),
				"path": "/api/v3/hiecm/user-initiated-linking/patient/care-context/discover",
				"status_code": 500,
				"error": "Need transaction id and request id to process the on-discover request",
				"requestId": request_id,
			}

		return response_message
