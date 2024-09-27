# # Copyright (c) 2024, earthians Health Informatics Pvt. Ltd. and contributors
# # For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document


class FHIRResource(Document):
	pass


def make_fhir_resource(doc, method=None):
	settings = frappe.get_single("Healthcare Settings")
	if not settings.fhir_capable or not settings.fhir_version:
		return

	mapper_exists = frappe.db.exists(
		"FHIR Resource Mapper", {"document_type": doc.doctype, "version": settings.fhir_version}
	)
	resource_data = {}
	if mapper_exists:
		mapper_doc = frappe.get_doc("FHIR Resource Mapper", mapper_exists)
		for i in mapper_doc.data:
			if i.resource_field:
				resource_data[i.resource_field] = doc.get(i.doc_field)

	if resource_data:
		resource_exists = frappe.db.exists(
			"FHIR Resource", {"reference_doctype": doc.doctype, "referance_doc_name": doc.name}
		)
		if not resource_exists:
			resource = frappe.new_doc("FHIR Resource")
			resource.reference_doctype = doc.doctype
			resource.referance_doc_name = doc.name
			resource.resource_data = json.dumps(resource_data, indent=2, sort_keys=True, default=str)
		else:
			resource = frappe.get_doc("FHIR Resource", resource_exists)
			resource.resource_data = json.dumps(resource_data, indent=2, sort_keys=True, default=str)
		resource.save(ignore_permissions=True)
