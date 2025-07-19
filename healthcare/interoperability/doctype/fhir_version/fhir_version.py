# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.background_jobs import enqueue

from healthcare.interoperability.fhir_engine.fhir_package_importer import FHIRPackageImporter


class FHIRVersion(Document):
	@frappe.whitelist()
	def import_structure_definitions(self):
		if self.schema_file.endswith(".tgz") or self.schema_file.endswith(".tar.gz"):
			enqueue(
				"healthcare.interoperability.doctype.fhir_version.fhir_version.import_fhir_package_job",
				queue="long",
				job_name=f"Import FHIR Package {self.schema_file}",
				package_tarball=self.schema_file,
				version_name=self.name,
			)
		else:
			frappe.throw(
				_(
					"Only .tgz / .tar.gz FHIR packages can be imported for now. Please upload a valid archive file."
				)
			)


def import_fhir_package_job(package_tarball, version_name):
	importer = FHIRPackageImporter(
		package_tarball=package_tarball,
		version_name=version_name,
	)
	importer.import_package()
