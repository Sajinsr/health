# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.background_jobs import enqueue


class FHIRVersion(Document):
	@frappe.whitelist()
	def import_structure_definitions(self):

		if self.schema_file.endswith(".tgz") or self.schema_file.endswith(".tar.gz"):
			enqueue(
				"healthcare.interoperability.utils.fhir_utils.import_structure_definitions_from_package",
				queue="long",
				timeout=900,
				version_name=self.name,
				package_tarball=self.schema_file,
			)
		else:
			frappe.throw(
				_("Only .tgz / .tar.gz FHIR packages can be imported. " "Please upload a valid archive file.")
			)
