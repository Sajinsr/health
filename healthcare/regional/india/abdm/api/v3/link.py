import json

import frappe

from healthcare.regional.india.abdm.utils import post_abdm_request, send_sms_notify


@frappe.whitelist(allow_guest=True)
def on_carecontext():
	data = json.loads(frappe.request.data)
	if data:
		args = {
			"path": frappe.request.path,
			"headers": json.dumps(frappe.request.headers, indent=2),
			"request_name": "Callback of HIP Link Carecontext",
			"abha_address": data.get("abhaAddress"),
			"error": data.get("error"),
			"notification": data.get("notification"),
			"data": data,
			"is_callback": True,
		}

		post_abdm_request(**args)

		if frappe.local.response["http_status_code"] == 200:
			patient = frappe.db.exists("Patient", {"abha_address": args.get("abha_address")})
			if patient:
				send_sms_notify(patient)

	return {"status": "success", "received": data, "status_code": 200}
