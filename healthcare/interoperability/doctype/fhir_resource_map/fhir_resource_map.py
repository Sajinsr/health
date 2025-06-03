# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FHIRResourceMap(Document):
	def autoname(self):

		if not self.name:
			self.name = f"MAP-{self.frappe_doctype}-{self.fhir_resource}"

			# append fhir profile and name
			if self.fhir_profile:
				self.name = f"{self.name}-{self.fhir_profile}-{self.fhir_version}"
			else:
				self.name = f"{self.name}-{self.fhir_version}"

	def validate(self):

		missing = [
			fm.fhir_path
			for fm in self.field_map
			if fm.min_card > 0 and not fm.frappe_field and not fm.default_value
		]
		if missing:
			frappe.throw(
				"You must map or supply a default for these FHIR elements which are mandatory:\n  "
				+ "\n  ".join(missing)
			)
