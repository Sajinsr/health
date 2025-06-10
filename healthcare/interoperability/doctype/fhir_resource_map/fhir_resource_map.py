# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from healthcare.interoperability.utils.fhir_engine import generate_fhir_resource


class FHIRResourceMap(Document):
	def autoname(self):

		if not self.name:
			self.name = f"MAP-{self.frappe_doctype}-{self.fhir_structure_def}"

			# append fhir profile and name
			if self.fhir_profile:
				self.name = f"{self.name}-{self.fhir_profile}-{self.fhir_version}"
			else:
				self.name = f"{self.name}-{self.fhir_version}"

	def validate(self):
		self.resource_type = self.fhir_structure_def.split("-", 1)[0]
		missing = [
			fm.fhir_path for fm in self.map if fm.min > 0 and not fm.frappe_field and not fm.default_value
		]
		if missing:
			frappe.throw(
				_(
					"You must map or supply a default value for these FHIR elements which are required as per Resource Structure Definition:\n  "
				)
				+ "\n  ".join(missing)
			)

	@frappe.whitelist()
	def save_mapped_elements(self, elements):

		self.set("map", [])
		for el in elements:
			self.append(
				"map",
				{
					"fhir_path": el.get("fhir_path"),
					"fhir_datatype": el.get("fhir_datatype"),
					"min": int(el.get("min") or 0),
					"max": str(el.get("max") or "1"),
					"short": el.get("short") or "",
					"definition": el.get("definition") or "",
					"is_required": bool(el.get("is_required")),
					"is_choice_type": bool(el.get("is_choice_type")),
					"frappe_field": el.get("frappe_field") or None,
					"default_value": el.get("default_value") or None,
				},
			)

		self.save(ignore_permissions=True)
		frappe.msgprint(_("FHIR field mappings saved."), alert=True)

	@frappe.whitelist()
	def preview_fhir_resource(self, docname):

		if not self.frappe_doctype:
			frappe.throw(_("Frappe Doctype is not specified in this FHIR Resource Map."))

		doc = frappe.get_doc(self.frappe_doctype, docname)

		resource = generate_fhir_resource(doc)
		return resource
