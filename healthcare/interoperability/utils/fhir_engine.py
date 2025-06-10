# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _


class FHIRDatatypeBuilder:
	def __init__(self, fhir_resource_map, mappings_by_path, doc=None):
		self.resource_map = fhir_resource_map
		self.mappings_by_path = mappings_by_path
		self.doc = doc

	def build(self, parent_path: str, datatype: str) -> dict:
		"""Build nested dict for complex FHIR Datatype (e.g., Identifier, HumanName, Reference)"""
		value = {}
		child_mappings = self._get_child_mappings(parent_path)

		for mapping in child_mappings:
			relative_path = mapping.fhir_path[len(parent_path) + 1 :]
			if "." in relative_path:
				first, rest = relative_path.split(".", 1)
				sub_path = f"{parent_path}.{first}"

				if first not in value:
					value[first] = {}

				child_datatype = mapping.fhir_datatype
				if frappe.db.get_value("FHIR Datatype", child_datatype, "is_primitive"):
					sub_value = self._get_direct_value(mapping)
					if not is_empty(sub_value):
						value.setdefault(first, {})[rest] = sub_value
				else:
					builder = FHIRDatatypeBuilder(self.resource_map, self.mappings_by_path, self.doc)
					child_value = builder.build(sub_path, child_datatype)
					if not is_empty(child_value):
						value[first] = child_value
			else:
				val = self._get_direct_value(mapping)
				if not is_empty(val):
					if relative_path in value and isinstance(value[relative_path], list):
						if isinstance(val, list):
							value[relative_path].extend(v for v in val if v not in value[relative_path])
						elif val not in value[relative_path]:
							value[relative_path].append(val)
					else:
						value[relative_path] = val

		return self._prune_empty(value)

	def _get_child_mappings(self, parent_path):
		"""Return mappings where fhir_path starts with parent_path + '.'"""
		return [m for m in self.mappings_by_path if m.fhir_path.startswith(f"{parent_path}.")]

	def _get_direct_value(self, mapping):
		if mapping.default_value:
			return mapping.default_value
		if not self.doc:
			return None
		if mapping.frappe_field:
			return self.doc.get(mapping.frappe_field)
		return None

	def _prune_empty(self, d):
		if not isinstance(d, dict):
			return d
		return {
			k: v for k, v in ((k, self._prune_empty(v)) for k, v in d.items()) if not is_empty(v)
		} or None


class FHIRResourceGenerator:
	def __init__(self, mapping_doc, frappe_doc=None):
		self.mapping = mapping_doc
		self.doc = frappe_doc
		self.datatypes = {
			d.name: d for d in frappe.get_all("FHIR Datatype", fields=["name", "is_primitive", "regex"])
		}

	def generate(self):
		resource = {"resourceType": self.mapping.resource_type}

		for mapping in self.mapping.map:
			value = self._get_value(mapping)
			if is_empty(value):
				if mapping.min > 0:
					frappe.log_error(
						title="Missing required FHIR value",
						message=f"Required field '{mapping.fhir_path}' not found in doc {self.doc.name if self.doc else ''}",
					)
				continue
			self._map_element(resource, mapping, value)

		return resource

	def _map_element(self, resource, mapping, value):
		path_parts = mapping.fhir_path.split(".")[1:]
		current = resource

		for i, part in enumerate(path_parts):
			is_last = i == len(path_parts) - 1

			if isinstance(current, list):
				if not current:
					current.append({})
				current = current[-1]

			if is_last:
				if is_empty(value):
					return
				if mapping.max == "*":
					if part in current and not isinstance(current[part], list):
						current[part] = [current[part]]
					else:
						current.setdefault(part, [])

					if isinstance(value, list):
						for v in value:
							if not is_empty(v) and v not in current[part]:
								current[part].append(v)
					elif not is_empty(value) and value not in current[part]:
						current[part].append(value)
				else:
					current[part] = value
			else:
				if mapping.max == "*" and isinstance(current.get(part), list):
					if not current[part]:
						current[part].append({})
					current = current[part][-1]
				else:
					current = current.setdefault(part, {})

	def _get_value(self, mapping):
		if not mapping.fhir_datatype:
			return None

		datatype = frappe.get_doc("FHIR Datatype", mapping.fhir_datatype)

		if datatype.is_primitive:
			if mapping.default_value is not None:
				return mapping.default_value
			if self.doc and mapping.frappe_field:
				return self.doc.get(mapping.frappe_field)
			return None

		builder = FHIRDatatypeBuilder(self.mapping, self.mapping.map, self.doc)
		return builder.build(mapping.fhir_path, mapping.fhir_datatype)


def is_empty(value):
	"""Recursively check if a value is effectively empty (None, empty dict/list, or nested empty structures)."""
	if value is None:
		return True
	if isinstance(value, str) and not value.strip():
		return True
	if isinstance(value, (list, tuple, set)):
		return all(is_empty(v) for v in value)
	if isinstance(value, dict):
		return all(is_empty(v) for v in value.values())
	return False


@frappe.whitelist()
def generate_fhir_resource(frappe_doc):
	mapping_doc = frappe.get_doc(
		"FHIR Resource Map", {"frappe_doctype": frappe_doc.doctype, "is_active": 1}
	)  # TODO: filters
	if not mapping_doc:
		frappe.throw(_(f"FHIR mapping for {frappe_doc.doctype} {frappe_doc.name} not found"))

	generator = FHIRResourceGenerator(mapping_doc, frappe_doc)
	fhir_resource = generator.generate()

	return fhir_resource, mapping_doc.name


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
	):  # TODO: optimize
		return

	fhir_data, map_name = generate_fhir_resource(frappe_doc)

	key = {
		"frappe_doctype": frappe_doc.doctype,
		"frappe_document": frappe_doc.name,
		"fhir_resource_map": map_name,
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
