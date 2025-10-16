import json

import frappe

from healthcare.regional.india.abdm.utils import post_abdm_request


@frappe.whitelist(allow_guest=True)
def on_notify():
	data = json.loads(frappe.request.data)
	if data:
		args = {
			"path": frappe.request.path,
			"headers": json.dumps(frappe.request.headers, indent=2),
			"request_name": "Callback of SMS Notify",
			"error": data.get("error"),
			"notification": data.acknowledgement.get("status") if data.get("acknowledgement") else None,
			"data": data,
			"is_callback": True,
		}

		post_abdm_request(**args)

	return {"status": "success", "received": data, "status_code": 200}
