# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import re
from datetime import date, datetime

import frappe

PRIMITIVE_TYPES = {
	"boolean",
	"integer",
	"decimal",
	"string",
	"uri",
	"url",
	"canonical",
	"base64Binary",
	"instant",
	"date",
	"dateTime",
	"time",
	"code",
	"oid",
	"id",
	"markdown",
	"unsignedInt",
	"positiveInt",
	"xhtml",
}


class PrimitiveDatatypeBuilder:
	def __init__(self, frappe_doc):
		self.frappe_doc = frappe_doc

	def build(self, mapping):
		raw_value = self.get_mapped_value(mapping)
		if raw_value is not None:
			return self._ensure_valid_primitive_type(raw_value, mapping.fhir_datatype)
		return None

	def get_mapped_value(self, element_map):
		for key in ("fixed_value", "frappe_field", "pattern_value", "default_value"):
			value = getattr(element_map, key, None)
			if key == "frappe_field" and value:
				value = self.frappe_doc.get(value)
			if value not in (None, "", [], {}):
				return value
		return None

	def _ensure_valid_primitive_type(self, value, datatype):
		if datatype == "boolean":
			if isinstance(value, str):
				return value.strip().lower() in ("1", "true", "yes")
			return bool(value)

		if datatype in {"positiveInt", "unsignedInt", "integer"}:
			try:
				return int(value)
			except (ValueError, TypeError):
				frappe.log_error(
					f"Invalid integer for {datatype}: {value}", "FHIR Primitive Datatype casting error"
				)
				return None

		if datatype == "decimal":
			try:
				return float(value)
			except (ValueError, TypeError):
				frappe.log_error(f"Invalid decimal: {value}", "FHIR Primitive Datatype casting error")
				return None

		if datatype == "code":
			value = str(value).strip()
			return value.lower()

		if datatype in {"date", "dateTime", "instant"}:
			if isinstance(value, (date, datetime)):
				return value.isoformat()
			return str(value).strip()

		# TODO: add more as required

		return value


class ComplexDatatypeBuilder:
	def __init__(self, mappings_by_path, frappe_doc):
		self.mappings_by_path = mappings_by_path
		self.frappe_doc = frappe_doc
		self.primitive_builder = PrimitiveDatatypeBuilder(self.frappe_doc)
		self.extension_builder = ExtensionBuilder(self.mappings_by_path, self.frappe_doc)

	def build(self, parent_path):
		result = {}
		child_mappings = self._get_child_mappings(parent_path)

		for path, mapping in child_mappings.items():
			relative_leaf = path[len(parent_path) + 1 :]
			if "." in relative_leaf:
				continue
			leaf = relative_leaf
			datatype = mapping.fhir_datatype
			max_cardinality = mapping.max

			if datatype in PRIMITIVE_TYPES:
				value = self.primitive_builder.build(mapping)
				if value is not None:
					result[leaf] = [value] if max_cardinality == "*" else value

			elif datatype == "Extension":
				ext = self.extension_builder.build(path)
				if ext:
					result[leaf] = ext

			else:
				nested = self.build(path)
				if nested:
					result[leaf] = [nested] if max_cardinality == "*" else nested

		return result if result else None

	def _get_child_mappings(self, parent_path):
		prefix = parent_path + "."

		direct_mappings = {
			path: mapping for path, mapping in self.mappings_by_path.items() if path.startswith(prefix)
		}
		return direct_mappings

	def _get_unmapped_children(self, parent_path):  # unused
		parent_mapping = self.mappings_by_path.get(parent_path)
		if not parent_mapping:
			return {}

		datatype = parent_mapping.fhir_datatype
		if not datatype or frappe.db.get_value("FHIR Datatype", datatype, "is_primitive"):
			return {}

		children = frappe.get_all(
			"FHIR Datatype Element",
			filters={"parent": datatype},
			fields=["element_name", "fhir_datatype", "max", "min"],
			order_by="idx",
		)

		return {
			f"{parent_path}.{child.fieldname}": frappe._dict(
				fhir_path=f"{parent_path}.{child.fieldname}",
				fhir_datatype=child.datatype,
				max=child.max,
				min=child.min,
				is_required=child.min > 0,
				fixed_value=None,  # TODO: set parent's value
				pattern_value=None,
				default_value=None,
				frappe_field=None,
			)
			for child in children
		}


class ExtensionBuilder:
	def __init__(self, mappings_by_path, frappe_doc):
		self.mappings_by_path = mappings_by_path
		self.frappe_doc = frappe_doc
		self.primitive_builder = PrimitiveDatatypeBuilder(self.frappe_doc)

	def build(self, parent_path):
		mapping = self.mappings_by_path.get(parent_path)
		value = self.primitive_builder.build(mapping)
		extensions = []

		if value is not None:
			extensions.append({"url": parent_path, "valueString": value})

		for path, mapping in self._get_child_mappings(parent_path).items():
			child_value = self.primitive_builder.build(mapping)
			if child_value is not None:
				extensions.append({"url": path, "valueString": child_value})

		return extensions if extensions else None

	def _get_child_mappings(self, parent_path):
		prefix = parent_path + "."
		return {
			path: mapping for path, mapping in self.mappings_by_path.items() if path.startswith(prefix)
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

			datatype = mapping.fhir_datatype
			max_cardinality = mapping.max

			if datatype in PRIMITIVE_TYPES:
				value = self.primitive_builder.build(mapping)

			elif datatype == "Extension":
				value = self.extension_builder.build(path)
			else:
				value = self.complex_builder.build(path)

			if value is None:
				continue
			if max_cardinality == "*":
				if not value:
					continue
				if not isinstance(value, list):
					value = [value]

			yield path, value
			self.yielded.update(self._get_child_paths(path))
			self.yielded.add(path)

	def _get_child_paths(self, parent_path):
		prefix = parent_path + "."
		return [path for path in self.mappings_by_path if path.startswith(prefix)]

	def _validate(self, fhir_path, value, mapping):
		if mapping.regex and isinstance(value, str):
			if not re.fullmatch(mapping.regex, value):
				frappe.log_error(
					f"Value '{value}' for {fhir_path} failed regex {mapping.regex}", "FHIR Validation Error"
				)
				raise ValueError(f"{fhir_path}: regex validation failed")

		if mapping.binding_strength == "required" and mapping.valueset_url:
			valid_codes = self._get_valid_codes(mapping.valueset_url)
			if value not in valid_codes:
				raise ValueError(
					f"{fhir_path}: value '{value}' not in required ValueSet {mapping.valueset_url}"
				)

	def _get_valid_codes(self, valueset_url):
		codes = frappe.get_all(
			"FHIR Code Value", filters={"valueset_url": valueset_url}, fields=["code"]
		)
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
			current = current.setdefault(part, {})
		current[parts[-1]] = value

	def _add_meta(self):
		if not self.map_doc.fhir_profile:
			return {}
		return {"meta": {"profile": [self.map_doc.fhir_profile]}}

	def _add_narrative(self, resource):
		if not self.map_doc.narrative_template:
			return {}

		template = frappe.get_doc("Terms and Conditions", self.map_doc.narrative_template)
		raw_html = template.terms or "<div>Missing narrative template</div>"

		div_html = frappe.render_template(raw_html, {"resource": resource})

		return {
			"text": {
				"status": "generated",
				"div": f"<div xmlns='http://www.w3.org/1999/xhtml'>{div_html}</div>",
			}
		}
