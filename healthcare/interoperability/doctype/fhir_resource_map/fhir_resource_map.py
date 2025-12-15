# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from healthcare.interoperability.fhir_engine.fhir_generator import generate_fhir_resource
from healthcare.interoperability.fhir_engine.fhir_resource_generator import FHIRResourceGenerator


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
		self._overlay_cache = None

		self.validate_element_map()

	@frappe.whitelist()
	def save_mapped_elements(self, elements):
		self.set("map", [])

		for el in elements:
			# Validate child table field for max *
			# Disabled to allow single values
			# if el.get("max") == "*" and el.get("frappe_field"):
			# 	df = frappe.get_meta(self.frappe_doctype).get_field(el.get("frappe_field"))
			# 	is_child_table = df and df.fieldtype == "Table"
			#
			# 	if not is_child_table:
			# 		frappe.throw(
			# 			f"FHIR element '{el.get('fhir_path')}' is repeating (max='*'), "
			# 			f"but Resource Map points to a single field '{el.get('frappe_field')}'. "
			# 			"Use a child table instead."
			# 		)

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
		frappe_doc = frappe.get_doc(self.frappe_doctype, docname)
		return generate_fhir_resource(self, frappe_doc)

	@frappe.whitelist()
	def preview_fhir_resource(self, docname, show_errors=False):
		frappe_doc = frappe.get_doc(self.frappe_doctype, docname)
		generator = FHIRResourceGenerator(self, frappe_doc)
		resource_json = generator.generate()
		return resource_json

	@frappe.whitelist()
	def overlay_structure_definitions(self, max_datatype_depth=2):
		"""
		Build overlay + populate element map.
		"""
		max_depth = None
		if max_datatype_depth is not None:
			try:
				max_depth = cint(max_datatype_depth)
			except Exception:
				max_depth = None

		overlay_map = self.build_structure_definition_overlay(
			max_datatype_depth=max_depth,
		)
		self.populate_element_map_from_overlay(overlay_map)

		self.save(ignore_permissions=True)

		return [overlay_map[path] for path in sorted(overlay_map.keys())]

	def get_structure_definition_names(self):
		names = []

		if self.fhir_structure_def:
			names.append(self.fhir_structure_def)

		for row in self.fhir_profiles or []:
			if row.fhir_structure_definition:
				names.append(row.fhir_structure_definition)

		return names

	def get_overlay_map(self):
		if hasattr(self, "_overlay_cache") and self._overlay_cache is not None:
			return self._overlay_cache

		# Default depth for internal use (e.g. validate_element_map)
		self._overlay_cache = self.build_structure_definition_overlay()
		return self._overlay_cache

	def build_structure_definition_overlay(
		self, structure_definition_names=None, max_datatype_depth=None
	):
		"""
		Build overlay from base StructureDefinition + profiles.
		"""
		if not structure_definition_names:
			structure_definition_names = self.get_structure_definition_names()

		if not structure_definition_names:
			frappe.throw("At least one FHIR Structure Definition is required")

		overlay_by_path = {}

		for structure_definition_name in structure_definition_names:
			structure_definition = frappe.get_doc(
				"FHIR Structure Definition",
				structure_definition_name,
			)

			for element_row in structure_definition.element_paths or []:
				element_path = element_row.get("fhir_path") or element_row.get("path")
				if not element_path:
					continue

				incoming = element_row.as_dict()
				incoming["source_structure_definition"] = structure_definition_name

				datatype_value = incoming.get("fhir_datatype") or incoming.get("datatype")
				if datatype_value:
					incoming["fhir_datatype"] = datatype_value

				if element_path not in overlay_by_path:
					overlay_by_path[element_path] = incoming
				else:
					current = overlay_by_path[element_path]
					overlay_by_path[element_path] = self.apply_most_restrictive_element(
						current,
						incoming,
					)

		overlay_by_path = self.expand_complex_datatypes(
			overlay_by_path,
			max_datatype_depth=max_datatype_depth,
		)

		return overlay_by_path

	def expand_complex_datatypes(self, overlay_map, max_datatype_depth=None):
		"""
		Take an overlay_map { fhir_path -> meta } and expand complex datatypes
		using FHIR Datatype Element definitions.
		"""

		# Interpret depth
		if max_datatype_depth is not None:
			try:
				max_datatype_depth = int(max_datatype_depth)
			except Exception:
				max_datatype_depth = None

		if max_datatype_depth is not None and max_datatype_depth <= 0:
			# Explicitly disable expansion
			return overlay_map

		if max_datatype_depth is None:
			max_datatype_depth = 2

		datatype_elements_by_type = self.get_datatype_elements_index()
		primitive_datatypes = self.get_primitive_datatype_names()

		NON_EXPANDING_TYPES = {
			"Extension",
			"Element",
			"BackboneElement",  # optional, remove if you want to expand it
			"Narrative",
			"Resource",
			"ElementDefinition",
			"xhtml",
		}

		# seed ancestry + depth for existing overlay entries (from StructureDefinitions)
		for path, meta in overlay_map.items():
			datatype = meta.get("datatype")
			if datatype:
				meta["_datatype_ancestry"] = [datatype]
				meta["_datatype_depth"] = 1

		previous_count = -1

		while previous_count != len(overlay_map):
			previous_count = len(overlay_map)
			new_entries = {}

			for parent_path, meta in list(overlay_map.items()):
				datatype = meta.get("fhir_datatype") or meta.get("datatype")
				if not datatype:
					continue

				# Skip primitives entirely
				if datatype in primitive_datatypes:
					continue

				# Skip meta-ish recursive types
				if datatype in NON_EXPANDING_TYPES:
					continue

				elements = datatype_elements_by_type.get(datatype)
				if not elements:
					continue

				ancestry = meta.get("_datatype_ancestry") or [datatype]
				try:
					depth = int(meta.get("_datatype_depth") or len(ancestry) or 0)
				except Exception:
					depth = len(ancestry) or 0

				# Hard-limit nesting depth per path
				if depth >= max_datatype_depth:
					continue

				for element in elements:
					element_name = element.get("element_name") or element.get("fhir_path") or element.get("path")
					if not element_name:
						continue

					# root row "CodeableConcept" etc – skip
					if element_name == datatype:
						continue

					# expect "CodeableConcept.coding", "CodeableConcept.coding.code", etc.
					if not element_name.startswith(datatype + "."):
						# if datatype elements are stored as suffixes ("coding.code"),
						# then adjust this block to prepend datatype before checking.
						continue

					suffix = element_name[len(datatype) + 1 :]
					expanded_path = f"{parent_path}.{suffix}"

					# skip if we already have this path
					if expanded_path in overlay_map or expanded_path in new_entries:
						continue

					child_meta = element.copy()
					child_meta["fhir_path"] = expanded_path

					child_datatype = child_meta.get("fhir_datatype") or child_meta.get("datatype")
					if child_datatype:
						child_meta["fhir_datatype"] = child_datatype
						child_meta["datatype"] = child_datatype

					child_ancestry = list(ancestry)

					if child_datatype:
						# Cycle: datatype already seen on this path
						if child_datatype in child_ancestry:
							# e.g. Identifier -> Reference -> Identifier, or Extension -> Extension
							continue

						child_ancestry.append(child_datatype)
						child_meta["_datatype_ancestry"] = child_ancestry

						child_depth = depth + 1
						child_meta["_datatype_depth"] = child_depth

						if child_depth > max_datatype_depth:
							continue

					if not child_meta.get("source_structure_definition"):
						child_meta["source_structure_definition"] = f"Datatype:{datatype}"

					new_entries[expanded_path] = child_meta

			if new_entries:
				if len(overlay_map) + len(new_entries) > 20000:
					sample_keys = list(new_entries.keys())[:20]
					frappe.log_error(
						message="\n".join(sample_keys),
						title="FHIR datatype expansion: new entries (sample)",
					)
				overlay_map.update(new_entries)

		return overlay_map

	def get_datatype_elements_index(self):
		"""
		Return:
		{
		        "CodeableConcept": [
		                        { element_name: "CodeableConcept.coding", fhir_datatype: "Coding", ... },
		                        { element_name: "CodeableConcept.text",   fhir_datatype: "string", ... },
		                        ...
		        ],
		        "Identifier": [ ... ],
		        ...
		}
		"""

		cache = frappe.cache()
		cached = cache.get_value("fhir_datatype_elements_index")
		if cached:
			return cached

		index = {}

		element_rows = frappe.get_all(
			"FHIR Datatype Element",
			fields=[
				"name",
				"parent",
				"element_name",
				"fhir_datatype",
				"is_choice_type",
				"min",
				"max",
				"short",
				"definition",
				"valueset_url",
				"binding_strength",
				"target_profiles",
			],
		)

		for row in element_rows:
			datatype_name = row.get("parent")
			if not datatype_name:
				continue

			if datatype_name not in index:
				index[datatype_name] = []

			index[datatype_name].append(row)

		cache.set_value("fhir_datatype_elements_index", index)
		return index

	def apply_most_restrictive_element(self, current_element, incoming_element):
		result = dict(current_element)

		result["min"] = self.choose_higher_min(
			current_element.get("min"),
			incoming_element.get("min"),
		)

		result["max"] = self.choose_lower_max(
			current_element.get("max"),
			incoming_element.get("max"),
		)

		result["binding_strength"] = self.choose_stricter_binding(
			current_element.get("binding_strength"),
			incoming_element.get("binding_strength"),
		)

		result["fhir_datatype"] = self.intersect_datatypes(
			current_element.get("fhir_datatype"),
			incoming_element.get("fhir_datatype"),
			element_path=current_element.get("fhir_path") or current_element.get("path"),
		)

		for fieldname in (
			"short",
			"definition",
			"valueset_url",
			"target_profiles",
		):
			incoming_value = incoming_element.get(fieldname)
			current_value = current_element.get(fieldname)
			result[fieldname] = incoming_value or current_value

		if incoming_element.get("source_structure_definition"):
			result["source_structure_definition"] = incoming_element["source_structure_definition"]

		return result

	def choose_higher_min(self, current_min, incoming_min):
		try:
			current_value = int(current_min or 0)
			incoming_value = int(incoming_min or 0)
			return max(current_value, incoming_value)
		except Exception:
			return incoming_min or current_min

	def choose_lower_max(self, current_max, incoming_max):
		if current_max == "0" or incoming_max == "0":
			return "0"

		if current_max == "*" and incoming_max:
			return incoming_max

		if incoming_max == "*" and current_max:
			return current_max

		try:
			current_value = int(current_max)
			incoming_value = int(incoming_max)
			return str(min(current_value, incoming_value))
		except Exception:
			return incoming_max or current_max

	def choose_stricter_binding(self, current_binding, incoming_binding):
		order = ["example", "preferred", "extensible", "required"]

		if not current_binding:
			return incoming_binding
		if not incoming_binding:
			return current_binding

		try:
			current_index = order.index(current_binding)
		except ValueError:
			current_index = -1

		try:
			incoming_index = order.index(incoming_binding)
		except ValueError:
			incoming_index = -1

		if current_index == -1 and incoming_index == -1:
			return incoming_binding or current_binding

		if incoming_index >= current_index:
			return incoming_binding

		return current_binding

	def intersect_datatypes(self, current_datatype, incoming_datatype, element_path=None):
		if not current_datatype and not incoming_datatype:
			return None

		if not current_datatype:
			return incoming_datatype

		if not incoming_datatype:
			return current_datatype

		current_set = {value.strip() for value in current_datatype.split(",") if value and value.strip()}
		incoming_set = {
			value.strip() for value in incoming_datatype.split(",") if value and value.strip()
		}

		common = current_set.intersection(incoming_set)

		if not common:
			message = "FHIR datatype conflict while overlaying StructureDefinitions"
			if element_path:
				message += " at element {0}".format(element_path)
			message += ": {0} vs {1}".format(current_datatype, incoming_datatype)

			frappe.throw(message, title="Invalid FHIR StructureDefinition Overlay")

		return ",".join(sorted(common))

	def populate_element_map_from_overlay(self, overlay_map):
		"""
		Rebuild element_map rows from the overlay:

		- One row per element path in overlay_map
		- Structural fields are taken from overlay
		- Mapping fields (frappe_field, fixed_value, default_value, pattern_value)
		  are preserved when the same path already existed
		- Paths no longer present in overlay are dropped
		"""

		previous_rows_by_path = {}

		for row in self.map or []:
			if row.fhir_path:
				previous_rows_by_path[row.fhir_path] = row.as_dict()

		self.set("map", [])

		for element_path in sorted(overlay_map.keys()):
			meta = overlay_map[element_path] or {}
			previous = previous_rows_by_path.get(element_path) or {}

			row_data = {}

			row_data["fhir_path"] = element_path
			row_data["datatype"] = meta.get("fhir_datatype") or meta.get("datatype")
			row_data["fhir_datatype"] = meta.get("fhir_datatype") or meta.get("datatype")
			row_data["is_choice_type"] = (
				True if row_data.get("datatype") and "," in row_data.get("datatype") else False
			)
			row_data["min"] = meta.get("min")
			row_data["max"] = meta.get("max")
			row_data["binding_strength"] = meta.get("binding_strength")
			row_data["short"] = meta.get("short")
			row_data["definition"] = meta.get("definition")
			row_data["valueset_url"] = meta.get("valueset_url")
			row_data["target_profiles"] = meta.get("target_profiles")
			row_data["is_required"] = int(meta.get("min") or 0) > 0

			for fieldname in (
				"frappe_field",
				"fixed_value",
				"default_value",
				"pattern_value",
			):
				row_data[fieldname] = previous.get(fieldname)

			self.append("map", row_data)

	def get_primitive_datatype_names(self):
		cache = frappe.cache()
		cached = cache.get_value("fhir_primitive_datatype_names")
		if cached:
			return set(cached)

		names = frappe.get_all(
			"FHIR Datatype",
			filters={"is_primitive": 1},
			pluck="name",
		)
		cache.set_value("fhir_primitive_datatype_names", names)
		return set(names)

	def is_primitive_datatype_name(self, datatype_name):
		if not datatype_name:
			return False
		primitive_names = self.get_primitive_datatype_names()
		return datatype_name in primitive_names

	def validate_element_map(self):
		overlay_map = self.get_overlay_map()

		if not overlay_map:
			frappe.throw("Cannot validate mapping without StructureDefinition overlay")

		paths_seen = set()

		for row in self.map or []:
			if not row.fhir_path:
				frappe.throw("FHIR path is mandatory in FHIR Resource Element Map")

			if row.fhir_path in paths_seen:
				frappe.throw("Duplicate mapping for FHIR path: {0}".format(row.fhir_path))

			paths_seen.add(row.fhir_path)

			self.validate_single_mapping_row(row, overlay_map.get(row.fhir_path))

		self.validate_required_elements_mapped(overlay_map, paths_seen)

	def validate_single_mapping_row(self, row, overlay_meta):
		if not overlay_meta:
			return  # if row not in overlaying profile

		errors = []
		max_cardinality = str(overlay_meta.get("max") or "").strip()
		if max_cardinality == "0":
			errors.append("Cannot map forbidden element {0} (max=0 in profile)".format(row.fhir_path))

		if overlay_meta.get("binding_strength") == "required" and not overlay_meta.get("valueset_url"):
			errors.append(
				"Element {0} has binding_strength='required' but no ValueSet URL".format(row.fhir_path)
			)

		if row.min and int(row.min) > 0:
			if self.is_primitive_datatype_name(row.datatype):
				if not any(
					[
						row.frappe_field,
						row.fixed_value,
						row.default_value,
						row.pattern_value,
					]
				):
					errors.append("Required element {0} has no value source in mapping".format(row.fhir_path))

		element_path = overlay_meta.get("fhir_path") or overlay_meta.get("path")
		if element_path and "[x]" in element_path:
			if not row.fhir_datatype:
				errors.append(
					"Choice element {0} must select a concrete datatype in mapping".format(row.fhir_path)
				)

			allowed_datatypes = set()
			if overlay_meta.get("fhir_datatype"):
				allowed_datatypes = {
					value.strip() for value in overlay_meta["fhir_datatype"].split(",") if value and value.strip()
				}

			selected_datatypes = {
				value.strip() for value in row.datatype.split(",") if value and value.strip()
			}

			if allowed_datatypes and not selected_datatypes.issubset(allowed_datatypes):
				errors.append(
					"Mapped datatype(s) {0} for {1} are not allowed by StructureDefinition ({2})".format(
						", ".join(sorted(selected_datatypes)),
						row.fhir_path,
						", ".join(sorted(allowed_datatypes)),
					)
				)

		if overlay_meta.get("target_profiles"):
			datatype = row.fhir_datatype or overlay_meta.get("fhir_datatype") or ""
			datatype_values = {value.strip() for value in datatype.split(",") if value and value.strip()}
			if "Reference" not in datatype_values:
				errors.append(
					"Element {0} has targetProfile but mapped datatype is not Reference".format(row.fhir_path)
				)

		if errors:
			msg = "\n".join(errors)
			frappe.msgprint(msg)

	def validate_required_elements_mapped(self, overlay_map, mapped_paths):
		required_unmapped = []

		for path, meta in overlay_map.items():
			datatype_name = (meta.get("datatype") or "").strip()
			if not self.is_primitive_datatype_name(datatype_name):
				continue  # enforce mapping for primitive required elements

			try:
				min_value = int(meta.get("min") or 0)
			except Exception:
				min_value = 0

			if min_value > 0 and path not in mapped_paths:
				required_unmapped.append(path)

		if required_unmapped:
			frappe.throw(
				"Required FHIR elements are not mapped: {0}".format(", ".join(sorted(required_unmapped)))
			)
