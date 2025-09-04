# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd.
# For license information, please see license.txt

import re
from datetime import date, datetime

import frappe


# @functools.lru_cache()
def get_primitive_datatypes():
	return frappe.get_all("FHIR Datatype", filters={"is_primitive": 1}, pluck="name")


def get_value_from_map(element_map, frappe_doc=None):
	for key in ("fixed_value", "frappe_field", "pattern_value", "default_value"):
		value = getattr(element_map, key, None)
		if key == "frappe_field" and value:
			value = getattr(frappe_doc, value, None)

		if value not in (None, "", [], {}):
			return value
	return None


def resolve_datatype(mapping, frappe_doc=None):
	dt = getattr(mapping, "fhir_datatype", None) or getattr(mapping, "datatype", None)
	if not dt:
		return None

	if isinstance(dt, str) and "," in dt:
		choices = [t.strip() for t in dt.split(",") if t.strip()]
		if not choices:
			return None

		# TODO: handle other primitive types?
		val = None
		try:
			val = get_value_from_map(mapping, frappe_doc) if frappe_doc else None
		except Exception:
			val = None

		if isinstance(val, bool) and "boolean" in choices:
			return "boolean"
		if isinstance(val, int) and "integer" in choices:
			return "integer"
		if isinstance(val, (date, datetime)) and "dateTime" in choices:
			return "dateTime"

		# fallback: first declared
		return choices[0]

	return dt


class PrimitiveDatatypeBuilder:
	def __init__(self, frappe_doc):
		self.frappe_doc = frappe_doc

	def build(self, mapping):
		raw_value = get_value_from_map(mapping, self.frappe_doc)
		if raw_value is not None:
			datatype = resolve_datatype(mapping, self.frappe_doc)
			return self._ensure_valid_primitive_type(raw_value, datatype)
		return None

	def _ensure_valid_primitive_type(self, value, datatype):
		if not datatype:
			return value

		# normalize strings
		as_text = value.strip() if isinstance(value, str) else None

		if datatype == "boolean":
			if isinstance(value, str):
				return (as_text or "").lower() in {"1", "true", "yes", "y", "t"}
			return bool(value)

		if datatype in {"positiveInt", "unsignedInt", "integer"}:
			try:
				iv = int(value)
				if datatype == "positiveInt" and iv <= 0:
					return None
				if datatype == "unsignedInt" and iv < 0:
					return None
				return iv
			except (ValueError, TypeError):
				frappe.log_error(
					f"Invalid integer for {datatype}: {value}",
					"FHIR Primitive Datatype casting error",
				)
				return None

		if datatype == "decimal":
			try:
				return float(value)
			except (ValueError, TypeError):
				frappe.log_error(
					f"Invalid decimal: {value}",
					"FHIR Primitive Datatype casting error",
				)
				return None

		if datatype == "code":
			return str(value).strip()

		if datatype in {"uri", "url", "canonical"}:
			return as_text or str(value)

		if datatype in {"date", "dateTime", "instant"}:
			if isinstance(value, (date, datetime)):
				return value.isoformat()
			return as_text or str(value)

		# pass through the rest (string, id, markdown, time, oid, base64Binary etc.)
		return value


class ExtensionBuilder:
	def __init__(self, mappings_by_path, frappe_doc):
		self.mappings_by_path = mappings_by_path
		self.frappe_doc = frappe_doc
		self.primitive_builder = PrimitiveDatatypeBuilder(self.frappe_doc)

	def build(self, parent_path):
		mapping = self.mappings_by_path.get(parent_path)
		extensions = []

		# determine URL to use for this extension group
		preferred_url = (
			getattr(mapping, "extension_url", None) or getattr(mapping, "fhir_path", None) or parent_path
		)

		# 1) parent's own value, if any
		value = self.primitive_builder.build(mapping)
		if value is not None:
			extensions.append({"url": preferred_url, "valueString": value})

		# 2) direct children become separate extensions
		for path, child_map in self._get_child_mappings(parent_path).items():
			child_value = self.primitive_builder.build(child_map)
			if child_value is not None:
				child_url = getattr(child_map, "extension_url", None) or path
				extensions.append({"url": child_url, "valueString": child_value})

		return extensions if extensions else None

	def _get_child_mappings(self, parent_path):
		prefix = parent_path + "."
		return {path: m for path, m in self.mappings_by_path.items() if path.startswith(prefix)}


class ComplexDatatypeBuilder:
	def __init__(self, mappings_by_path, frappe_doc):
		self.mappings_by_path = mappings_by_path
		self.frappe_doc = frappe_doc
		# child mappings can be primitive / extension / complex
		self.primitive_builder = PrimitiveDatatypeBuilder(self.frappe_doc)
		self.extension_builder = ExtensionBuilder(self.mappings_by_path, self.frappe_doc)

	def build(self, parent_path):
		result = {}
		child_mappings = self._get_child_mappings(parent_path)

		for path, mapping in child_mappings.items():
			relative_leaf = path[len(parent_path) + 1 :]
			if "." in relative_leaf:
				# only direct children here; nested handled by recursion
				continue

			leaf = relative_leaf
			datatype = resolve_datatype(mapping, self.frappe_doc)
			max_cardinality = mapping.max

			if datatype in get_primitive_datatypes():
				value = self.primitive_builder.build(mapping)
				if value is not None:
					result[leaf] = [value] if max_cardinality == "*" else value

			elif datatype == "Extension":
				ext = self.extension_builder.build(path)
				if ext:
					result[leaf] = ext

			else:
				# Treat any non-primitive (including BackboneElement/Resource) as complex
				nested = self.build(path)
				if nested:
					result[leaf] = [nested] if max_cardinality == "*" else nested

		return result if result else None

	def _get_child_mappings(self, parent_path):
		prefix = parent_path + "."
		return {path: m for path, m in self.mappings_by_path.items() if path.startswith(prefix)}

	# Kept for future: pull unmapped children from the datatype table if desired.
	def _get_unmapped_children(self, parent_path):  # unused
		parent_mapping = self.mappings_by_path.get(parent_path)
		if not parent_mapping:
			return {}

		datatype = resolve_datatype(parent_mapping, self.frappe_doc)
		if not datatype or frappe.db.get_value("FHIR Datatype", datatype, "is_primitive"):
			return {}

		children = frappe.get_all(
			"FHIR Datatype Element",
			filters={"parent": datatype},
			fields=["element_name", "fhir_datatype", "max", "min"],
			order_by="idx",
		)

		return {
			f"{parent_path}.{child.element_name}": frappe._dict(
				fhir_path=f"{parent_path}.{child.element_name}",
				datatype=child.fhir_datatype,
				max=child.max,
				min=child.min,
				is_required=child.min > 0,
				fixed_value=None,
				pattern_value=None,
				default_value=None,
				frappe_field=None,
			)
			for child in children
		}


class FHIRResourceMapIterator:
	def __init__(self, map_doc, frappe_doc):
		self.mappings_by_path = {m.fhir_path: m for m in map_doc.map}
		self.map_doc = map_doc
		self.frappe_doc = frappe_doc
		self.yielded = set()
		self.primitive_builder = PrimitiveDatatypeBuilder(self.frappe_doc)
		self.extension_builder = ExtensionBuilder(self.mappings_by_path, self.frappe_doc)
		self.complex_builder = ComplexDatatypeBuilder(self.mappings_by_path, self.frappe_doc)

	def iterate(self):
		for path, mapping in self.mappings_by_path.items():
			if path in self.yielded:
				continue

			datatype = resolve_datatype(mapping, self.frappe_doc)
			max_cardinality = mapping.max

			if datatype in get_primitive_datatypes():
				value = self.primitive_builder.build(mapping)
			elif datatype == "Extension":
				value = self.extension_builder.build(path)
			else:
				value = self.complex_builder.build(path)

			if value is None:
				continue

			if max_cardinality == "*":
				if not isinstance(value, list):
					value = [value]

			yield path, value
			self.yielded.update(self._get_child_paths(path))
			self.yielded.add(path)

	def _get_child_paths(self, parent_path):
		prefix = parent_path + "."
		return [path for path in self.mappings_by_path if path.startswith(prefix)]

	def _validate(self, fhir_path, value, mapping):
		"""validation skeleton regex and code"""
		if getattr(mapping, "regex", None) and isinstance(value, str):
			if not re.fullmatch(mapping.regex, value):
				frappe.log_error(
					f"Value '{value}' for {fhir_path} failed regex {mapping.regex}",
					"FHIR Validation Error",
				)
				raise ValueError(f"{fhir_path}: regex validation failed")

		if getattr(mapping, "binding_strength", None) == "required" and getattr(
			mapping, "valueset_url", None
		):
			valid_codes = self._get_valid_codes(mapping.valueset_url)
			if value not in valid_codes:
				raise ValueError(
					f"{fhir_path}: value '{value}' not in required ValueSet {mapping.valueset_url}"
				)

	def _get_valid_codes(self, valueset_url):
		codes = frappe.get_all("Code Value", filters={"valueset_url": valueset_url}, fields=["code"])
		return {c.code for c in codes}


class FHIRResourceGenerator:
	def __init__(self, map_doc, frappe_doc):
		self.map_doc = map_doc
		self.frappe_doc = frappe_doc

	def generate(self):
		iterator = FHIRResourceMapIterator(self.map_doc, self.frappe_doc)
		resource_type = self.map_doc.resource_type
		resource = {"resourceType": resource_type}

		for path, value in iterator.iterate():
			relative_path = path.removeprefix(resource_type + ".")
			self._add_path_to_dict(resource, relative_path, value)

		resource.update(self._add_meta())
		resource.update(self._add_narrative(resource))

		return resource

	def _add_path_to_dict(self, resource, dotted_path, value):
		parts = dotted_path.split(".")
		current = resource
		for part in parts[:-1]:
			current = current.setdefault(part, {})  # check if mapped?

		current[parts[-1]] = value

	def _add_meta(self):
		if not getattr(self.map_doc, "fhir_profile", None):
			return {}
		return {"meta": {"profile": [self.map_doc.url]}}

	def _add_narrative(self, resource):
		#  If a template is set, render it. Otherwise leave text alone, it could
		#  also be provided via the map if Patient.text.status/div children is added.
		template_name = getattr(self.map_doc, "narrative_template", None)
		if not template_name:
			return {}

		template = frappe.get_doc("Terms and Conditions", template_name)
		raw_html = template.terms or "<div>Missing narrative template</div>"
		div_html = frappe.render_template(raw_html, {"resource": resource})

		return {
			"text": {
				"status": "generated",
				"div": f"<div xmlns='http://www.w3.org/1999/xhtml'>{div_html}</div>",
			}
		}
