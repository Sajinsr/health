from __future__ import unicode_literals

import datetime
import json
import math

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, rounded, time_diff_in_hours

from erpnext.controllers.accounts_controller import get_taxes_and_charges
from erpnext.healthcare.doctype.healthcare_settings.healthcare_settings import get_income_account
from erpnext.healthcare.utils import (
	check_insurance_approval_on_item,
	get_insurance_details,
	get_procedure_delivery_item,
	get_sales_invoice_for_healthcare_doc,
	item_reduce_procedure_rate,
	service_item_and_practitioner_charge,
	set_if_multiple_insurance_assignments_prsent,
	validity_exists,
)


@frappe.whitelist()
def get_healthcare_services_to_invoice(
	patient, posting_date, validate_insurance_on_invoice=False, insurance=None
):
	patient = frappe.get_doc("Patient", patient)
	posting_date = getdate(posting_date)
	if patient:
		include_in_insurance = True if insurance else False
		multiple_assignments_prsent = False
		prev_assignment = False
		filters = {"patient": patient.name, "invoiced": False, "docstatus": 1}
		if patient.customer:
			item_to_invoice = []
			package_cs = {}
			patient_appointments = frappe.get_list(
				"Patient Appointment",
				{"patient": patient.name, "invoiced": False, "status": ["!=", "Cancelled"]},
				order_by="appointment_date",
			)
			if patient_appointments:
				fee_validity_details = []
				valid_days = frappe.db.get_value("Healthcare Settings", None, "valid_days")
				max_visit = frappe.db.get_value("Healthcare Settings", None, "max_visit")
				for patient_appointment in patient_appointments:
					include_in_package = False
					cost_center = False
					patient_appointment_obj = frappe.get_doc("Patient Appointment", patient_appointment["name"])
					if patient_appointment_obj.schc_package_assignment:
						include_in_package = True
					if patient_appointment_obj.service_unit:
						cost_center = frappe.db.get_value(
							"Healthcare Service Unit", patient_appointment_obj.service_unit, "cost_center"
						)
					if patient_appointment_obj.procedure_template:
						if (
							frappe.db.get_value(
								"Clinical Procedure Template", patient_appointment_obj.procedure_template, "is_billable"
							)
							== 1
						):
							app_service_item = frappe.db.get_value(
								"Clinical Procedure Template", patient_appointment_obj.procedure_template, "item"
							)
							service_item_name = frappe.db.get_value("Item", app_service_item, "item_name")
							app_procedure_rate = False
							insurance_details = False
							approved_qty = False
							insurance_approval = False
							if include_in_package and valid_package(
								patient_appointment_obj.schc_package_assignment, patient_appointment_obj.appointment_date
							):
								package_service_item = get_package_service_item(patient_appointment_obj)
								if package_service_item:
									app_service_item = package_service_item
									service_item_name = frappe.db.get_value("Item", app_service_item, "item_name")
								app_procedure_rate, discount_percentage = get_package_item_charge(
									patient_appointment_obj.schc_package_assignment, app_service_item, package_cs
								)
							elif include_in_insurance and patient_appointment_obj.insurance:
								valid_date = (
									patient_appointment_obj.appointment_date
									if validate_insurance_on_invoice == "1"
									else posting_date
								)
								is_insurance_approval = frappe.get_value(
									"Insurance Company",
									(
										frappe.get_value(
											"Insurance Assignment", patient_appointment_obj.insurance, "insurance_company"
										)
									),
									"is_insurance_approval",
								)
								if is_insurance_approval:
									approved_qty, insurance_approval = check_insurance_approval_on_item(
										patient_appointment_obj.name, app_service_item, posting_date
									)
									if approved_qty:
										insurance_details = get_insurance_details(
											patient_appointment_obj.insurance, app_service_item, patient, valid_date
										)
								else:
									insurance_details = get_insurance_details(
										patient_appointment_obj.insurance, app_service_item, patient, valid_date
									)
							if include_in_package and app_procedure_rate:
								item_to_invoice.append(
									{
										"reference_dt": "Patient Appointment",
										"reference_dn": patient_appointment_obj.name,
										"item_name": service_item_name,
										"item_code": app_service_item,
										"rate": app_procedure_rate,
										"discount_percentage": discount_percentage,
										"cost_center": cost_center if cost_center else "",
									}
								)
							elif include_in_insurance and insurance_details:
								invoice_item = {
									"reference_dt": "Patient Appointment",
									"reference_dn": patient_appointment_obj.name,
									"item_name": service_item_name,
									"item_code": app_service_item,
									"cost_center": cost_center if cost_center else "",
									"discount_percentage": insurance_details.discount,
									"insurance_claim_coverage": insurance_details.coverage,
									"insurance_approval_number": patient_appointment_obj.insurance_approval_number
									if patient_appointment_obj.insurance_approval_number
									else "",
								}
								if insurance_details.rate:
									invoice_item["rate"] = (insurance_details.rate,)
								if approved_qty:
									invoice_item["qty"] = (approved_qty,)
									invoice_item["insurance_approval"] = insurance_approval
								if patient_appointment_obj.insurance == insurance:
									item_to_invoice.append(invoice_item)
									(
										multiple_assignments_prsent,
										prev_assignment,
									) = set_if_multiple_insurance_assignments_prsent(
										include_in_insurance,
										patient_appointment_obj,
										prev_assignment,
										multiple_assignments_prsent,
									)
							else:
								item_to_invoice.append(
									{
										"reference_dt": "Patient Appointment",
										"reference_dn": patient_appointment_obj.name,
										"item_name": service_item_name,
										"item_code": app_service_item,
										"cost_center": cost_center if cost_center else "",
									}
								)
								(
									multiple_assignments_prsent,
									prev_assignment,
								) = set_if_multiple_insurance_assignments_prsent(
									include_in_insurance,
									patient_appointment_obj,
									prev_assignment,
									multiple_assignments_prsent,
								)
					elif patient_appointment_obj.radiology_procedure:
						if (
							frappe.db.get_value(
								"Radiology Procedure", patient_appointment_obj.radiology_procedure, "is_billable"
							)
							== 1
						):
							app_service_item = frappe.db.get_value(
								"Radiology Procedure", patient_appointment_obj.radiology_procedure, "item"
							)
							service_item_name = frappe.db.get_value("Item", app_service_item, "item_name")
							app_procedure_rate = False
							insurance_details = False
							approved_qty = False
							insurance_approval = False
							if include_in_package and valid_package(
								patient_appointment_obj.schc_package_assignment, patient_appointment_obj.appointment_date
							):
								package_service_item = get_package_service_item(patient_appointment_obj)
								if package_service_item:
									app_service_item = package_service_item
									service_item_name = frappe.db.get_value("Item", app_service_item, "item_name")
								app_procedure_rate, discount_percentage = get_package_item_charge(
									patient_appointment_obj.schc_package_assignment, app_service_item, package_cs
								)
							elif include_in_insurance and patient_appointment_obj.insurance:
								valid_date = (
									patient_appointment_obj.appointment_date
									if validate_insurance_on_invoice == "1"
									else posting_date
								)
								is_insurance_approval = frappe.get_value(
									"Insurance Company",
									(
										frappe.get_value(
											"Insurance Assignment", patient_appointment_obj.insurance, "insurance_company"
										)
									),
									"is_insurance_approval",
								)
								if is_insurance_approval:
									approved_qty, insurance_approval = check_insurance_approval_on_item(
										patient_appointment_obj.name, app_service_item, posting_date
									)
									if approved_qty:
										insurance_details = get_insurance_details(
											patient_appointment_obj.insurance, app_service_item, patient, valid_date
										)
								else:
									insurance_details = get_insurance_details(
										patient_appointment_obj.insurance, app_service_item, patient, valid_date
									)
							if include_in_package and app_procedure_rate:
								item_to_invoice.append(
									{
										"reference_dt": "Patient Appointment",
										"reference_dn": patient_appointment_obj.name,
										"item_name": service_item_name,
										"item_code": app_service_item,
										"rate": app_procedure_rate,
										"discount_percentage": discount_percentage,
										"cost_center": cost_center if cost_center else "",
									}
								)
							elif include_in_insurance and insurance_details:
								invoice_item = {
									"reference_dt": "Patient Appointment",
									"reference_dn": patient_appointment_obj.name,
									"item_name": service_item_name,
									"item_code": app_service_item,
									"cost_center": cost_center if cost_center else "",
									"discount_percentage": insurance_details.discount,
									"insurance_claim_coverage": insurance_details.coverage,
									"insurance_approval_number": patient_appointment_obj.insurance_approval_number
									if patient_appointment_obj.insurance_approval_number
									else "",
								}
								if insurance_details.rate:
									invoice_item["rate"] = (insurance_details.rate,)
								if approved_qty:
									invoice_item["qty"] = (approved_qty,)
									invoice_item["insurance_approval"] = insurance_approval
								if patient_appointment_obj.insurance == insurance:
									item_to_invoice.append(invoice_item)
									(
										multiple_assignments_prsent,
										prev_assignment,
									) = set_if_multiple_insurance_assignments_prsent(
										include_in_insurance,
										patient_appointment_obj,
										prev_assignment,
										multiple_assignments_prsent,
									)
							else:
								item_to_invoice.append(
									{
										"reference_dt": "Patient Appointment",
										"reference_dn": patient_appointment_obj.name,
										"item_name": service_item_name,
										"item_code": app_service_item,
										"cost_center": cost_center if cost_center else "",
									}
								)
								(
									multiple_assignments_prsent,
									prev_assignment,
								) = set_if_multiple_insurance_assignments_prsent(
									include_in_insurance,
									patient_appointment_obj,
									prev_assignment,
									multiple_assignments_prsent,
								)
					else:
						practitioner_exist_in_list = False
						skip_invoice = False
						if fee_validity_details and not include_in_package:
							for validity in fee_validity_details:
								if validity["practitioner"] == patient_appointment_obj.practitioner:
									practitioner_exist_in_list = True
									if validity["valid_till"] >= patient_appointment_obj.appointment_date:
										validity["visits"] = validity["visits"] + 1
										if int(max_visit) > validity["visits"]:
											skip_invoice = True
									if not skip_invoice:
										validity["visits"] = 1
										validity["valid_till"] = (
											patient_appointment_obj.appointment_date + datetime.timedelta(days=int(valid_days))
										)
						if not practitioner_exist_in_list and not include_in_package:
							valid_till = patient_appointment_obj.appointment_date + datetime.timedelta(
								days=int(valid_days)
							)
							visits = 0
							validity_exist = validity_exists(
								patient_appointment_obj.practitioner, patient_appointment_obj.patient
							)
							if validity_exist:
								fee_validity = frappe.get_doc("Fee Validity", validity_exist[0][0])
								valid_till = fee_validity.valid_till
								visits = fee_validity.visited
							fee_validity_details.append(
								{
									"practitioner": patient_appointment_obj.practitioner,
									"valid_till": valid_till,
									"visits": visits,
								}
							)
						service_item, practitioner_charge = service_item_and_practitioner_charge(
							patient_appointment_obj
						)
						service_item_name = frappe.db.get_value("Item", service_item, "item_name")
						if (
							not include_in_package and not practitioner_charge
						):  # skip billing if charge not configured
							skip_invoice = True

						if not skip_invoice:
							income_account = None
							package_practitioner_charge = False
							if patient_appointment_obj.practitioner:
								income_account = get_income_account(
									patient_appointment_obj.practitioner, patient_appointment_obj.company
								)
							if include_in_package and valid_package(
								patient_appointment_obj.schc_package_assignment, patient_appointment_obj.appointment_date
							):
								package_service_item = get_package_service_item(patient_appointment_obj)
								if package_service_item:
									service_item = package_service_item
									service_item_name = frappe.db.get_value("Item", service_item, "item_name")
								package_practitioner_charge, discount_percentage = get_package_item_charge(
									patient_appointment_obj.schc_package_assignment, service_item, package_cs
								)
							insurance_details = False
							if include_in_insurance and patient_appointment_obj.insurance:
								valid_date = (
									patient_appointment_obj.appointment_date
									if validate_insurance_on_invoice == "1"
									else posting_date
								)
								insurance_details = get_insurance_details(
									patient_appointment_obj.insurance, service_item, patient, valid_date
								)
							if include_in_package and package_practitioner_charge:
								item_to_invoice.append(
									{
										"reference_dt": "Patient Appointment",
										"reference_dn": patient_appointment_obj.name,
										"item_code": service_item,
										"rate": package_practitioner_charge,
										"income_account": income_account,
										"item_name": service_item_name,
										"discount_percentage": discount_percentage,
										"cost_center": cost_center if cost_center else "",
									}
								)
							elif include_in_insurance and insurance_details:
								if insurance_details.rate:
									practitioner_charge = insurance_details.rate
								if patient_appointment_obj.insurance == insurance:
									item_to_invoice.append(
										{
											"reference_dt": "Patient Appointment",
											"reference_dn": patient_appointment_obj.name,
											"item_name": service_item_name,
											"item_code": service_item,
											"cost_center": cost_center if cost_center else "",
											"rate": practitioner_charge,
											"income_account": income_account,
											"discount_percentage": insurance_details.discount,
											"insurance_claim_coverage": insurance_details.coverage,
											"insurance_approval_number": patient_appointment_obj.insurance_approval_number
											if patient_appointment_obj.insurance_approval_number
											else "",
										}
									)
									(
										multiple_assignments_prsent,
										prev_assignment,
									) = set_if_multiple_insurance_assignments_prsent(
										include_in_insurance,
										patient_appointment_obj,
										prev_assignment,
										multiple_assignments_prsent,
									)
							else:
								item_to_invoice.append(
									{
										"reference_dt": "Patient Appointment",
										"reference_dn": patient_appointment_obj.name,
										"item_name": service_item_name,
										"item_code": service_item,
										"rate": practitioner_charge,
										"income_account": income_account,
										"cost_center": cost_center if cost_center else "",
									}
								)
								(
									multiple_assignments_prsent,
									prev_assignment,
								) = set_if_multiple_insurance_assignments_prsent(
									include_in_insurance,
									patient_appointment_obj,
									prev_assignment,
									multiple_assignments_prsent,
								)

			encounters = frappe.get_list("Patient Encounter", filters)
			if encounters:
				for encounter in encounters:
					cost_center = False
					encounter_obj = frappe.get_doc("Patient Encounter", encounter["name"])
					if encounter_obj.service_unit:
						cost_center = frappe.db.get_value(
							"Healthcare Service Unit", encounter_obj.service_unit, "cost_center"
						)
					if not encounter_obj.appointment:
						practitioner_charge = 0
						income_account = None
						service_item = None
						discount_percentage = 0
						if encounter_obj.practitioner:
							service_item, practitioner_charge = service_item_and_practitioner_charge(encounter_obj)
							service_item_name = frappe.db.get_value("Item", service_item, "item_name")
							if not practitioner_charge:  # skip billing if charge not configured
								continue
							income_account = get_income_account(encounter_obj.practitioner, encounter_obj.company)
						insurance_details = False
						approved_qty = False
						insurance_approval = False
						if include_in_insurance and encounter_obj.insurance:
							valid_date = (
								encounter_obj.encounter_date if validate_insurance_on_invoice == "1" else posting_date
							)
							is_insurance_approval = frappe.get_value(
								"Insurance Company",
								(frappe.get_value("Insurance Assignment", encounter_obj.insurance, "insurance_company")),
								"is_insurance_approval",
							)
							if is_insurance_approval:
								approved_qty, insurance_approval = check_insurance_approval_on_item(
									encounter_obj.name, service_item, posting_date
								)
								if approved_qty:
									insurance_details = get_insurance_details(
										encounter_obj.insurance, service_item, patient, valid_date
									)
							else:
								insurance_details = get_insurance_details(
									encounter_obj.insurance, service_item, patient, valid_date
								)
						if include_in_insurance and insurance_details:
							if insurance_details.rate:
								practitioner_charge = insurance_details.rate
							invoice_item = {
								"reference_dt": "Patient Encounter",
								"reference_dn": encounter_obj.name,
								"item_name": service_item_name,
								"item_code": service_item,
								"rate": practitioner_charge,
								"cost_center": cost_center if cost_center else "",
								"discount_percentage": insurance_details.discount,
								"insurance_claim_coverage": insurance_details.coverage,
								"insurance_approval_number": encounter_obj.insurance_approval_number
								if encounter_obj.insurance_approval_number
								else "",
							}
							if approved_qty:
								invoice_item["qty"] = (approved_qty,)
								invoice_item["insurance_approval"] = insurance_approval
							if encounter_obj.insurance == insurance:
								item_to_invoice.append(invoice_item)
								(
									multiple_assignments_prsent,
									prev_assignment,
								) = set_if_multiple_insurance_assignments_prsent(
									include_in_insurance, encounter_obj, prev_assignment, multiple_assignments_prsent
								)
						else:
							item_to_invoice.append(
								{
									"reference_dt": "Patient Encounter",
									"reference_dn": encounter_obj.name,
									"item_name": service_item_name,
									"item_code": service_item,
									"rate": practitioner_charge,
									"cost_center": cost_center if cost_center else "",
									"income_account": income_account,
								}
							)
							multiple_assignments_prsent, prev_assignment = set_if_multiple_insurance_assignments_prsent(
								include_in_insurance, encounter_obj, prev_assignment, multiple_assignments_prsent
							)

			lab_tests = frappe.get_list("Lab Test", filters)
			if lab_tests:
				for lab_test in lab_tests:
					cost_center = False
					lab_test_obj = frappe.get_doc("Lab Test", lab_test["name"])
					if lab_test_obj.service_unit:
						cost_center = frappe.db.get_value(
							"Healthcare Service Unit", lab_test_obj.service_unit, "cost_center"
						)
					insurance_details = False
					approved_qty = False
					insurance_approval = False
					if include_in_insurance and lab_test_obj.insurance:
						valid_date = (
							lab_test_obj.submitted_date if validate_insurance_on_invoice == "1" else posting_date
						)
						is_insurance_approval = frappe.get_value(
							"Insurance Company",
							(frappe.get_value("Insurance Assignment", lab_test_obj.insurance, "insurance_company")),
							"is_insurance_approval",
						)
						if is_insurance_approval:
							approved_qty, insurance_approval = check_insurance_approval_on_item(
								lab_test_obj.name,
								frappe.db.get_value("Lab Test Template", lab_test_obj.template, "item"),
								posting_date,
							)
							if approved_qty:
								insurance_details = get_insurance_details(
									lab_test_obj.insurance,
									frappe.db.get_value("Lab Test Template", lab_test_obj.template, "item"),
									patient,
									valid_date,
								)
						else:
							insurance_details = get_insurance_details(
								lab_test_obj.insurance,
								frappe.db.get_value("Lab Test Template", lab_test_obj.template, "item"),
								patient,
								valid_date,
							)
					if frappe.db.get_value("Lab Test Template", lab_test_obj.template, "is_billable") == 1:
						service_item_name = frappe.db.get_value(
							"Item", frappe.db.get_value("Lab Test Template", lab_test_obj.template, "item"), "item_name"
						)
						if include_in_insurance and insurance_details:
							invoice_item = {
								"reference_dt": "Lab Test",
								"reference_dn": lab_test_obj.name,
								"item_name": service_item_name,
								"item_code": frappe.db.get_value("Lab Test Template", lab_test_obj.template, "item"),
								"discount_percentage": insurance_details.discount,
								"cost_center": cost_center if cost_center else "",
								"insurance_claim_coverage": insurance_details.coverage,
								"insurance_approval_number": lab_test_obj.insurance_approval_number
								if lab_test_obj.insurance_approval_number
								else "",
							}
							if insurance_details.rate:
								invoice_item["rate"] = (insurance_details.rate,)
							if approved_qty:
								invoice_item["qty"] = (approved_qty,)
								invoice_item["insurance_approval"] = insurance_approval
							if lab_test_obj.insurance == insurance:
								item_to_invoice.append(invoice_item)
								(
									multiple_assignments_prsent,
									prev_assignment,
								) = set_if_multiple_insurance_assignments_prsent(
									include_in_insurance, lab_test_obj, prev_assignment, multiple_assignments_prsent
								)
						else:
							item_to_invoice.append(
								{
									"reference_dt": "Lab Test",
									"reference_dn": lab_test_obj.name,
									"item_name": service_item_name,
									"item_code": frappe.db.get_value("Lab Test Template", lab_test_obj.template, "item"),
									"cost_center": cost_center if cost_center else "",
								}
							)
							multiple_assignments_prsent, prev_assignment = set_if_multiple_insurance_assignments_prsent(
								include_in_insurance, lab_test_obj, prev_assignment, multiple_assignments_prsent
							)

			lab_rxs = frappe.db.sql(
				"""select lp.name, et.name from `tabPatient Encounter` et, `tabLab Prescription` lp
			where et.patient=%s and lp.parent=et.name and lp.lab_test_created=0 and lp.invoiced=0""",
				(patient.name),
			)
			if lab_rxs:
				for lab_rx in lab_rxs:
					cost_center = False
					rx_obj = frappe.get_doc("Lab Prescription", lab_rx[0])
					if rx_obj.parenttype == "Patient Encounter":
						rx_obj_service_unit = frappe.get_value("Patient Encounter", rx_obj.parent, "service_unit")
						if rx_obj_service_unit:
							cost_center = frappe.db.get_value(
								"Healthcare Service Unit", rx_obj_service_unit, "cost_center"
							)
					encx_obj = frappe.get_doc("Patient Encounter", lab_rx[1])
					if rx_obj.lab_test_code and (
						frappe.db.get_value("Lab Test Template", rx_obj.lab_test_code, "is_billable") == 1
					):
						service_item_name = frappe.db.get_value(
							"Item", frappe.db.get_value("Lab Test Template", rx_obj.lab_test_code, "item"), "item_name"
						)
						insurance_details = False
						approved_qty = False
						insurance_approval = False
						if include_in_insurance and encx_obj.insurance:
							valid_date = (
								encx_obj.encounter_date if validate_insurance_on_invoice == "1" else posting_date
							)
							is_insurance_approval = frappe.get_value(
								"Insurance Company",
								(frappe.get_value("Insurance Assignment", encx_obj.insurance, "insurance_company")),
								"is_insurance_approval",
							)
							if is_insurance_approval:
								approved_qty, insurance_approval = check_insurance_approval_on_item(
									encx_obj.name,
									frappe.db.get_value("Lab Test Template", rx_obj.lab_test_code, "item"),
									posting_date,
								)
								if approved_qty:
									insurance_details = get_insurance_details(
										encx_obj.insurance,
										frappe.db.get_value("Lab Test Template", rx_obj.lab_test_code, "item"),
										patient,
										valid_date,
									)
							else:
								insurance_details = get_insurance_details(
									encx_obj.insurance,
									frappe.db.get_value("Lab Test Template", rx_obj.lab_test_code, "item"),
									patient,
									valid_date,
								)
						if include_in_insurance and insurance_details:
							invoice_item = {
								"reference_dt": "Lab Prescription",
								"reference_dn": rx_obj.name,
								"item_name": service_item_name,
								"item_code": frappe.db.get_value("Lab Test Template", rx_obj.lab_test_code, "item"),
								"cost_center": cost_center if cost_center else "",
								"discount_percentage": insurance_details.discount,
								"insurance_claim_coverage": insurance_details.coverage,
								"insurance_approval_number": encx_obj.insurance_approval_number
								if encx_obj.insurance_approval_number
								else "",
							}
							if insurance_details.rate:
								invoice_item["rate"] = insurance_details.rate
							if approved_qty:
								invoice_item["qty"] = (approved_qty,)
								invoice_item["insurance_approval"] = insurance_approval
							if encx_obj.insurance == insurance:
								item_to_invoice.append(invoice_item)
								(
									multiple_assignments_prsent,
									prev_assignment,
								) = set_if_multiple_insurance_assignments_prsent(
									include_in_insurance, encx_obj, prev_assignment, multiple_assignments_prsent
								)
						else:
							item_to_invoice.append(
								{
									"reference_dt": "Lab Prescription",
									"reference_dn": rx_obj.name,
									"item_name": service_item_name,
									"item_code": frappe.db.get_value("Lab Test Template", rx_obj.lab_test_code, "item"),
									"cost_center": cost_center if cost_center else "",
								}
							)
							multiple_assignments_prsent, prev_assignment = set_if_multiple_insurance_assignments_prsent(
								include_in_insurance, encx_obj, prev_assignment, multiple_assignments_prsent
							)

			procedures = frappe.get_list(
				"Clinical Procedure",
				{"patient": patient.name, "invoiced": False, "docstatus": 1, "status": "Completed"},
			)
			if procedures:
				for procedure in procedures:
					cost_center = False
					procedure_obj = frappe.get_doc("Clinical Procedure", procedure["name"])
					if procedure_obj.service_unit:
						cost_center = frappe.db.get_value(
							"Healthcare Service Unit", procedure_obj.service_unit, "cost_center"
						)
					# if not procedure_obj.appointment:
					if procedure_obj.procedure_template and (
						frappe.db.get_value(
							"Clinical Procedure Template", procedure_obj.procedure_template, "is_billable"
						)
						== 1
					):
						reduce_from_procedure_rate = 0
						if procedure_obj.consume_stock:
							delivery_note_items = get_procedure_delivery_item(patient.name, procedure_obj.name)
							if delivery_note_items:
								for delivery_note_item in delivery_note_items:
									dn_item = frappe.get_doc("Delivery Note Item", delivery_note_item[0])
									reduce_from_procedure_rate += item_reduce_procedure_rate(dn_item, procedure_obj.items)
						procedure_service_item = frappe.db.get_value(
							"Clinical Procedure Template", procedure_obj.procedure_template, "item"
						)
						service_item_name = frappe.db.get_value("Item", procedure_service_item, "item_name")
						procedure_rate = False
						if procedure_obj.schc_package_assignment and valid_package(
							procedure_obj.schc_package_assignment, procedure_obj.start_date
						):
							package_service_item = get_package_service_item(procedure_obj)
							if package_service_item:
								procedure_service_item = package_service_item
								service_item_name = frappe.db.get_value("Item", procedure_service_item, "item_name")
							procedure_rate, discount_percentage = get_package_item_charge(
								procedure_obj.schc_package_assignment, procedure_service_item, package_cs
							)
						insurance_details = False
						approved_qty = False
						insurance_approval = False
						if include_in_insurance and procedure_obj.insurance:
							valid_date = (
								procedure_obj.start_date if validate_insurance_on_invoice == "1" else posting_date
							)
							is_insurance_approval = frappe.get_value(
								"Insurance Company",
								(frappe.get_value("Insurance Assignment", procedure_obj.insurance, "insurance_company")),
								"is_insurance_approval",
							)
							if is_insurance_approval:
								approved_qty, insurance_approval = check_insurance_approval_on_item(
									procedure_obj.name, procedure_service_item, posting_date
								)
								if approved_qty:
									insurance_details = get_insurance_details(
										procedure_obj.insurance, procedure_service_item, patient, valid_date
									)
							else:
								insurance_details = get_insurance_details(
									procedure_obj.insurance, procedure_service_item, patient, valid_date
								)
						if procedure_obj.schc_package_assignment and procedure_rate:
							item_to_invoice.append(
								{
									"reference_dt": "Clinical Procedure",
									"reference_dn": procedure_obj.name,
									"item_name": service_item_name,
									"item_code": procedure_service_item,
									"rate": procedure_rate - reduce_from_procedure_rate,
									"discount_percentage": discount_percentage,
									"cost_center": cost_center if cost_center else "",
								}
							)
						elif include_in_insurance and insurance_details:
							invoice_item = {
								"reference_dt": "Clinical Procedure",
								"reference_dn": procedure_obj.name,
								"item_name": service_item_name,
								"item_code": procedure_service_item,
								"discount_percentage": insurance_details.discount,
								"cost_center": cost_center if cost_center else "",
								"insurance_claim_coverage": insurance_details.coverage,
								"insurance_approval_number": procedure_obj.insurance_approval_number
								if procedure_obj.insurance_approval_number
								else "",
							}
							if insurance_details.rate:
								invoice_item["rate"] = insurance_details.rate - reduce_from_procedure_rate
							else:
								invoice_item["rate"] = (
									float(procedure_obj.standard_selling_rate) - reduce_from_procedure_rate
								)
							if approved_qty:
								invoice_item["qty"] = (approved_qty,)
								invoice_item["insurance_approval"] = insurance_approval
							if procedure_obj.insurance == insurance:
								item_to_invoice.append(invoice_item)
								(
									multiple_assignments_prsent,
									prev_assignment,
								) = set_if_multiple_insurance_assignments_prsent(
									include_in_insurance, procedure_obj, prev_assignment, multiple_assignments_prsent
								)
						else:
							invoice_item = {
								"reference_dt": "Clinical Procedure",
								"reference_dn": procedure_obj.name,
								"cost_center": cost_center if cost_center else "",
								"item_name": service_item_name,
								"item_code": procedure_service_item,
								"rate": float(procedure_obj.standard_selling_rate) - reduce_from_procedure_rate,
							}
							if procedure_obj.schc_patient_selling_rate and procedure_obj.schc_patient_selling_rate > 0:
								invoice_item["rate"] = (
									float(procedure_obj.schc_patient_selling_rate) - reduce_from_procedure_rate
								)
							item_to_invoice.append(invoice_item)
							multiple_assignments_prsent, prev_assignment = set_if_multiple_insurance_assignments_prsent(
								include_in_insurance, procedure_obj, prev_assignment, multiple_assignments_prsent
							)
					# Doctor's Fees for the Procedure if applicable
					if (
						procedure_obj.inpatient_record
						and procedure_obj.inpatient_record_procedure
						and procedure_obj.schc_doctor_fee
					):
						service_item_name = frappe.db.get_value(
							"Item",
							frappe.db.get_value("Healthcare Settings", None, "revenue_booking_item"),
							"item_name",
						)
						item_to_invoice.append(
							{
								"reference_dt": "Inpatient Record Procedure",
								"reference_dn": procedure_obj.inpatient_record_procedure,
								"cost_center": cost_center if cost_center else "",
								"item_name": service_item_name,
								"item_code": frappe.db.get_value("Healthcare Settings", None, "revenue_booking_item"),
								"rate": procedure_obj.schc_doctor_fee,
							}
						)

			r_procedures = frappe.get_list("Radiology Examination", filters)
			if r_procedures:
				for procedure in r_procedures:
					cost_center = False
					procedure_obj = frappe.get_doc("Radiology Examination", procedure["name"])
					if procedure_obj.service_unit:
						cost_center = frappe.db.get_value(
							"Healthcare Service Unit", procedure_obj.service_unit, "cost_center"
						)
					if not procedure_obj.appointment:
						if procedure_obj.radiology_procedure and (
							frappe.db.get_value("Radiology Procedure", procedure_obj.radiology_procedure, "is_billable")
							== 1
						):
							procedure_service_item = frappe.db.get_value(
								"Radiology Procedure", procedure_obj.radiology_procedure, "item"
							)
							service_item_name = frappe.db.get_value("Item", procedure_service_item, "item_name")
						insurance_details = False
						approved_qty = False
						insurance_approval = False
						if include_in_insurance and procedure_obj.insurance:
							valid_date = (
								procedure_obj.start_date if validate_insurance_on_invoice == "1" else posting_date
							)
							is_insurance_approval = frappe.get_value(
								"Insurance Company",
								(frappe.get_value("Insurance Assignment", procedure_obj.insurance, "insurance_company")),
								"is_insurance_approval",
							)
							if is_insurance_approval:
								approved_qty, insurance_approval = check_insurance_approval_on_item(
									procedure_obj.name, procedure_service_item, posting_date
								)
								if approved_qty:
									insurance_details = get_insurance_details(
										procedure_obj.insurance, procedure_service_item, patient, valid_date
									)
							else:
								insurance_details = get_insurance_details(
									procedure_obj.insurance, procedure_service_item, patient, valid_date
								)
						if include_in_insurance and insurance_details:
							invoice_item = {
								"reference_dt": "Radiology Examination",
								"reference_dn": procedure_obj.name,
								"item_name": service_item_name,
								"cost_center": cost_center if cost_center else "",
								"item_code": procedure_service_item,
								"discount_percentage": insurance_details.discount,
								"insurance_claim_coverage": insurance_details.coverage,
								"insurance_approval_number": procedure_obj.insurance_approval_number
								if procedure_obj.insurance_approval_number
								else "",
							}
							if insurance_details.rate:
								invoice_item["rate"] = insurance_details.rate
							if approved_qty:
								invoice_item["qty"] = (approved_qty,)
								invoice_item["insurance_approval"] = insurance_approval
							if procedure_obj.insurance == insurance:
								item_to_invoice.append(invoice_item)
								(
									multiple_assignments_prsent,
									prev_assignment,
								) = set_if_multiple_insurance_assignments_prsent(
									include_in_insurance, procedure_obj, prev_assignment, multiple_assignments_prsent
								)
						else:
							item_to_invoice.append(
								{
									"reference_dt": "Radiology Examination",
									"reference_dn": procedure_obj.name,
									"item_name": service_item_name,
									"cost_center": cost_center if cost_center else "",
									"item_code": procedure_service_item,
								}
							)
							multiple_assignments_prsent, prev_assignment = set_if_multiple_insurance_assignments_prsent(
								include_in_insurance, procedure_obj, prev_assignment, multiple_assignments_prsent
							)

			delivery_note_items = get_procedure_delivery_item(patient.name)
			if delivery_note_items:
				for delivery_note_item in delivery_note_items:
					cost_center = False
					reference_type = False
					reference_name = False
					insurance_details = False
					delivery_note = frappe.get_doc("Delivery Note", delivery_note_item[1])
					dn_item = frappe.get_doc("Delivery Note Item", delivery_note_item[0])
					if dn_item.reference_dt == "Clinical Procedure" and dn_item.reference_dn:
						service_unit = frappe.get_value("Clinical Procedure", dn_item.reference_dn, "service_unit")
						if service_unit:
							cost_center = frappe.db.get_value("Healthcare Service Unit", service_unit, "cost_center")

					if include_in_insurance and delivery_note.insurance:
						valid_date = (
							delivery_note.posting_date if validate_insurance_on_invoice == "1" else posting_date
						)
						insurance_details = get_insurance_details(
							delivery_note.insurance, dn_item.item_code, patient, valid_date
						)
					if include_in_insurance and delivery_note.insurance and insurance_details:
						invoice_item = {
							"reference_dt": "Delivery Note",
							"reference_dn": delivery_note_item[1] if delivery_note_item[1] else "",
							"item_code": dn_item.item_code,
							"rate": dn_item.rate,
							"qty": dn_item.qty,
							"item_name": dn_item.item_name,
							"cost_center": cost_center if cost_center else dn_item.cost_center,
							"delivery_note": delivery_note_item[1] if delivery_note_item[1] else "",
							"discount_percentage": insurance_details.discount,
							"insurance_claim_coverage": insurance_details.coverage,
							"insurance_approval_number": delivery_note.insurance_approval_number
							if delivery_note.insurance_approval_number
							else "",
						}
						if insurance_details.rate:
							invoice_item["rate"] = (insurance_details.rate,)
						if delivery_note.insurance == insurance:
							item_to_invoice.append(invoice_item)
							multiple_assignments_prsent, prev_assignment = set_if_multiple_insurance_assignments_prsent(
								include_in_insurance, delivery_note, prev_assignment, multiple_assignments_prsent
							)
					else:
						item_to_invoice.append(
							{
								"reference_dt": "Delivery Note",
								"reference_dn": delivery_note_item[1] if delivery_note_item[1] else "",
								"item_code": dn_item.item_code,
								"rate": dn_item.rate,
								"qty": dn_item.qty,
								"item_name": dn_item.item_name,
								"cost_center": cost_center if cost_center else dn_item.cost_center,
								"delivery_note": delivery_note_item[1] if delivery_note_item[1] else "",
							}
						)
						multiple_assignments_prsent, prev_assignment = set_if_multiple_insurance_assignments_prsent(
							include_in_insurance, delivery_note, prev_assignment, multiple_assignments_prsent
						)

			inpatient_services = frappe.db.sql(
				"""select io.name, io.parent from `tabInpatient Record` ip,
			`tabInpatient Occupancy` io where ip.patient=%s and io.parent=ip.name and
			io.left=1 and io.invoiced=0""",
				(patient.name),
			)
			if inpatient_services:
				for inpatient_service in inpatient_services:
					inpatient_occupancy = frappe.get_doc("Inpatient Occupancy", inpatient_service[0])
					inpatient_record = frappe.get_doc("Inpatient Record", inpatient_service[1])
					service_unit_type = frappe.get_doc(
						"Healthcare Service Unit Type",
						frappe.db.get_value(
							"Healthcare Service Unit", inpatient_occupancy.service_unit, "service_unit_type"
						),
					)
					service_unit_type_item_name = frappe.db.get_value("Item", service_unit_type.item, "item_name")
					if service_unit_type and service_unit_type.is_billable == 1:
						hours_occupied = time_diff_in_hours(
							inpatient_occupancy.check_out, inpatient_occupancy.check_in
						)
						qty = 0.5
						if hours_occupied > 0:
							if service_unit_type.no_of_hours and service_unit_type.no_of_hours > 0:
								actual_qty = hours_occupied / service_unit_type.no_of_hours
							else:
								# 24 hours = 1 Day
								actual_qty = hours_occupied / 24
							floor = math.floor(actual_qty)
							decimal_part = actual_qty - floor
							if decimal_part > 0.5:
								qty = rounded(floor + 1, 1)
							elif decimal_part < 0.5 and decimal_part > 0:
								qty = rounded(floor + 0.5, 1)
							if qty <= 0:
								qty = 0.5
						cost_center = False
						if inpatient_occupancy.service_unit:
							cost_center = frappe.db.get_value(
								"Healthcare Service Unit", inpatient_occupancy.service_unit, "cost_center"
							)
						service_item_rate = False
						insurance_details = False
						if include_in_insurance and inpatient_record.insurance:
							valid_date = (
								inpatient_record.scheduled_date if validate_insurance_on_invoice == "1" else posting_date
							)
							insurance_details = get_insurance_details(
								inpatient_record.insurance, service_unit_type.item, patient, valid_date
							)
						if include_in_insurance and insurance_details:
							invoice_item = {
								"reference_dt": "Inpatient Occupancy",
								"reference_dn": inpatient_occupancy.name,
								"item_name": service_unit_type_item_name,
								"item_code": service_unit_type.item,
								"cost_center": cost_center if cost_center else "",
								"qty": qty,
								"discount_percentage": insurance_details.discount,
								"insurance_claim_coverage": insurance_details.coverage,
								"insurance_approval_number": inpatient_record.insurance_approval_number
								if inpatient_record.insurance_approval_number
								else "",
							}
							if insurance_details.rate:
								invoice_item["rate"] = insurance_details.rate
							if inpatient_record.insurance == insurance:
								item_to_invoice.append(invoice_item)
								(
									multiple_assignments_prsent,
									prev_assignment,
								) = set_if_multiple_insurance_assignments_prsent(
									include_in_insurance, inpatient_record, prev_assignment, multiple_assignments_prsent
								)
						else:
							item_to_invoice.append(
								{
									"reference_dt": "Inpatient Occupancy",
									"reference_dn": inpatient_occupancy.name,
									"item_name": service_unit_type_item_name,
									"item_code": service_unit_type.item,
									"cost_center": cost_center if cost_center else "",
									"qty": qty,
								}
							)
							multiple_assignments_prsent, prev_assignment = set_if_multiple_insurance_assignments_prsent(
								include_in_insurance, inpatient_record, prev_assignment, multiple_assignments_prsent
							)
			return item_to_invoice, multiple_assignments_prsent
		else:
			frappe.throw(_("The Patient {0} do not have customer refrence to invoice").format(patient.name))


@frappe.whitelist()
def get_item_to_invoice(encounter, posting_date, validate_insurance_on_invoice=False):
	encounter = frappe.get_doc("Patient Encounter", encounter)
	if encounter:
		patient = frappe.get_doc("Patient", encounter.patient)
		if patient and patient.customer:
			item_to_invoice = []
			for item_line in encounter.item_prescription:
				if item_line.item_code:
					item_name = frappe.db.get_value("Item", item_line.item_code, "item_name")
					quantity = item_line.quantity
					insurance_details = False
					approved_qty = False
					insurance_approval = False
					if encounter.insurance:
						valid_date = (
							encounter.encounter_date if validate_insurance_on_invoice == "1" else posting_date
						)
						is_insurance_approval = frappe.get_value(
							"Insurance Company",
							(frappe.get_value("Insurance Assignment", encounter.insurance, "insurance_company")),
							"is_insurance_approval",
						)
						if is_insurance_approval:
							approved_qty, insurance_approval = check_insurance_approval_on_item(
								encounter.name, item_line.item_code, posting_date
							)
							if approved_qty:
								insurance_details = get_insurance_details(
									encounter.insurance, item_line.item_code, patient, valid_date
								)
						else:
							insurance_details = get_insurance_details(
								encounter.insurance, item_line.item_code, patient, valid_date
							)
					if insurance_details:
						quantity = approved_qty if approved_qty else quantity
						invoice_item = {
							"reference_dt": "Item Prescription",
							"reference_dn": item_line.name,
							"item_name": item_name,
							"item_code": item_line.item_code,
							"qty": quantity,
							"description": item_line.comment,
							"discount_percentage": insurance_details.discount,
							"insurance_claim_coverage": insurance_details.coverage,
							"insurance_approval_number": encounter.insurance_approval_number
							if encounter.insurance_approval_number
							else "",
						}
						if insurance_details.rate:
							invoice_item["rate"] = insurance_details.rate
						if insurance_approval:
							invoice_item["insurance_approval"] = insurance_approval
						item_to_invoice.append(invoice_item)
					else:
						item_to_invoice.append(
							{
								"reference_dt": "Item Prescription",
								"reference_dn": item_line.name,
								"item_name": item_name,
								"item_code": item_line.item_code,
								"qty": quantity,
							}
						)
			return item_to_invoice, False


def get_package_item_charge(package, service_item, package_cs):
	healthcare_package = frappe.get_doc("Healthcare Package Assignment", package)
	for item in healthcare_package.items:
		if service_item == item.item_code and item.no_of_session > item.completed_session:
			package_item_cs = {}
			if package in package_cs:
				if service_item in package_cs[package]:
					package_cs[package][service_item] += 1
				else:
					package_cs[package][service_item] = item.completed_session + 1
			else:
				package_item_cs[service_item] = item.completed_session + 1
				package_cs[package] = package_item_cs
			if package_cs[package][service_item] <= item.no_of_session:
				return (item.session_amount / item.no_of_session), item.discount_percentage
	return False, False


def valid_package(package, posting_date):
	return frappe.db.exists(
		"Healthcare Package Assignment",
		{
			"name": package,
			"from_date": ("<=", getdate(posting_date)),
			# 'to_date':(">=", getdate(posting_date)),
			"docstatus": 1,
		},
	)


def manage_package_session(doc, method):
	package_cs = {}
	jv_amount = {}
	posting_date = doc.posting_date
	if doc.items:
		reference_doctypes = ["Patient Appointment", "Clinical Procedure"]
		for item in doc.items:
			if item.reference_dt in reference_doctypes:
				package = frappe.db.get_value(item.reference_dt, item.reference_dn, "schc_package_assignment")
				if item.reference_dt == "Patient Appointment":
					posting_date = frappe.db.get_value(item.reference_dt, item.reference_dn, "appointment_date")
				elif item.reference_dt == "Clinical Procedure":
					posting_date = frappe.db.get_value(item.reference_dt, item.reference_dn, "start_date")
				if package and valid_package(package, posting_date):
					session_rate, discount = get_package_item_charge(package, item.item_code, package_cs)
					amount = session_rate - (session_rate * 0.01 * discount)
					if amount:
						if package in jv_amount:
							jv_amount[package] += amount
						else:
							jv_amount[package] = amount
					package_obj = frappe.get_doc("Healthcare Package Assignment", package)
					for pack_item in package_obj.items:
						if pack_item.item_code == item.item_code:
							if method == "on_submit" and pack_item.no_of_session > pack_item.completed_session:
								pack_item.completed_session += 1
							elif method == "on_cancel" and pack_item.completed_session > 0:
								pack_item.completed_session -= 1
					package_obj.save()
		if jv_amount and method == "on_submit":
			for key in jv_amount:
				create_journal_entry_transfer(
					frappe.get_doc("Healthcare Package Assignment", key), jv_amount[key], doc
				)

	doc.reload()


def create_journal_entry_transfer(package, amount, doc):
	from erpnext.accounts.party import get_party_account

	journal_entry = frappe.new_doc("Journal Entry")
	journal_entry.voucher_type = "Journal Entry"
	journal_entry.naming_series = package.journal_voucher_series
	journal_entry.company = package.company
	journal_entry.posting_date = doc.posting_date
	accounts = []
	tax_amount = 0.0
	if doc.taxes:
		for tax in doc.taxes:
			tax_amount += tax.tax_amount
	accounts.append(
		{
			"account": get_party_account("Customer", doc.customer, doc.company),
			"credit_in_account_currency": amount + tax_amount,
			"party_type": "Customer",
			"party": doc.customer,
			"reference_type": doc.doctype,
			"reference_name": doc.name,
		}
	)
	accounts.append(
		{"account": package.package_advance, "debit_in_account_currency": amount + tax_amount}
	)
	# if doc.taxes:
	# 	for tax in doc.taxes:
	# 		accounts.append({
	# 			"account": tax.account_head,
	# 			"debit_in_account_currency": tax.tax_amount
	# 		})
	journal_entry.set("accounts", accounts)
	journal_entry.save(ignore_permissions=True)
	journal_entry.submit()
	for package_tax in package.taxes:
		if not package_tax.sales_invoice_tax_amount:
			package_tax.sales_invoice_tax_amount = 0
		for invoice_tax in doc.taxes:
			if package_tax.account_head == invoice_tax.account_head:
				package_tax.sales_invoice_tax_amount += invoice_tax.tax_amount
	package.save(ignore_permissions=True)


@frappe.whitelist()
def cancel_je_for_package(doc, method):
	if doc.items:
		for item in doc.items:
			prescription_dt = [
				"Inpatient Record Procedure",
				"Inpatient Occupancy",
				"Lab Prescription",
				"Procedure Prescription",
				"Radiology Procedure Prescription",
				"Drug Prescription",
				"Item Prescription",
			]
			if (
				item.reference_dn
				and frappe.get_meta(item.reference_dt).has_field("schc_package_assignment")
				and item.reference_dt not in prescription_dt
			):
				service = frappe.get_doc(item.reference_dt, item.reference_dn)
				if service.schc_package_assignment:
					journal_entries = frappe.db.sql(
						"""select parent from `tabJournal Entry Account`
								where reference_type ="Sales Invoice" and  reference_name= %s
								""",
						(doc.name),
						as_dict=True,
					)
					if journal_entries and journal_entries[0]:
						jv = frappe.get_doc("Journal Entry", journal_entries[0].parent)
						if jv.docstatus == 1:
							jv.cancel()


@frappe.whitelist()
def include_package_in_auto_invoice(doc):
	if doc.invoiced != 1 and not doc.insurance:
		if frappe.get_meta(doc.doctype).has_field("schc_package_assignment") and doc.get(
			"schc_package_assignment"
		):
			sales_invoice = get_sales_invoice_for_healthcare_doc(doc.doctype, doc.name)
			if sales_invoice:
				sales_invoice = set_include_package_in_auto_invoice(doc, sales_invoice)
				sales_invoice.save(ignore_permissions=True)


def set_include_package_in_auto_invoice(doc, sales_invoice):
	posting_date = sales_invoice.posting_date
	package_cs = {}
	if (
		sales_invoice
		and sales_invoice.items
		and sales_invoice.docstatus < 1
		and sales_invoice.items[0].reference_dt == doc.doctype
		and sales_invoice.items[0].reference_dn == doc.name
	):
		if doc.doctype == "Patient Appointment":
			posting_date = frappe.db.get_value(doc.doctype, doc.name, "appointment_date")
		elif doc.doctype == "Clinical Procedure":
			posting_date = frappe.db.get_value(doc.doctype, doc.name, "start_date")
		if valid_package(doc.schc_package_assignment, sales_invoice.posting_date):
			service_item = get_package_service_item(doc)
			if not service_item:
				service_item = get_service_item_for_healthcare_doc(doc)
			if service_item:
				rate, discount_percentage = get_package_item_charge(
					doc.schc_package_assignment, service_item, package_cs
				)
				if rate:
					sales_invoice.items[0].item_code = service_item
					sales_invoice.items[0].item_name = frappe.db.get_value("Item", service_item, "item_name")
					if sales_invoice.selling_price_list:
						sales_invoice.items[0].price_list_rate = frappe.db.get_value(
							"Item Price",
							{"item_code": service_item, "price_list": sales_invoice.selling_price_list},
							"price_list_rate",
						)
					sales_invoice.items[0].rate = float(rate)
					if discount_percentage and float(discount_percentage) > 0:
						sales_invoice.items[0].discount_percentage = float(discount_percentage)
						sales_invoice.items[0].discount_amount = float(rate) * float(discount_percentage) * 0.01
						sales_invoice.items[0].rate = float(sales_invoice.items[0].rate) - float(
							sales_invoice.items[0].discount_amount
						)
					sales_invoice.items[0].amount = float(sales_invoice.items[0].rate) * float(
						sales_invoice.items[0].qty
					)
		# set taxes
		from healthcare.healthcare.doctype.healthcare_package_assignment.healthcare_package_assignment import (
			get_patient_taxes_and_charges,
		)

		taxes_and_charges_template = get_patient_taxes_and_charges(doc.patient, doc.company, date=None)
		if taxes_and_charges_template:
			taxes_and_charges = get_taxes_and_charges(
				"Sales Taxes and Charges Template", taxes_and_charges_template
			)
			taxes = []
			if taxes_and_charges:
				for tax in taxes_and_charges:
					taxes.append(
						{
							"charge_type": tax.charge_type,
							"account_head": tax.account_head,
							"description": tax.description,
							"included_in_print_rate": tax.included_in_print_rate,
							"rate": tax.rate,
						}
					)
				sales_invoice.set("taxes", taxes)
			sales_invoice.taxes_and_charges = taxes_and_charges_template
		sales_invoice.set_missing_values(for_validate=True)
	return sales_invoice


def get_package_service_item(doc):
	if frappe.get_meta(doc.doctype).has_field("schc_package_item") and doc.schc_package_item:
		return doc.schc_package_item
	return False


def get_service_item_for_healthcare_doc(doc):
	hc_doctypes = [
		"Patient Appointment",
		"Clinical Procedure",
		"Radiology Examination",
		"Lab Test",
		"Lab Prescription",
		"Inpatient Occupancy",
		"Patient Encounter",
	]
	field_doctype = {
		"procedure_template": "Clinical Procedure Template",
		"radiology_procedure": "Radiology Procedure",
		"template": "Lab Test Template",
	}
	if doc.doctype in hc_doctypes:
		for field in field_doctype:
			if frappe.get_meta(doc.doctype).has_field(field) and doc.get(field):
				return get_billable_service_item(field_doctype[field], doc.get(field))
		if doc.doctype in ["Patient Appointment", "Patient Encounter"]:
			return service_item_and_practitioner_charge(doc)[0]
		elif doc.doctype == "Inpatient Occupancy":
			return get_billable_service_item(
				"Healthcare Service Unit Type",
				frappe.db.get_value("Healthcare Service Unit", doc.service_unit, "service_unit_type"),
			)
	return False


def get_billable_service_item(doctype, name):
	if frappe.db.get_value(doctype, name, "is_billable") == 1:
		return frappe.db.get_value(doctype, name, "item")
