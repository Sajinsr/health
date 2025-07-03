# import importlib

import json

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from frappe.website.utils import build_response


class AbdmHandler(BaseRenderer):
	def __init__(self, path, http_status_code=None):
		super().__init__(path, http_status_code)

	def can_render(self):
		if self.path.startswith("abdm/callback"):
			return True
		return False

	def render(self):
		try:
			method = frappe.request.method
			prefix = "abdm/callback"
			callback_path = self.path.removeprefix(prefix)
			frappe.log_error(
				message=f"Callback Request intiated on path: {callback_path}.",
				title="ABDM Callback Request Initiated",
			)
			if method == "POST" and callback_path:
				try:
					dotted_path = callback_path.replace("-", "_").replace("/", ".")
					abdm_path = f"healthcare.regional.india.abdm{dotted_path}".replace("..", ".")
					method = frappe.get_attr(abdm_path)
					response_data = method()
					status_code = response_data.get("status_code") or 200
				except json.JSONDecodeError:
					response_data = {"status": "error", "message": "Invalid JSON format in request body."}
					status_code = 400
				except Exception as e:
					response_data = {
						"status": "error",
						"message": f"Error processing ABHA Request: {str(e)}",
					}
					status_code = 500
			else:
				response_data = {
					"status": "error",
					"message": f"Method {method} not allowed for {self.path}. Use POST.",
				}
				status_code = 405
			frappe.log_error(
				message=f"Response Data: {response_data}, Status Code: {status_code}",
				title="ABDM Callback Request Processed",
			)
			return build_response(
				self.path, response_data, status_code or self.http_status_code, self.headers
			)
		except Exception as e:
			frappe.log_error(message=e, title="ABDM Callback Request Failed")
			return build_response(
				self.path,
				{"status": "error", "message": f"Internal server error during ABDM API processing: {str(e)}"},
				500,
				self.headers,
			)


# @frappe.whitelist(allow_guest=True)
# def handle_abdm_apis():
# 	request = frappe.request
# 	if request.path.startswith(
# 		"/api/method/healthcare.regional.india.abdm.handler.handle_abdm_apis/callback"
# 	):
# 		prefix = "/api/method/healthcare.regional.india.abdm.handler.handle_abdm_apis/callback"

# 		callback_path = request.path.removeprefix(prefix)
# 		if callback_path:
# 			dotted_path = callback_path.replace("-", "_").replace("/", ".")

# 			abdm_path = f"healthcare.regional.india.abdm{dotted_path}".replace("..", ".")
# 			method = frappe.get_attr(abdm_path)

# 			return method()
