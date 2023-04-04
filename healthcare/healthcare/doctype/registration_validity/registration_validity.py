# Copyright (c) 2023, healthcare and contributors
# For license information, please see license.txt

import frappe

from frappe.model.document import Document
from frappe.utils import getdate


class RegistrationValidity(Document):
	def on_cancel(self):
		self.db_set("status", "Cancelled")

	def on_submit(self):
		self.set_status()

	def set_status(self):
		today = getdate()
		valid_to = getdate(self.valid_to) if self.valid_to else None

		if valid_to and valid_to <= today:
			self.db_set("status", "Expired")
		elif not valid_to or (valid_to and valid_to > today):
			self.db_set("status", "Active")


def update_registration_status():
	# update the status of validity daily
	registrations = frappe.get_all(
		"Registration Validity",
		{"status": ("not in", ["Expired", "Cancelled"]), "valid_to": ["is", "not set"]},
		as_dict=1,
	)

	for registration in registrations:
		frappe.get_doc("Registration Validity", registration.name).set_status()
