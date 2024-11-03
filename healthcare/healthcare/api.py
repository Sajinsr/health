# -*- coding: utf-8 -*-
# Copyright (c) 2018, SehaCloud and contributors
# For license information, please see license.txt

import json

from sehacloud_healthcare.sehacloud_healthcare.healthcare_service_to_invoice import (
	manage_package_session,
)

import frappe
from frappe.utils import (
	add_days,
	date_diff,
	datetime,
	formatdate,
	get_datetime,
	get_time,
	getdate,
	nowtime,
	time_diff_in_seconds,
)
from frappe.utils.background_jobs import enqueue

from erpnext.healthcare.utils import (
	get_sales_invoice_for_healthcare_doc,
	sales_item_details_for_healthcare_doc,
)


@frappe.whitelist()
def get_app_data(args):
	args = json.loads(args)
	if not "doctype" in args or not args["doctype"]:
		return False
	if not "app_key" in args or not args["app_key"]:
		return False
	doctype = args["doctype"]
	if "app_key" in args:
		app_key = args["app_key"]
	fields = []
	if "fields" in args and args["fields"]:
		fields = args["fields"]
	filters = {}
	if "filters" in args:
		filters = args["filters"]
	limit_start = 0
	if "limit_start" in args:
		limit_start = args["limit_start"]
	limit_page_length = 20
	if "limit_page_length" in args:
		limit_page_length = args["limit_page_length"]
	ignore_permissions = False
	if "ignore_permissions" in args:
		ignore_permissions = args["ignore_permissions"]
	order_by = "modified desc"
	if "order_by" in args:
		order_by = args["order_by"]
	data = {}
	fields.extend(["name"])
	result = frappe.get_list(
		doctype,
		fields=fields,
		filters=filters,
		order_by=order_by,
		limit_start=limit_start,
		limit_page_length=limit_page_length,
		ignore_permissions=ignore_permissions,
	)
	if result:
		data["data"] = result
	return data


@frappe.whitelist()
def create_patient_appointment(args):
	args = json.loads(args)
	appointment_fields = [
		"patient",
		"appointment_date",
		"appointment_time",
		"practitioner",
		"appointment_type",
		"source",
	]

	if not "app_key" in args or not args["app_key"]:
		return False

	if not "ignore_permissions" in args or not args["ignore_permissions"]:
		return False

	for appointment_field in appointment_fields:
		if not appointment_field in args or not args[appointment_field]:
			return False

	appointment_fields.extend(
		[
			"duration",
			"service_unit",
			"referring_practitioner",
			"procedure_template",
			"radiology_procedure",
			"procedure_prescription",
		]
	)
	ignore_permissions = False
	if "ignore_permissions" in args:
		ignore_permissions = args["ignore_permissions"]

	appointment = frappe.new_doc("Patient Appointment")
	for appointment_field in appointment_fields:
		if appointment_field in args and args[appointment_field]:
			appointment.set(appointment_field, args[appointment_field])
	appointment.status = "Scheduled"
	appointment.department = frappe.db.get_value(
		"Healthcare Practitioner", args["practitioner"], "department"
	)
	if not "duration" in args or not args["duration"]:
		appointment.duration = frappe.db.get_value(
			"Appointment Type", args["appointment_type"], "default_duration"
		)
	if appointment.source == "Direct":
		appointment.referring_practitioner = args["practitioner"]
	elif "referring_practitioner" in args and args["referring_practitioner"]:
		appointment.referring_practitioner = args["referring_practitioner"]
	try:
		appointment.save(ignore_permissions=ignore_permissions)
		return appointment
	except Exception as e:
		return e


@frappe.whitelist()
def get_availability(args):
	args = json.loads(args)

	mandatory_fields = ["app_key", "start", "filters"]

	for mandatory_field in mandatory_fields:
		if not mandatory_field in args or not args[mandatory_field]:
			return mandatory_field

	ignore_permissions = False
	if "ignore_permissions" in args:
		ignore_permissions = args["ignore_permissions"]

	if "end" in args and args["end"]:
		end = args["end"]
	else:
		end = add_days(getdate(args["start"]), 1)

	filters = args["filters"]
	if not "practitioner" in filters:
		return False
	if not "service_unit" in filters:
		filters["service_unit"] = False

	from sehacloud_healthcare.sehacloud_healthcare.utils import get_events

	try:
		events = get_events(args["start"], end, args["filters"])
		slots = []
		for event in events:
			if isinstance(event, dict):
				event = frappe._dict(event)
			if event.doctype == "Patient Appointment":
				slots.append(
					{
						"start": event.start,
						"end": event.end,
						"status": "Booked",
						"practitioner": event.practitioner,
					}
				)
			elif event.doctype == "Practitioner Event":
				slots.append(
					{
						"start": event.start,
						"end": event.end,
						"status": "Available",
						"practitioner": event.practitioner,
					}
				)
			else:
				slots.append(
					{
						"start": event.start,
						"end": event.end,
						"practitioner": event.practitioner,
						"status": event.title[0] if (event.title and len(event.title) > 0) else "",
					}
				)
		return slots
	except Exception as e:
		return e
