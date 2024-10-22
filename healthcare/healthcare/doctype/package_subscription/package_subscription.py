# Copyright (c) 2024, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document, _
from frappe.utils import get_link_to_form


class PackageSubscription(Document):
	def validate(self):
		if self.total_package_amount:
			self.outstanding_amount = self.total_package_amount - self.paid_amount

		if not self.status == "Discontinued":
			if self.paid_amount == 0:
				self.status = "Unpaid"
			else:
				self.status = "Paid" if self.outstanding_amount == 0 else "Partially Paid"

	def on_update_after_submit(self):
		if self.total_package_amount:
			self.db_set("outstanding_amount", self.total_package_amount - self.paid_amount)

		if not self.status == "Discontinued":
			if self.paid_amount == 0:
				self.db_set("status", "Unpaid")
			else:
				self.db_set("status", "Paid" if self.outstanding_amount == 0 else "Partially Paid")

	def before_insert(self):
		exists = frappe.db.exists(
			"Package Subscription",
			{
				"patient": self.patient,
				"healthcare_package": self.healthcare_package,
				"docstatus": 0,
			},
		)

		if exists:
			frappe.throw(
				_(
					f"Subscription already exists for patient {frappe.bold(self.patient_name)}: {get_link_to_form('Package Subscription', exists)}"
				)
			)

	@frappe.whitelist()
	def get_package_details(self):
		if not self.healthcare_package:
			return

		package_doc = frappe.get_doc("Healthcare Package", self.healthcare_package)

		self.package_details = []
		for item in package_doc.package_items:
			self.append("package_details", (frappe.copy_doc(item)).as_dict())
		self.total_package_amount = package_doc.total_package_amount
		self.outstanding_amount = package_doc.total_package_amount
		self.discount_amount = package_doc.discount_amount
		self.total_amount = package_doc.total_amount
