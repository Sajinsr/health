# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe


class CapabilityStatementRenderer:
	def get(self, fhir_version):
		cs_doc = frappe.get_doc("FHIR Capability Statement", {"fhir_version": fhir_version})

		return {
			"resourceType": "CapabilityStatement",
			"id": cs_doc.name,
			"url": f"{frappe.utils.get_url()}/api/fhir/{fhir_version}/metadata",
			"version": fhir_version,
			"name": cs_doc.name.replace(" ", ""),
			"title": cs_doc.title or cs_doc.name,
			"status": "active",
			"experimental": 0,
			"publisher": cs_doc.publisher or "earthians Health",
			"date": frappe.utils.now_datetime().isoformat(),
			"kind": "instance",
			"software": {
				"name": "Marley Healthcare FHIR Server",
				"version": frappe.get_conf().get("version") or "0.1.0",
			},
			"implementation": {
				"description": "Marley Healthcare FHIR Interface",
				"url": frappe.utils.get_url(),
			},
			"fhirVersion": fhir_version,
			"format": ["json"],
			"rest": [
				{
					"mode": "server",
					"documentation": cs_doc.description or "",
					"resource": self.build_resource_statements(cs_doc),
				}
			],
		}

	def build_resource_statements(self, cs_doc):
		resources = []
		interactions_map = {
			"r": "read",
			"c": "create",
			"u": "update",
			"d": "delete",
		}

		for row in cs_doc.get("supported_resources"):
			map_doc = frappe.get_doc("FHIR Resource Map", row.fhir_resource_map)
			interactions = []
			for short, full in interactions_map.items():
				if row.get(short):
					interactions.append({"code": full})

			resource = {
				"type": map_doc.resource_type,
				"interaction": interactions,
				"documentation": row.description or "",
			}

			if map_doc.fhir_profile:
				resource["profile"] = map_doc.fhir_profile

			search_params = frappe.get_all(
				"FHIR Search Parameter",
				filters={"resource_type": map_doc.resource_type},
				fields=["parameter_name", "datatype", "url", "description"],
			)

			if search_params:
				resource["searchParam"] = []
				for sp in search_params:
					resource["searchParam"].append(
						{
							"name": sp.parameter_name,
							"type": sp.datatype,
							"definition": sp.url,
							"documentation": sp.description,
						}
					)

			resources.append(resource)

		return resources


def capability_statement_handler(version):
	try:
		return CapabilityStatementRenderer().get(version)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "CapabilityStatement Error")
		frappe.throw("Unable to generate CapabilityStatement")
