# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
import os
import tarfile
import tempfile
from pathlib import Path

import frappe
from frappe.utils.file_manager import get_file_path

FHIR_SYSTEM_TYPE_MAP = {
	"http://hl7.org/fhirpath/System.String": "string",
	"http://hl7.org/fhirpath/System.Boolean": "boolean",
	"http://hl7.org/fhirpath/System.Integer": "integer",
	"http://hl7.org/fhirpath/System.Decimal": "decimal",
	"http://hl7.org/fhirpath/System.Date": "date",
	"http://hl7.org/fhirpath/System.DateTime": "dateTime",
}


class FHIRPackageImporter:
	def __init__(self, package_tarball, version_name, profile_name=None):
		self.package_tarball = package_tarball
		self.version_name = version_name
		self.profile_name = profile_name
		self.temp_dir = None
		self.package_root = None

	def import_package(self):
		self._extract_archive()
		self._validate_package_contents()
		self._process_structure_definitions()

	def _extract_archive(self):
		file_path = get_file_path(self.package_tarball)
		if not file_path or not os.path.exists(file_path):
			frappe.throw(f"Cannot find FHIR package on disk '{file_path}'")

		self.temp_dir = tempfile.TemporaryDirectory()
		try:
			with tarfile.open(file_path, "r:gz") as tar:
				tar.extractall(path=self.temp_dir.name)
		except tarfile.ReadError:
			frappe.throw(f"'{file_path}' is not a valid .tgz / .tar.gz archive.")

	def _validate_package_contents(self):
		self.package_root = Path(self.temp_dir.name) / "package"
		if not self.package_root.exists():
			frappe.throw("Invalid FHIR package: missing 'package/' directory.")

		pkg_json_path = self.package_root / "package.json"
		if not pkg_json_path.exists():
			frappe.throw("Missing 'package/package.json'.")

		with open(pkg_json_path, "r", encoding="utf-8") as f:
			pkg_meta = json.load(f)

		declared_versions = pkg_meta.get("fhirVersions", [])
		if declared_versions:
			declared_version = declared_versions[0]
			if declared_version != self.version_name:
				frappe.log_error(f"Declared version '{declared_version}' vs expected '{self.version_name}'")

	def _process_structure_definitions(self):
		json_files = list(self.package_root.rglob("*.json"))
		for path in json_files:
			try:
				with open(path, "r", encoding="utf-8") as f:
					data = json.load(f)
			except Exception as e:
				frappe.log_error(f"Failed loading JSON from {path}: {e}")
				continue

			if data.get("resourceType") != "StructureDefinition":
				continue

			self._upsert_structure_definition(data)  # enqueue?

	def _upsert_structure_definition(self, sd_data):
		sd_url = sd_data.get("url")
		if not sd_url:
			return

		existing_name = frappe.db.get_value(
			"FHIR Structure Definition",
			{"url": sd_url, "fhir_profile": self.profile_name, "fhir_version": self.version_name},
		)

		if existing_name:
			sd = frappe.get_doc("FHIR Structure Definition", existing_name)
			sd.set("element_paths", [])
		else:
			sd = frappe.new_doc("FHIR Structure Definition")

		sd.fhir_sd = sd_data.get("id")
		sd.fhir_version = self.version_name
		sd.fhir_profile = self.profile_name or ""
		sd.url = sd_url
		sd.kind = (sd_data.get("kind") or "").capitalize()
		sd.status = (sd_data.get("status") or "").capitalize()
		sd.sd_type = "base"
		sd.sd_version = sd_data.get("version")
		sd.publisher = sd_data.get("publisher")
		sd.sd = json.dumps(sd_data, indent=1)

		self._populate_element_paths(sd, sd_data)

		try:
			sd.save(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(f"Failed to save Structure Definition {sd_url}: {e}")

	def _populate_element_paths(self, sd, sd_data):
		elements = sd_data.get("snapshot", {}).get("element", [])
		for e in elements:
			row = sd.append("element_paths", {})
			row.short = e.get("short")
			row.definition = e.get("definition")
			row.path = e.get("path")
			row.min = e.get("min", 0)
			row.max = e.get("max")
			row.is_required = e.get("min", 0) > 0
			row.mapping = json.dumps(e.get("mapping"), indent=1)

			types = e.get("type") or e.get("types") or []
			normalized_types = []
			for t in types:
				code = t.get("code") if isinstance(t, dict) else t
				code = FHIR_SYSTEM_TYPE_MAP.get(code, code)
				normalized_types.append(code)

			if len(normalized_types) == 1:
				row.datatype = normalized_types[0]
			elif normalized_types:
				row.datatype = ",".join(normalized_types)
				row.is_choice_type = 1

			# TODO: required?
			if any(
				isinstance(t, dict) and t.get("code") == "Reference" and t.get("targetProfile") for t in types
			):
				target_profiles = []
				for t in types:
					if isinstance(t, dict) and t.get("code") == "Reference":
						target_profiles.extend(t.get("targetProfile") or [])
				row.target_profiles = json.dumps(target_profiles, indent=1)

			binding = e.get("binding")
			if binding:
				row.valueset_url = binding.get("valueSet")
				row.binding_strength = binding.get("strength")

			element_prefix_map = {
				"fixed": "fixed_value",
				"pattern": "pattern_value",
				"defaultValue": "default_value",
			}

			for key, value in e.items():
				if value is not None and key.startswith(tuple(element_prefix_map.keys())):
					val = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
					for prefix, fieldname in element_prefix_map.items():
						if key.startswith(prefix):
							setattr(row, fieldname, val)
							break
