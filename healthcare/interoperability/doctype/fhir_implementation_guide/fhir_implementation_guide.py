# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FHIRImplementationGuide(Document):
	@frappe.whitelist()
	def render(self):
		return {
			"resourceType": "ImplementationGuide",
			"url": self.url,
			"version": self.version,
			"name": self.name,
			"status": self.status,
			"fhirVersion": [self.fhir_version],
			"publisher": self.publisher,
			"description": self.description,
			"packageId": self.name.lower().replace(" ", "-"),
			"dependsOn": self.build_dependencies(),
		}

	def build_dependencies(self):
		return [{"uri": row.url, "version": row.ig_version} for row in self.dependencies]
