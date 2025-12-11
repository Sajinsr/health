# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from healthcare.interoperability.fhir_engine.fhir_resource_generator import (
	generate_fhir_resource_from_map,
)

# from healthcare.interoperability.fhir_engine.fhir_builder import FHIRResourceBuilder

# from healthcare.interoperability.utils.fhir_transformer import FHIRResourceTransformer
# from healthcare.interoperability.fhir_engine.fhir_resource_generator import FHIRResourceGenerator


class FHIRResourceMap(Document):
	def autoname(self):
		if not self.name:
			self.name = f"MAP-{self.frappe_doctype}-{self.fhir_structure_def}"

			# append fhir profile and name
			if self.fhir_profile:
				self.name = f"{self.name}-{self.fhir_profile}-{self.fhir_version}"
			else:
				self.name = f"{self.name}-{self.fhir_version}"

	def validate(self):
		self.resource_type = self.fhir_structure_def.split("-", 1)[0]

		# also need to consider COMPLEX_FHIR_DATATYPES (validation present in cscript for now)
		# missing = [
		# 	fm.fhir_path for fm in self.map if fm.min > 0 and not fm.frappe_field and not fm.default_value
		# ]
		# if missing:
		# 	frappe.throw(
		# 		_(
		# 			"You must map or supply a default value for these FHIR elements which are required as per Resource Structure Definition:\n  "
		# 		)
		# 		+ "\n  ".join(missing)
		# 	)

	@frappe.whitelist()
	def save_mapped_elements(self, elements):
		self.set("map", [])
		print(f"count: {len(elements)}")
		for el in elements:
			fhir_path = el.get("fhir_path")
			datatype = el.get("datatype")

			# handle [x]
			if el.get("is_choice_type") and datatype and "," not in datatype and "[x]" in fhir_path:
				replacement = datatype[0].upper() + datatype[1:]
				fhir_path = fhir_path.replace("[x]", replacement)

			# set fhir datatype link
			fhir_datatype = None
			if datatype and frappe.db.exists("FHIR Datatype", datatype):
				fhir_datatype = datatype

			self.append(
				"map",
				{
					"fhir_path": fhir_path,
					"datatype": datatype,
					"fhir_datatype": fhir_datatype,
					"min": int(el.get("min") or 0),
					"max": str(el.get("max") or "1"),
					"short": el.get("short") or "",
					"definition": el.get("definition") or "",
					"is_required": bool(el.get("is_required")),
					"is_choice_type": bool(el.get("is_choice_type")),
					"frappe_field": el.get("frappe_field"),
					"valueset_url": el.get("valueset_url"),
					"binding_strength": el.get("binding_strength"),
					"fixed_value": el.get("fixed_value"),
					"pattern_value": el.get("pattern_value"),
					"default_value": el.get("default_value"),
					"target_profiles": el.get("target_profiles"),
				},
			)
		self.save()
		frappe.msgprint(_("FHIR element <> Frappe field mapping saved."), alert=True)

	@frappe.whitelist()
	def new_preview_fhir_resource(self, docname, show_errors=False):
		frappe.msgprint("Not Implemented")
		# frappe_doc = frappe.get_doc(self.frappe_doctype, docname)

		# generator = FHIRResourceGenerator(self, frappe_doc)
		# resource_json = generator.generate()
		# return resource_json

	@frappe.whitelist()
	def preview_fhir_resource(self, docname, show_errors=False):
		# frappe_doc = frappe.get_doc(self.frappe_doctype, docname)

		# builder = FHIRResourceBuilder(self, frappe_doc)
		# resource_json = builder.build()
		# return resource_json
		resource_map = frappe.get_doc("FHIR Resource Map", self.name)
		patient_doc = frappe.get_doc("Patient", docname)
		resource = generate_fhir_resource_from_map(resource_map, patient_doc)
		return resource

	@frappe.whitelist()
	def rebuild_element_map(self):
		"""
		Overlay base + profile StructureDefinitions and populate the
		`map` child table (FHIR Resource Element Map).
		"""
		base_structure_definition_name = getattr(self, "fhir_structure_def", None)
		if not base_structure_definition_name:
			frappe.throw("Base FHIR Structure Definition is not set on FHIR Resource Map.")

		# Collect profile StructureDefinition names from child table in idx order
		profile_structure_definition_names = []
		profile_rows = getattr(self, "fhir_profiles", []) or []
		profile_rows = sorted(profile_rows, key=lambda row: getattr(row, "idx", 0))

		for row in profile_rows:
			sd_name = getattr(row, "fhir_structure_definition", None)
			if sd_name:
				profile_structure_definition_names.append(sd_name)

		effective_elements = build_effective_elements(
			base_structure_definition_name,
			profile_structure_definition_names,
		)

		# Preserve existing mappings for same fhir_path
		existing_by_path = {}
		existing_rows = getattr(self, "map", []) or []
		for row in existing_rows:
			path = getattr(row, "fhir_path", None)
			if path:
				existing_by_path[path] = row

		# Reset child table and repopulate
		self.set("map", [])

		for path in sorted(effective_elements.keys()):
			eff = effective_elements[path]

			new_row = self.append("map", {})
			# Core definition fields
			new_row.fhir_path = eff["path"]

			# datatype (string)
			datatype_str = ",".join(sorted(eff["type_codes"])) if eff["type_codes"] else None
			new_row.datatype = datatype_str

			# If there is exactly one type code, set fhir_datatype link to it
			# so regex gets pulled via fetch_from
			if eff["type_codes"] and len(eff["type_codes"]) == 1:
				new_row.fhir_datatype = list(eff["type_codes"])[0]
			else:
				new_row.fhir_datatype = None

			new_row.min = eff["min"]
			new_row.max = eff["max"]
			new_row.short = eff["short"]
			new_row.definition = eff["definition"]
			new_row.valueset_url = eff["valueset_url"]
			new_row.binding_strength = eff["binding_strength"]

			# derived flags
			new_row.is_required = 1 if eff["min"] is not None and eff["min"] > 0 else 0
			# basic heuristic: multiple types → choice type
			new_row.is_choice_type = 1 if eff["type_codes"] and len(eff["type_codes"]) > 1 else 0

			# carry over existing mapping-related fields
			existing_row = existing_by_path.get(path)
			if existing_row:
				for fieldname in (
					"frappe_field",
					# "fixed_value",
					# "pattern_value",
					"default_value",
					# "profile",
					# "target_profiles",
				):
					if hasattr(existing_row, fieldname):
						setattr(new_row, fieldname, getattr(existing_row, fieldname))

		self.save()
		return self.name


def build_effective_elements(base_structure_definition_name, profile_structure_definition_names):
	effective_elements = {}

	base_structure_definition = frappe.get_doc(
		"FHIR Structure Definition", base_structure_definition_name
	)
	build_effective_elements_from_structure_definition(effective_elements, base_structure_definition)

	for profile_structure_definition_name in profile_structure_definition_names:
		profile_structure_definition = frappe.get_doc(
			"FHIR Structure Definition", profile_structure_definition_name
		)
		overlay_structure_definition(effective_elements, profile_structure_definition)

	cleanup_effective_elements(effective_elements)
	return effective_elements


def build_effective_elements_from_structure_definition(
	effective_elements, structure_definition_document
):
	for element in getattr(structure_definition_document, "element_paths", []):
		path = get_element_path(element)
		if not path:
			continue

		type_codes = get_element_type_codes(element)

		effective_elements[path] = {
			"path": path,
			"min": get_int(getattr(element, "min", None)),
			"max": get_maximum_value(getattr(element, "max", None)),
			"type_codes": type_codes,
			"binding_strength": getattr(element, "binding_strength", None),
			"valueset_url": getattr(element, "valueset_url", None),
			"is_required": bool(getattr(element, "is_required", 0)),
			"short": getattr(element, "short", None),
			"definition": getattr(element, "definition", None),
			"is_removed": is_removed(getattr(element, "max", None)),
			"regex": getattr(element, "regex", None),
			"fixed_value": getattr(element, "fixed_value", None),
			"pattern_value": getattr(element, "pattern_value", None),
			"default_value": getattr(element, "default_value", None),
			"target_profiles": getattr(element, "target_profiles", None),
		}


def overlay_structure_definition(effective_elements, structure_definition_document):
	for element in getattr(structure_definition_document, "element_paths", []):
		path = get_element_path(element)
		if not path:
			continue

		if path not in effective_elements:
			effective_elements[path] = {
				"path": path,
				"min": None,
				"max": None,
				"type_codes": set(),
				"binding_strength": None,
				"valueset_url": None,
				"is_required": False,
				"short": None,
				"definition": None,
				"is_removed": False,
				"regex": "",
				"fixed_value": "",
				"pattern_value": "",
				"default_value": "",
				"target_profiles": "",
			}

		apply_element_overlay(effective_elements[path], element)


def apply_element_overlay(effective_element, overlay_element):
	overlay_minimum = get_int(getattr(overlay_element, "min", None))
	if overlay_minimum is not None:
		if effective_element["min"] is None:
			effective_element["min"] = overlay_minimum
		else:
			effective_element["min"] = max(effective_element["min"], overlay_minimum)

	overlay_maximum_raw = getattr(overlay_element, "max", None)
	overlay_maximum = get_maximum_value(overlay_maximum_raw)
	if overlay_maximum is not None:
		if overlay_maximum == "0":
			effective_element["max"] = "0"
			effective_element["is_removed"] = True
		else:
			if effective_element["max"] is None:
				effective_element["max"] = overlay_maximum
			else:
				effective_element["max"] = more_restrictive_maximum(effective_element["max"], overlay_maximum)

	overlay_type_codes = get_element_type_codes(overlay_element)
	if overlay_type_codes:
		if effective_element["type_codes"]:
			intersection = effective_element["type_codes"].intersection(overlay_type_codes)
			if intersection:
				effective_element["type_codes"] = intersection
			else:
				effective_element["type_codes"] = overlay_type_codes
		else:
			effective_element["type_codes"] = overlay_type_codes

	overlay_binding_strength = getattr(overlay_element, "binding_strength", None)
	if overlay_binding_strength:
		effective_element["binding_strength"] = stronger_binding_strength(
			effective_element["binding_strength"], overlay_binding_strength
		)
		overlay_valueset_url = getattr(overlay_element, "valueset_url", None)
		if overlay_valueset_url and effective_element["binding_strength"] == overlay_binding_strength:
			effective_element["valueset_url"] = overlay_valueset_url

	overlay_must_support = getattr(overlay_element, "is_required", None)
	if overlay_must_support:
		effective_element["is_required"] = True

	overlay_short = getattr(overlay_element, "short", None)
	if overlay_short:
		effective_element["short"] = overlay_short

	overlay_definition = getattr(overlay_element, "definition", None)
	if overlay_definition:
		effective_element["definition"] = overlay_definition

	if overlay_maximum_raw is not None and is_removed(overlay_maximum_raw):
		effective_element["is_removed"] = True


def cleanup_effective_elements(effective_elements):
	paths_to_delete = []

	for path, element in effective_elements.items():
		if element.get("is_removed"):
			paths_to_delete.append(path)
			continue

		if element.get("max") == "0":
			paths_to_delete.append(path)
			continue

		type_codes = element.get("type_codes")
		if type_codes is not None and len(type_codes) == 0:
			paths_to_delete.append(path)
			continue

	print(f"Deleting {len(paths_to_delete)}")
	for path in paths_to_delete:
		effective_elements.pop(path, None)


def get_element_path(element):
	for attribute in ("fhir_path", "path", "element_path"):
		value = getattr(element, attribute, None)
		if value:
			return value
	return None


def get_element_type_codes(element):
	raw_type_codes = getattr(element, "fhir_datatype", None) or getattr(element, "datatype", None)

	if not raw_type_codes:
		return set()

	if isinstance(raw_type_codes, str):
		if "," in raw_type_codes:
			parts = [value.strip() for value in raw_type_codes.split(",") if value.strip()]
			return set(parts)
		return {raw_type_codes.strip()}

	try:
		iterable = list(raw_type_codes)
	except TypeError:
		return set()

	values = set()
	for item in iterable:
		if isinstance(item, str):
			value = item.strip()
		else:
			value = getattr(item, "code", None) or getattr(item, "type_code", None)
		if value:
			values.add(value)

	return values


def more_restrictive_maximum(current, new):
	if current == "0" or new == "0":
		return "0"

	if current == "*":
		return new

	if new == "*":
		return current

	try:
		current_value = int(current)
		new_value = int(new)
	except ValueError:
		return new

	return str(min(current_value, new_value))


def stronger_binding_strength(current, new):
	order = {
		None: 0,
		"example": 1,
		"preferred": 2,
		"extensible": 3,
		"required": 4,
	}

	current_score = order.get(current, 0)
	new_score = order.get(new, 0)

	if new_score >= current_score:
		return new

	return current if current is not None else new


def get_int(value):
	if value is None:
		return None
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def get_maximum_value(value):
	if value is None:
		return None
	if isinstance(value, str):
		value = value.strip()
		return value or None
	return str(value)


def is_removed(maximum_value):
	if maximum_value is None:
		return False
	if isinstance(maximum_value, str):
		return maximum_value.strip() == "0"
	try:
		return int(maximum_value) == 0
	except (TypeError, ValueError):
		return False
