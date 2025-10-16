# Copyright (c) 2022, healthcare and contributors
# For license information, please see license.txt

import json

# import frappe
from frappe.model.document import Document


class ABDMRequest(Document):
	def validate(self):
		self.set_request_id()

	def set_request_id(self):
		if not self.request_id:
			headers = json.loads(self.header)
			if isinstance(headers, dict) and (headers.get("REQUEST-ID") or headers.get("Request-Id")):
				self.request_id = headers.get("REQUEST-ID") or headers.get("Request-Id")
			elif isinstance(headers, list):
				for header in headers:
					if header[0] == "Request-Id" or header[0] == "REQUEST-ID":
						self.request_id = header[1]
						break
