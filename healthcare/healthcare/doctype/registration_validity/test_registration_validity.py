# Copyright (c) 2023, healthcare and Contributors
# See license.txt

import frappe

from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from healthcare.healthcare.doctype.patient_appointment.test_patient_appointment import (
	create_appointment,
	create_healthcare_docs,
	update_status
)


class TestRegistrationValidity(FrappeTestCase):
	def test_create_registration(self):
		patient, practitioner = create_healthcare_docs()
		frappe.db.set_value("Healthcare Settings", None, "collect_registration_fee", 1)
		frappe.db.set_value("Healthcare Settings", None, "registration_fee", 300)
		frappe.db.set_value("Healthcare Settings", None, "automate_appointment_invoicing", 1)
		appointment = create_appointment(patient, practitioner, nowdate(), invoice=1)
		self.assertEqual(frappe.db.get_value("Patient Appointment", appointment.name, "invoiced"), 1)
		sales_invoice_name = frappe.db.get_value(
			"Sales Invoice Item", {"reference_dn": appointment.name}, "parent"
		)
		self.assertTrue(sales_invoice_name)
		self.assertEqual(
			frappe.db.get_value("Sales Invoice", sales_invoice_name, "company"), appointment.company
		)
		self.assertEqual(
			frappe.db.get_value("Sales Invoice", sales_invoice_name, "patient"), appointment.patient
		)

		self.assertEqual(
			frappe.db.get_value("Sales Invoice", sales_invoice_name, "total"), (appointment.paid_amount + 300)
		)

		registration = frappe.db.exists("Registration Validity", {"sales_invoice_reference": sales_invoice_name})
		self.assertTrue(registration)

		if registration:
			self.assertEqual(
			frappe.db.get_value("Registration Validity", registration, "status"), "Active"
		)

	
	def test_cancel_registration(self):
		patient, practitioner = create_healthcare_docs()
		frappe.db.set_value("Healthcare Settings", None, "enable_free_follow_ups", 1)
		appointment = create_appointment(patient, practitioner, nowdate())
		fee_validity = frappe.db.get_value(
			"Fee Validity", {"patient": patient, "practitioner": practitioner}
		)
		# fee validity created
		self.assertTrue(fee_validity)

		# first follow up appointment
		appointment = create_appointment(patient, practitioner, add_days(nowdate(), 1))
		self.assertEqual(frappe.db.get_value("Fee Validity", fee_validity, "visited"), 1)

		update_status(appointment.name, "Cancelled")
		# check fee validity updated
		self.assertEqual(frappe.db.get_value("Fee Validity", fee_validity, "visited"), 0)

		frappe.db.set_value("Healthcare Settings", None, "enable_free_follow_ups", 0)
		frappe.db.set_value("Healthcare Settings", None, "automate_appointment_invoicing", 1)
		appointment = create_appointment(patient, practitioner, add_days(nowdate(), 1), invoice=1)
		update_status(appointment.name, "Cancelled")
		# check invoice cancelled
		sales_invoice_name = frappe.db.get_value(
			"Sales Invoice Item", {"reference_dn": appointment.name}, "parent"
		)
		self.assertEqual(frappe.db.get_value("Sales Invoice", sales_invoice_name, "status"), "Cancelled")

		# if registration exist check registration validity cancelled
		registration_status = frappe.db.get_value(
			"Registration Validity", {"sales_invoice_reference": sales_invoice_name}, "status"
		)
		if registration_status:
			self.assertEqual(registration_status, "Cancelled")
