# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import json

import requests

import frappe
from frappe.model.document import Document


class FHIRResource(Document):
	@frappe.whitelist()
	def validate_fhir_resource_with_validator(self):
		if not self.fhir_resource:
			return {"error": "No resource JSON to validate."}

		try:
			payload = json.loads(self.fhir_resource)

			response = requests.post(
				"https://validator.fhir.org/validate",
				headers={"Content-Type": "application/fhir+json"},
				data=json.dumps(payload),
				timeout=10,
			)

			if response.status_code != 200:
				return {
					"error": f"FHIR Validator responded with {response.status_code}",
					"response": response.text,
				}

			return {"issues": response.json().get("issue", []), "status": "success"}

		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "FHIR Remote Validation Error")
			return {"error": str(e)}
