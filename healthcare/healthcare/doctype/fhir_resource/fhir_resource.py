# # Copyright (c) 2024, earthians Health Informatics Pvt. Ltd. and contributors
# # For license information, please see license.txt

import json
from copy import deepcopy

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

	if not mapper_exists:
		return

	mapper_doc = frappe.get_doc("FHIR Resource Mapper", mapper_exists)
	resource_type_json = frappe.db.get_value(
		"Resource Type", mapper_doc.resource_type, "resource_json"
	)

	if isinstance(resource_type_json, str):
		resource_type_json = json.loads(resource_type_json)

	for resource in resource_type_json:
		if isinstance(resource_type_json[resource], list):
			child_rows = [d for d in mapper_doc.resource_maps if d.get("parent_resource_field") == resource]
			child_docfield = child_rows[0].get("parent_docfield") if len(child_rows) else None

			child_resource = []
			if child_docfield:
				for item in doc.get(child_docfield):
					child_json = {}
					for child in resource_type_json[resource][0]:
						child_json = deepcopy(
							make_resource_map(item, child, resource_type_json[resource][0], child_rows)
						)
					child_resource.append(child_json)

			resource_type_json[resource] = child_resource
		else:
			make_resource_map(doc, resource, resource_type_json, mapper_doc.resource_maps)

	if resource_type_json:
		resource_exists = frappe.db.exists(
			"FHIR Resource", {"reference_doctype": doc.doctype, "referance_doc_name": doc.name}
		)
		if not resource_exists:
			resource = frappe.new_doc("FHIR Resource")
			resource.reference_doctype = doc.doctype
			resource.referance_doc_name = doc.name
			resource.resource_data = json.dumps(resource_type_json, indent=2, default=str)
		else:
			resource = frappe.get_doc("FHIR Resource", resource_exists)
			resource.resource_data = json.dumps(resource_type_json, indent=2, default=str)

		resource.save(ignore_permissions=True)


def make_resource_map(doc, resource, json, mapper_doc_child):
	json[resource] = None

	for d in mapper_doc_child:
		if d.get("resource_field") == resource:
			json[resource] = doc.get(d.doc_field)

	return json
