# -*- coding: utf-8 -*-
# Copyright (c) 2015, ESS LLP and contributors
# For license information, please see license.txt


import datetime

import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class FeeValidity(Document):
	def validate(self):
		self.update_status()

	def update_status(self):
		if getdate(self.valid_till) < getdate():
			self.status = "Expired"
		elif self.visited == self.max_visits:
			self.status = "Completed"
		else:
			self.status = "Active"


def create_fee_validity(appointment):
	if patient_has_validity(appointment):
		return

	fee_validity = frappe.new_doc("Fee Validity")
	fee_validity.practitioner = appointment.practitioner
	fee_validity.patient = appointment.patient
	fee_validity.medical_department = appointment.department
	fee_validity.patient_appointment = appointment.name
	fee_validity.sales_invoice_ref = frappe.db.get_value(
		"Sales Invoice Item", {"reference_dn": appointment.name}, "parent"
	)
	fee_validity.max_visits = frappe.db.get_single_value("Healthcare Settings", "max_visits") or 1
	valid_days = frappe.db.get_single_value("Healthcare Settings", "valid_days") or 1
	fee_validity.visited = 0
	fee_validity.start_date = getdate(appointment.appointment_date)
	fee_validity.valid_till = getdate(appointment.appointment_date) + datetime.timedelta(
		days=int(valid_days)
	)
	fee_validity.save(ignore_permissions=True)
	return fee_validity


def patient_has_validity(appointment):
	validity_exists = frappe.db.exists(
		"Fee Validity",
		{
			"practitioner": appointment.practitioner,
			"patient": appointment.patient,
			"status": "Active",
			"valid_till": [">=", appointment.appointment_date],
			"start_date": ["<=", appointment.appointment_date],
		},
	)

	return True if validity_exists else False


def update_validity_status():
	# update the status of fee validity daily
	validities = frappe.db.get_all("Fee Validity", {"status": ["not in", ["Expired", "Cancelled"]]})

	for fee_validity in validities:
		fee_validity_doc = frappe.get_doc("Fee Validity", fee_validity.name)
		fee_validity_doc.update_status()
		fee_validity_doc.save()
