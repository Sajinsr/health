import json

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from frappe.website.utils import build_response


class ABDMCallbackError(Exception):
	"""Custom exception for ABDM callback errors."""

	pass


class ABDMRequestValidator:
	"""Handles validation of ABDM request payloads."""

	def __init__(self, payload):
		self.payload = payload
		self.response = payload.get("response") or {}

	def has_valid_request_id(self):
		return bool(self.response.get("requestId"))

	def has_valid_transaction_id(self):
		return bool(self.payload.get("transactionId"))

	def is_duplicate_transaction(self):
		"""Check if the transaction ID already exists."""
		return frappe.db.exists("ABDM Request", {"transaction_id": self.payload.get("transactionId")})

	def is_granted_request(self):
		"""Check if request ID exists and is granted."""
		return frappe.db.exists(
			"ABDM Request",
			{"request_id": self.response.get("requestId"), "status": "Granted"},
		)

	def is_confirmation_request(self):
		"""Check if the request is a OTP confirmation request"""
		return bool(self.payload.get("confirmation"))


class AbdmHandler(BaseRenderer):
	"""Custom renderer for handling ABDM callback routes."""

	def __init__(self, path, http_status_code=None):
		super().__init__(path, http_status_code)
		self.prefix = "abdm/callback"
		self.response_data = {}
		self.status_code = 200

	def can_render(self):
		return self.path.startswith(self.prefix)

	def render(self):
		try:
			if frappe.request.method != "POST":
				return self._build_success_response({}, 200)

			payload = self._get_request_payload()
			callback_path = self.path.removeprefix(self.prefix)

			if not callback_path:
				return self._build_success_response({}, 200)

			validator = ABDMRequestValidator(payload)
			self.response_data, self.status_code = self._process_callback(callback_path, validator)

			frappe.log_error(
				message=f"Response Data: {self.response_data}, Status Code: {self.status_code}",
				title="ABDM Callback Request Processed",
			)

			return self._build_success_response(self.response_data, self.status_code)

		except ABDMCallbackError as e:
			return self._build_error_response(str(e), 400)
		except Exception as e:
			frappe.log_error(message=frappe.get_traceback(), title="ABDM Callback Request Failed")
			return self._build_error_response(
				f"Internal server error during ABDM API processing: {str(e)}", 500
			)

	def _get_request_payload(self):
		try:
			data = frappe.request.data
			if not data:
				raise ABDMCallbackError("Empty request payload.")
			return json.loads(data)
		except json.JSONDecodeError:
			raise ABDMCallbackError("Invalid JSON in request payload.")

	def _process_callback(self, callback_path, validator):
		"""Core logic for handling various ABDM callback scenarios."""
		if not isinstance(validator.payload, dict):
			raise ABDMCallbackError("Invalid response format in payload.")

		# Case 1: Request ID based callback
		if validator.has_valid_request_id():
			if validator.is_granted_request():
				return self._get_method_response(callback_path)
			else:
				return self._error("Invalid or expired Request ID.", 400)

		# Case 2: Transaction ID based callback
		elif validator.has_valid_transaction_id():
			if validator.is_duplicate_transaction():
				return self._error("Duplicate transaction request.", 400)
			return self._get_method_response(callback_path)

		# Case 3: Confirmation request
		elif validator.is_confirmation_request():
			return self._get_method_response(callback_path)

		# Case 4: Unknown payload format
		else:
			raise ABDMCallbackError("Missing both requestId and transactionId in payload.")

	def _get_method_response(self, path):
		try:
			dotted_path = path.replace("-", "_").replace("/", ".")
			method_path = f"healthcare.regional.india.abdm{dotted_path}".replace("..", ".")
			method = frappe.get_attr(method_path)
			response = method()
			status_code = response.get("status_code", 200) if isinstance(response, dict) else 200
			return response, status_code
		except Exception as e:
			raise ABDMCallbackError(f"Error invoking callback method: {str(e)}")

	def _build_success_response(self, data, status_code=200):
		return build_response(self.path, data, status_code, self.headers)

	def _build_error_response(self, message, status_code=500):
		response_data = {"status": "error", "message": message}
		return build_response(self.path, response_data, status_code, self.headers)

	def _error(self, message, status_code=400):
		return {"status": "error", "message": message}, status_code
