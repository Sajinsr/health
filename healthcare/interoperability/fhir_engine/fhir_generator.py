# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, getdate


def generate_fhir_resource(map_doc, frappe_doc):
	resource_type = (map_doc.resource_type or "").strip()
	if not resource_type:  # resource type is mandatory
		frappe.throw("FHIR Resource Map is missing resource_type")

	resource = {"resourceType": resource_type}
	resource.update(add_meta(map_doc))

	errors = []
	primitive_datatypes = get_primitive_datatypes()
	cardinality_lookup = build_cardinality_lookup(map_doc)  # path: max
	doctype_meta = frappe.get_meta(map_doc.frappe_doctype)

	for element_map in map_doc.map or []:
		fhir_path = (getattr(element_map, "fhir_path", None) or "").strip()
		if not fhir_path:  # no fhir path, no key in dict
			continue

		if fhir_path == resource_type:
			continue  # root

		datatype = (getattr(element_map, "datatype", None) or "").strip()
		min_cardinality = cint(getattr(element_map, "min", 0) or 0)
		is_primitive = datatype in primitive_datatypes

		is_child_table, table_fieldname, child_fieldname = is_child_table_field(
			map_doc,
			element_map,
			doctype_meta,
		)

		if is_child_table:
			child_rows = getattr(frappe_doc, table_fieldname, None) or []

			has_any_value = False
			for row_index, child_row in enumerate(child_rows):
				raw_value = getattr(child_row, child_fieldname, None)

				if raw_value in (None, "", [], {}):
					continue

				has_any_value = True
				value = normalize_primitive_value(raw_value)

				if datatype and not is_primitive:
					value = build_complex_value(element_map, value)

				set_fhir_element(  # insert whole row
					resource=resource,
					element_map=element_map,
					value=value,
					resource_type=resource_type,
					cardinality_lookup=cardinality_lookup,
					group_index=row_index,
				)

			if not has_any_value and is_primitive and min_cardinality > 0:  # no row inserted
				errors.append(
					_("Missing required value for path '{path}' (min={min}, map={map})").format(
						path=fhir_path,
						min=min_cardinality,
						map=map_doc.name,
					)
				)
			# done, child table row
			continue

		value = get_value_from_map(element_map, frappe_doc)

		if value in (None, "", [], {}):
			if is_primitive and min_cardinality > 0:
				errors.append(
					_("Missing required value for path '{path}' (min={min}, map={map})").format(
						path=fhir_path,
						min=min_cardinality,
						map=map_doc.name,
					)
				)
			continue

		if datatype and not is_primitive:
			value = build_complex_value(element_map, value)

		set_fhir_element(
			resource=resource,
			element_map=element_map,
			value=value,
			resource_type=resource_type,
			cardinality_lookup=cardinality_lookup,
			group_index=None,
		)

	resource.update(add_narrative(map_doc, resource))
	resource = prune_empty_containers(resource)

	if errors:
		frappe.log_error(
			message="\n".join(errors),
			title=_("FHIR generation failed ({resource_type})").format(resource_type=map_doc.resource_type),
		)
		raise frappe.ValidationError(
			_("FHIR resource generation failed for {resource_type}. " "See error log for details.").format(
				resource_type=map_doc.resource_type
			)
		)

	return resource


# Strict-ish ISO patterns (good enough to avoid phone numbers)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME_RE = re.compile(
	r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?([zZ]|[+\-]\d{2}:\d{2})?$"
)
ISO_TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?$")
BOOL_STRINGS = {"true", "false", "t", "f", "y", "n", "1", "0"}


def normalize_primitive_value(value):
	"""
	Normalize Python primitives into FHIR-friendly JSON values.

	Key rule: NEVER "guess" date/datetime from arbitrary numeric strings.
	Only parse when the string matches an ISO-like pattern.
	"""
	if value is None:
		return None

	# bool must be before int/float because bool is a subclass of int in Python
	if isinstance(value, bool):
		return bool(value)

	if isinstance(value, Decimal):
		return cint(value) if value.as_tuple().exponent >= 0 else flt(value)

	if isinstance(value, (int, float)):
		return value

	if isinstance(value, datetime):
		return value.isoformat()

	if isinstance(value, date):
		return value.isoformat()

	if isinstance(value, time):
		return value.isoformat()

	if isinstance(value, timedelta):
		return value.total_seconds()

	if isinstance(value, str):
		text = value.strip()
		if not text:
			return value

		lowered = text.lower()
		if lowered in BOOL_STRINGS:
			return lowered in {"true", "t", "y", "1"}

		# Only parse if it REALLY looks like an ISO date/time/datetime
		try:
			if ISO_DATETIME_RE.match(text):
				dt_val = get_datetime(text)
				return dt_val.isoformat() if dt_val else value

			if ISO_DATE_RE.match(text):
				date_val = getdate(text)
				return date_val.isoformat() if date_val else value

			if ISO_TIME_RE.match(text):
				# leave as string, or parse to time if you want
				return text
		except Exception:
			return value

		# Anything else stays as-is (phone numbers, MRNs, codes, etc.)
		return value

	return value


def build_complex_value(element_map, value):
	"""
	Wrapper for common complex FHIR datatypes
	"""
	datatype_name = (
		getattr(element_map, "datatype", None) or getattr(element_map, "fhir_datatype", None) or ""
	)
	datatype_name = str(datatype_name).strip()
	if not datatype_name:
		return value  # unknown datatype, raise?

	if isinstance(value, (dict, list)):
		return value  # already a complex type

	text_value = str(value).strip()

	if datatype_name == "Identifier":
		return {"value": text_value}

	if datatype_name == "Reference":
		return {"reference": text_value}

	if datatype_name == "CodeableConcept":
		return {"text": text_value}

	if datatype_name == "Coding":
		return {"code": text_value}

	if datatype_name == "HumanName":
		return {"text": text_value}

	if datatype_name == "ContactPoint":
		return {
			"system": "phone",
			"value": text_value,
		}

	if datatype_name == "Address":
		return {"text": text_value}

	if datatype_name == "Period":
		# Accept:
		# - tuple/list of two values       -> (start, end)
		# - string "start/end"             -> split on "/"
		# - scalar                         -> start only
		if isinstance(value, (list, tuple)) and len(value) >= 1:
			start = str(value[0]).strip() if value[0] is not None else None
			end = str(value[1]).strip() if len(value) > 1 and value[1] is not None else None
			period = {}
			if start:
				period["start"] = start
			if end:
				period["end"] = end
			return period

		if "/" in text_value:
			start_text, end_text = text_value.split("/", 1)
			period = {}
			start_text = start_text.strip()
			end_text = end_text.strip()
			if start_text:
				period["start"] = start_text
			if end_text:
				period["end"] = end_text
			return period

		# Fallback: scalar -> start only
		return {"start": text_value}

	if datatype_name == "Quantity":
		# Accept forms:
		# - tuple/list (value, unit)
		# - "123 kg"  -> value=123, unit="kg"
		# - "123"     -> value=123
		# - scalar    -> value=<as float if possible>
		quantity = {}

		if isinstance(value, (list, tuple)) and value:
			raw_value = value[0]
			raw_unit = value[1] if len(value) > 1 else None
			try:
				quantity["value"] = float(raw_value)
			except Exception:
				quantity["value"] = raw_value
			if raw_unit:
				quantity["unit"] = str(raw_unit).strip()
			return quantity

		# string with space -> try split into value + unit
		parts = text_value.split()
		if len(parts) >= 2:
			number_part = parts[0]
			unit_part = " ".join(parts[1:]).strip()
			try:
				quantity["value"] = float(number_part)
			except Exception:
				quantity["value"] = text_value  # give up on numeric interpretation
			if unit_part:
				quantity["unit"] = unit_part
			return quantity

		# plain scalar -> try numeric, else keep as string
		try:
			quantity["value"] = float(text_value)
		except Exception:
			quantity["value"] = text_value
		return quantity

	if datatype_name == "Attachment":
		return {"url": text_value}

	return value


def set_fhir_element(
	resource,
	element_map,
	value,
	resource_type,
	cardinality_lookup,
	group_index=None,
):
	"""
	Assign `value` into `resource` based on a dotted FHIR path and cardinality
	For child table the whole row
	"""

	raw_path = (getattr(element_map, "fhir_path", None) or "").strip()
	if not raw_path or value is None:
		return

	parts = raw_path.split(".")

	if resource_type:
		if parts[0] == resource_type:
			parts = parts[1:]
		else:
			first = parts[0]
			if first and first[0].isupper():
				return

	if not parts:
		return

	def get_max(full_path):
		if cardinality_lookup:
			max_value = cardinality_lookup.get(full_path)
		else:
			max_value = None  # default = 1
		return (max_value or "1").strip()

	def qualified_path(path_without_resource):
		return f"{resource_type}.{path_without_resource}" if resource_type else path_without_resource

	current = resource

	# intermediates
	for index, segment in enumerate(parts[:-1]):
		path_without_resource = ".".join(parts[: index + 1])
		full_path = qualified_path(path_without_resource)
		segment_max = get_max(full_path)

		# honor max=0 (intermediate suppressed by profile)
		if segment_max == "0":
			return

		if not isinstance(current, dict):
			return

		# repeating container
		if segment_max != "1":
			existing = current.get(segment)

			# child table grouping: index by group_index
			if group_index is not None:
				if existing is None:
					existing = []
					current[segment] = existing

				if not isinstance(existing, list):
					existing = [existing]
					current[segment] = existing

				# ensure list long enough
				while len(existing) <= group_index:
					existing.append({})

				bucket = existing[group_index]
				if not isinstance(bucket, dict):
					bucket = {}
					existing[group_index] = bucket

				current = bucket
				continue

			# old behavior: always use last bucket
			if existing is None:
				bucket = {}
				current[segment] = [bucket]
				current = bucket
			elif isinstance(existing, list):
				if not existing:
					bucket = {}
					existing.append(bucket)
					current = bucket
				else:
					last = existing[-1]
					if not isinstance(last, dict):
						bucket = {}
						existing.append(bucket)
						current = bucket
					else:
						current = last
			elif isinstance(existing, dict):
				current[segment] = [existing]
				current = existing
			else:
				bucket = {}
				current[segment] = [bucket]
				current = bucket

		# non-repeating container
		else:
			existing = current.get(segment)
			if existing is None or not isinstance(existing, dict):
				bucket = {}
				current[segment] = bucket
				current = bucket
			else:
				current = existing

	# leaf
	leaf_key = parts[-1]
	leaf_path_without_resource = ".".join(parts)
	full_leaf_path = qualified_path(leaf_path_without_resource)
	leaf_max = get_max(full_leaf_path)

	# honor max=0 at leaf
	if leaf_max == "0":
		return

	if not isinstance(current, dict):
		return

	if leaf_max == "1":
		current[leaf_key] = value
		return

	existing_leaf = current.get(leaf_key)

	if existing_leaf is None:
		current[leaf_key] = [value]
	elif isinstance(existing_leaf, list):
		if value not in existing_leaf:
			existing_leaf.append(value)
	else:
		if value == existing_leaf:
			current[leaf_key] = [existing_leaf]
		else:
			current[leaf_key] = [existing_leaf, value]


def get_primitive_datatypes():
	"""
	Return set of primitive FHIR datatype names from FHIR Datatype doctype
	"""
	cache = frappe.cache()
	cached = cache.get_value("fhir_primitive_datatypes")
	if cached:
		return set(cached)

	names = frappe.get_all(
		"FHIR Datatype",
		filters={"is_primitive": 1},
		pluck="name",
	)
	cache.set_value("fhir_primitive_datatypes", names)
	return set(names)


def get_fhir_datatype_doc(datatype_name):
	return frappe.get_cached_doc("FHIR Datatype", datatype_name)


def build_cardinality_lookup(resource_map):
	"""
	Build a dict mapping fully qualified FHIR paths to max cardinality
	"""
	lookup = {}
	resource_type = (resource_map.resource_type or "").strip()
	if not resource_type:
		return lookup

	prefix = resource_type + "."

	for row in resource_map.map:
		path = (row.fhir_path or "").strip()
		if not path:
			continue
		if not path.startswith(prefix):
			continue

		max_value = (row.max or "1").strip()
		lookup[path] = max_value

	return lookup


def add_meta(map_doc):
	if not getattr(map_doc, "fhir_profiles", None):
		return {}

	urls = []
	for profile in getattr(map_doc, "fhir_profiles", None):
		if getattr(profile, "url", None):
			urls.append(profile.url)

	if not urls:
		return {}

	return {"meta": {"profile": urls}}


def add_narrative(map_doc, resource):
	template_name = getattr(map_doc, "narrative_template", None)
	if not template_name:
		return {}

	template = frappe.get_doc("Terms and Conditions", template_name)
	raw_html = template.terms or "<div>Missing narrative template</div>"

	div_html = frappe.render_template(raw_html, {"resource": resource})

	# pick language from resource if present, fallback to 'en'
	language = resource.get("language") or "en"

	return {
		"text": {
			"status": "generated",
			"div": (
				f"<div xmlns='http://www.w3.org/1999/xhtml' "
				f"lang='{language}' xml:lang='{language}'>"
				f"{div_html}</div>"
			),
		}
	}


def get_value_from_map(element_map, frappe_doc=None):
	"""
	Resolve a value for this element from the map row + frappe_doc.
	"""
	for key in ("fixed_value", "frappe_field", "pattern_value", "default_value"):
		value = getattr(element_map, key, None)

		if key == "frappe_field" and value and frappe_doc is not None:
			value = getattr(frappe_doc, value, None)

		if value not in (None, "", [], {}):
			return normalize_primitive_value(value)

	return None


def prune_empty_containers(value):
	"""
	Recursively prune empty dicts/lists from a FHIR resource.
	"""
	if isinstance(value, dict):
		pruned = {}
		for key, child in value.items():
			child_pruned = prune_empty_containers(child)
			if child_pruned not in (None, "", [], {}):
				pruned[key] = child_pruned
		return pruned

	if isinstance(value, list):
		pruned_list = []
		for item in value:
			item_pruned = prune_empty_containers(item)
			if item_pruned not in (None, "", [], {}):
				pruned_list.append(item_pruned)
		return pruned_list

	return value


def parse_frappe_field_reference(element_map):
	"""
	Parse frappe_field into (table_fieldname, child_fieldname).
	"""
	ref = (getattr(element_map, "frappe_field", None) or "").strip()
	if not ref:
		return None, None

	if "." in ref:
		table_fieldname, child_fieldname = ref.split(".", 1)
		return table_fieldname.strip(), child_fieldname.strip() or None

	return ref, None


def is_child_table_field(map_doc, element_map, doctype_meta):
	table_fieldname, child_fieldname = parse_frappe_field_reference(element_map)
	if not table_fieldname:
		return False, None, None

	doctype_field = doctype_meta.get_field(table_fieldname)
	if not doctype_field:
		return False, None, None

	if getattr(doctype_field, "fieldtype", None) != "Table":
		return False, None, None

	return True, table_fieldname, child_fieldname


def has_value_at_path(resource, fhir_path):
	if not fhir_path:
		return False

	path_parts = fhir_path.split(".")
	current = resource

	for part in path_parts:
		if not isinstance(current, dict):
			return False
		if part not in current:
			return False
		current = current[part]

	return current not in (None, "", [], {})


def is_required(meta):
	try:
		return int(meta.get("min") or 0) > 0
	except Exception:
		return False
