import json

import frappe

from healthcare.regional.india.abdm.utils import post_abdm_request


@frappe.whitelist(allow_guest=True)
def notify():
	data = json.loads(frappe.request.data)
	if data:
		args = {
			"path": frappe.request.path,
			"headers": frappe.as_json(frappe.request.headers, indent=2),
			"request_name": "Callback of HIP Link Carecontext Notify",
			"abha_address": data.get("abhaAddress"),
			"error": data.get("error"),
			"notification": data.get("notification"),
			"data": data,
		}
		post_abdm_request(**args)

	return {"status": "success", "received": data, "status_code": 200}
