# Copyright (c) 2018, ESS LLP and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json

import frappe
from frappe import _
from frappe.utils import getdate

from healthcare.healthcare.utils import (
	get_doc_for_appointment,
	get_sales_invoice_for_healthcare_doc,
)

# from healthcare.healthcare.doctype.patient.patient import set_invoice_details_for_appointment


@frappe.whitelist()
def get_appointments(
	date,
	to_date,
	status_values,
	practitioner=None,
	patient=None,
	company=None,
	service_unit=None,
	appointment_type=None,
):
	if status_values != "" or not status_values:
		statuses = status_values.split(",")
	else:
		statuses = False

	query = """
	select
		pa.name, pa.patient_name, pa.patient, pa.practitioner, pa.appointment_date, pa.duration, pa.service_unit,
		pa.appointment_time, pa.status, pa.department, pa.appointment_type, pa.notes, pa.invoiced, pa.practitioner_name, pa.procedure_template,
		pp.comments, pa.company,
		# pa.schc_package_assignment,
		# pi.item_code, pi.completed_session, pi.balance_sessions,
		# pa.schc_package_item,
		# hp.status as hp_status,
		si.status as invoice_status, enc.name as encounter,
		# enc.has_drug_prescription, enc.has_item_prescription, enc.has_lab_prescription, enc.has_procedure_prescription, enc.has_radiology_prescription,
		enc.docstatus as encounter_status"""
	# add MCA custom field
	mca_payment_status = (
		frappe.get_meta("Patient Appointment").has_field("mca_payment_status") or False
	)
	# if mca_payment_status:
	# 	query += ", pa.mca_payment_status "

	# add COVID-19 custom field
	covid_test_passed = frappe.get_meta("Patient Appointment").has_field("covid_test_passed") or False
	# if covid_test_passed:
	# 	query += ", pa.covid_test_passed "

	# add patient confirm custom field
	patient_confirmed = frappe.get_meta("Patient Appointment").has_field("patient_confirmed") or False
	# if patient_confirmed:
	# 	query += ", pa.patient_confirmed "

	# add plan of care custom field
	plan_of_care = frappe.get_meta("Patient Encounter").has_field("plan_of_care") or False
	# if plan_of_care:
	# 	query += ", enc.plan_of_care as plan_of_care "
	query += """
	from
		`tabPatient Appointment` pa left join
		`tabProcedure Prescription` pp on pp.name = pa.procedure_prescription left join
		# `tabHealthcare Package Assignment` hp on hp.name = pa.schc_package_assignment left join
		# `tabHealthcare Package Item` pi on pi.parent = pa.schc_package_assignment and pi.item_code = pa.schc_package_item left join
		`tabSales Invoice Item` si_item on si_item.reference_dn = pa.name and si_item.docstatus = 1 left join
		`tabSales Invoice` si on si.name = si_item.parent left join
		`tabPatient Encounter` enc on enc.appointment = pa.name and enc.docstatus = 1
	where
		"""
	query += "pa.company='{0}'".format(company)
	if date:
		query += " and pa.appointment_date>='{0}' and pa.appointment_date<='{1}'".format(
			getdate(date), getdate(to_date)
		)
	if patient:
		query += " and pa.patient='{0}'".format(patient)
	if practitioner:
		query += " and pa.practitioner='{0}'".format(practitioner)
	if service_unit:
		query += " and pa.service_unit='{0}'".format(service_unit)
	if appointment_type:
		query += " and pa.appointment_type='{0}'".format(appointment_type)

	status_str = False
	if statuses:
		for status in statuses:
			status = status.strip()
			if status:
				if not status_str:
					status_str = "(pa.status = '{0}'".format(status)
				else:
					status_str += "or pa.status = '{0}'".format(status)
	if status_str:
		status_str += ")"
		query += " and {0}".format(status_str)
	else:
		query += " and pa.status != 'Cancelled'"

	query += " order by pa.appointment_date desc, pa.appointment_time, pa.status"

	appointment_list = frappe.db.sql(query, as_dict=1)

	if appointment_list:
		from operator import itemgetter

		# Patients in list
		patients = tuple(map(itemgetter("patient"), appointment_list))
		if len(patients) == 1:
			patients = ", ".join('("{0}")'.format(patient) for patient in patients)
		patient_comment_list = []
		if patients:
			query1 = """
			select content, owner, modified, reference_name
			from
				`tabComment`
			where
				"""
			query1 += "comment_type='Comment' and reference_name in {0}".format(patients)
			patient_comment_list = frappe.db.sql(query1, as_dict=1)
		# Appoinment name in list
		appointment_names = tuple(map(itemgetter("name"), appointment_list))
		if len(appointment_names) == 1:
			appointment_names = ", ".join(
				'("{0}")'.format(appointment) for appointment in appointment_names
			)
		patient_appointment_comment_list = []
		if appointment_names:
			query2 = """
			select content, owner, modified, reference_name
			from
				`tabComment`
			where
				"""
			query2 += "comment_type='Comment' and reference_name in {0}".format(appointment_names)
			patient_appointment_comment_list = frappe.db.sql(query2, as_dict=1)
	# iteration
	for app in appointment_list:

		payment = _("Not Invoiced")
		if app.invoiced and app.invoice_status:
			payment = app.invoice_status
		app["payment"] = payment

		# Patient Comments
		app["content"] = ""
		app["owner"] = ""
		app["modified"] = ""
		if patient_comment_list:
			dict_patient = list(filter(lambda x: x["reference_name"] == app.patient, patient_comment_list))
			if dict_patient:
				app["content"] = dict_patient[0]["content"]
				app["owner"] = dict_patient[0]["owner"]
				app["modified"] = getdate(dict_patient[0]["modified"])
		# Patient Appoinment Comments
		app["app_content"] = ""
		app["app_owner"] = ""
		app["app_modified"] = ""
		if patient_appointment_comment_list:
			dict_app = list(
				filter(lambda x: x["reference_name"] == app.name, patient_appointment_comment_list)
			)
			if dict_app:
				app["app_content"] = dict_app[0]["content"]
				app["app_owner"] = dict_app[0]["owner"]
				app["app_modified"] = getdate(dict_app[0]["modified"])

		app["practitioner_filter"] = True if practitioner else False
		app["date_filter"] = True if date else False
		app["patient_filter"] = True if patient else False
		app["service_unit_filter"] = True if service_unit else False
		app["appointment_type_filter"] = True if appointment_type else False
		# app['show_mca_payment_status'] = True if mca_payment_status else False
		# app['show_covid_test_passed'] = True if covid_test_passed else False
		# app['show_plan_of_care'] = True if plan_of_care else False
		app["show_patient_confirmed"] = True if patient_confirmed else False
	return appointment_list


@frappe.whitelist()
def create_encounter(appointment):
	appointment = frappe.get_doc("Patient Appointment", appointment)
	encounter = frappe.new_doc("Patient Encounter")
	encounter.appointment = appointment.name
	encounter.patient = appointment.patient
	encounter.practitioner = appointment.practitioner
	encounter.visit_department = appointment.department
	encounter.patient_sex = appointment.patient_sex
	encounter.patient_age = frappe.get_doc("Patient", appointment.patient).get_age()
	encounter.source = appointment.get("source")
	if appointment.get("source") and appointment.get("source") != "Direct":
		encounter.referring_practitioner = appointment.referring_practitioner
	encounter.encounter_date = appointment.appointment_date
	return encounter.as_dict()


@frappe.whitelist()
def update_encounter(appointment):
	encounter = get_doc_for_appointment("Patient Encounter", appointment)
	return encounter.as_dict() if encounter else False


@frappe.whitelist()
def create_procedure(appointment):
	appointment = frappe.get_doc("Patient Appointment", appointment)
	procedure = frappe.new_doc("Clinical Procedure")
	procedure.appointment = appointment.name
	procedure.patient = appointment.patient
	procedure.patient_age = appointment.patient_age
	procedure.patient_sex = appointment.patient_sex
	procedure.procedure_template = appointment.procedure_template
	procedure.prescription = appointment.procedure_prescription
	procedure.practitioner = appointment.practitioner
	procedure.invoiced = appointment.invoiced
	procedure.medical_department = appointment.department
	procedure.start_date = appointment.appointment_date
	procedure.start_time = appointment.appointment_time
	procedure.notes = appointment.notes
	procedure.service_unit = appointment.service_unit
	procedure.company = appointment.company
	procedure.source = appointment.source
	if appointment.source and appointment.source != "Direct":
		procedure.referring_practitioner = appointment.referring_practitioner
	consume_stock = frappe.db.get_value(
		"Clinical Procedure Template", appointment.procedure_template, "consume_stock"
	)
	if consume_stock == 1:
		procedure.consume_stock = True
		warehouse = False
		if appointment.service_unit:
			warehouse = frappe.db.get_value(
				"Healthcare Service Unit", appointment.service_unit, "warehouse"
			)
		if not warehouse:
			warehouse = frappe.db.get_value("Stock Settings", None, "default_warehouse")
		if warehouse:
			procedure.warehouse = warehouse
	return procedure.as_dict()


@frappe.whitelist()
def update_procedure(appointment):
	procedure = get_doc_for_appointment("Clinical Procedure", appointment)
	return procedure.as_dict() if procedure else False


@frappe.whitelist()
def reschedule_appointment(appointment_details, appointment_id=False):
	appointment_details = json.loads(appointment_details)
	if appointment_id:
		appointment = frappe.get_doc("Patient Appointment", appointment_id)
		for key in appointment_details:
			if key == "appointment_date":
				appointment.set(key, getdate(appointment_details[key]))
			else:
				appointment.set(key, appointment_details[key] if appointment_details[key] else "")
		# If appointment created for today set as open
		if getdate() == getdate(appointment_details["appointment_date"]):
			appointment.status = "Open"
		else:
			appointment.status = "Scheduled"
		appointment.save()
	else:
		from healthcare.healthcare.utils import book_appointment_from_desk

		book_appointment_from_desk(appointment_details)


@frappe.whitelist()
def cancel_reason_appointment(
	appointment_id, cancellation_source, cancelled_by, cancellation_notes
):
	appointment = frappe.get_doc("Patient Appointment", appointment_id)
	appointment.cancellation_source = cancellation_source
	# appointment.cancellation_reason = cancellation_reason
	appointment.cancelled_by = cancelled_by
	appointment.cancellation_notes = cancellation_notes
	appointment.save()


@frappe.whitelist()
def invoice_appointment(appointment_id):
	if not appointment_id:
		return False
	doc = frappe.get_doc("Patient Appointment", appointment_id)
	if doc.invoiced == 1:
		frappe.msgprint("Appoinment is already Invoiced")
	# else:
	# 	sales_invoice = set_invoice_details_for_appointment(doc, False)
	# 	if sales_invoice:
	# from healthcare.healthcare.healthcare_service_to_invoice import set_include_package_in_auto_invoice
	# sales_invoice = set_include_package_in_auto_invoice(doc, sales_invoice)
	# from healthcare.healthcare.utils import set_revenue_distributions_in_invoice
	# sales_invoice = set_revenue_distributions_in_invoice(sales_invoice)
	# return sales_invoice
	return False


@frappe.whitelist()
def view_invoice(appointment_id):
	if not appointment_id:
		return False
	sales_invoice = get_sales_invoice_for_healthcare_doc("Patient Appointment", appointment_id)
	return sales_invoice if sales_invoice else False


@frappe.whitelist()
def update_mca_payment_status(appointment_id, action):
	appointment = frappe.get_doc("Patient Appointment", appointment_id)
	if action == "Add":
		appointment.mca_payment_status = 1
	if action == "Remove":
		appointment.mca_payment_status = 0
	appointment.save()


@frappe.whitelist()
def update_covid_test_status(appointment_id, action):
	appointment = frappe.get_doc("Patient Appointment", appointment_id)
	if action == "Check":
		appointment.covid_test_passed = 1
	if action == "Uncheck":
		appointment.covid_test_passed = 0
	appointment.save()


@frappe.whitelist()
def update_patient_confirmed(appointment_id, action):
	appointment = frappe.get_doc("Patient Appointment", appointment_id)
	if action == "Check":
		appointment.patient_confirmed = 1
	if action == "Uncheck":
		appointment.patient_confirmed = 0
	appointment.save()
