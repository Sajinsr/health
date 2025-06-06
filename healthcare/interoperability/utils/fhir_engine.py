# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
import re
from collections import defaultdict

import frappe

PATH_TOKENIZER = re.compile(r"([^\.\[\]]+)|\[(\d+)\]").findall


def set_dotted_path_value(data, path, value):

	tokens = PATH_TOKENIZER(path)

	parsed_paths = [("key", k) if k else ("index", int(i)) for k, i in tokens]

	for i, (type, val) in enumerate(parsed_paths):
		is_last = i == len(parsed_paths) - 1

		if type == "key":
			if not isinstance(data, dict):
				raise TypeError(f"Expected dict at segment '{val}', got {type(data).__name__}")
			if val not in data:
				data[val] = {} if not is_last else value
			if is_last:
				data[val] = value
			else:
				data = data[val]

		elif type == "index":
			if not isinstance(data, list):
				raise TypeError(f"Expected list at index [{val}], got {type(data).__name__}")
			while len(data) <= val:
				data.append({})
			if is_last:
				data[val] = value
			else:
				data = data[val]


def generate_fhir_resource(frappe_doc):

	mapping = frappe.get_doc(
		"FHIR Resource Map", {"frappe_doctype": frappe_doc.doctype, "is_active": 1}
	)  # TODO: filters
	resource_type = (
		mapping.fhir_structure_def.split("-", 1)[0]
		if mapping.fhir_structure_def
		else mapping.fhir_resource
	)
	resource = {"resourceType": resource_type}
	repeat_groups = defaultdict(dict)

	for row in mapping.map:
		fhir_path = row.fhir_path or ""
		if fhir_path.strip() in ("", resource_type):
			continue

		if fhir_path.startswith(resource_type + "."):
			fhir_path = fhir_path[len(resource_type) + 1 :]

		value = frappe_doc.get(row.frappe_field) if row.frappe_field else None
		if not value or (isinstance(value, str) and not value.strip()):
			value = row.default_value
		if value in (None, "", [], {}, "null"):
			continue

		path_parts = fhir_path.split(".", 1)
		root = path_parts[0]
		subpath = path_parts[1] if len(path_parts) > 1 else "_self"

		if row.max == "*":
			entry = repeat_groups[root]
			if subpath == "_self":
				repeat_groups[root] = [value]
			else:
				try:
					set_dotted_path_value(entry, subpath, value)
				except Exception as e:
					frappe.log_error(f"{fhir_path} ← {value}\n{e}", "Repeat Merge Error")
		else:
			try:
				set_dotted_path_value(resource, fhir_path, value)
			except Exception as e:
				frappe.log_error(f"{fhir_path} ← {value}\n{e}", "Single Field Error")

	for root, entry in repeat_groups.items():
		resource[root] = [entry] if isinstance(entry, dict) else entry

	return resource


def upsert_fhir_resource(frappe_doc, method):
	"""
	hook on_update all docs
	check if structure definition is mapped for dt
	if map not found return else generate resource
	"""

	if not frappe.db.exists(
		{
			"doctype": "FHIR Resource Map",
			"is_active": 1,
			"frappe_doctype": frappe_doc.doctype,
		}
	):
		# TODO: optimize
		return

	fhir_data = generate_fhir_resource(frappe_doc)

	key = {
		"frappe_doctype": frappe_doc.doctype,
		"frappe_document": frappe_doc.name,
	}

	existing = frappe.get_all("FHIR Resource", filters=key, pluck="name")

	data = {
		**key,
		"fhir_resource_type": fhir_data.get("resourceType"),
		"fhir_resource": json.dumps(fhir_data, indent=2),
	}

	if existing:
		frappe.db.set_value("FHIR Resource", existing[0], data)
	else:
		frappe.get_doc({**data, "doctype": "FHIR Resource"}).insert(ignore_permissions=True)

	return fhir_data
