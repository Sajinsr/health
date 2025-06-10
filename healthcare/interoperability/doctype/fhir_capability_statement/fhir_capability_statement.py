# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FHIRCapabilityStatement(Document):
	@frappe.whitelist()
	def render(self):
		return {
			"resourceType": "CapabilityStatement",
			"status": "active",
			"date": frappe.utils.now_datetime().isoformat(),
			"kind": "instance",
			"format": ["json"],
			"fhirVersion": self.fhir_version,
			"rest": [{"mode": "server", "resource": self.build_resource_statements()}],
		}

	def build_resource_statements(self):
		resources = []
		interactions_map = {
			"r": "read",
			"c": "create",
			"u": "update",
			"d": "delete",
		}

		for row in self.get("supported_resources"):
			map_doc = frappe.get_doc("FHIR Resource Map", row.fhir_resource_map)
			interactions = []
			for short, full in interactions_map.items():
				if row.get(short):
					interactions.append({"code": full})

			resource = {
				"type": map_doc.resource_type,
				"profile": map_doc.fhir_profile or None,
				"interaction": interactions,
				"documentation": row.description or "",
			}

			search_params = frappe.get_all(
				"FHIR Search Parameter",
				filters={"resource_type": map_doc.resource_type},
				fields=["parameter_name", "datatype", "url", "description"],
			)

			if len(search_params):
				resource["searchParam"] = []
				for sp in search_params:
					search_param_block = {
						"name": sp.parameter_name,
						"type": sp.datatype,
						"definition": sp.url,
						"documentation": sp.description,
					}
					resource["searchParam"].append(search_param_block)

			resources.append(resource)

		return resources
