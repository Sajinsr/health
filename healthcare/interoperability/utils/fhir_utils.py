import json
import os
import tarfile
import tempfile
from pathlib import Path

import frappe
from frappe import _
from frappe.utils.file_manager import get_file_path


def import_structure_definitions_from_package(package_tarball, version_name, profile_name=None):
	"""
	unpack a .tgz/.tar.gz FHIR package
	read all StructureDefinition JSON files
	create/update corresponding "FHIR Structure Definition" documents
	"""

	file_path = get_file_path(package_tarball)
	if not file_path or not os.path.exists(file_path):
		frappe.throw(_(f"Cannot find FHIR package on disk '{file_path}'"))

	# extract the tar.gz at tempdir
	with tempfile.TemporaryDirectory() as tmpdir:
		try:
			with tarfile.open(file_path, "r:gz") as tar:
				tar.extractall(path=tmpdir)
		except tarfile.ReadError:
			frappe.log_error(
				message=f"Failed to open as tar.gz: {file_path}", title="FHIR Package Extraction Error"
			)
			frappe.throw(_(f"Uploaded file '{file_path}' is not a valid .tgz / .tar.gz archive file."))

		# npm packages usually expand to a “package/” root.
		pkg_root = Path(tmpdir) / "package"
		if not pkg_root.exists():
			frappe.throw("Invalid FHIR package layout, missing 'package/' folder after extraction.")

		# 5) Determine fhir_version string from package.json (for cross‐checking)
		pkg_json_path = pkg_root / "package.json"
		if not pkg_json_path.exists():
			frappe.throw("Invalid FHIR package: missing 'package/package.json'.")
		with open(pkg_json_path, "r", encoding="utf-8") as f:
			pkg_meta = json.load(f)

		# Optional: Verify that this package’s fhirVersion matches fhir_version_doc.fhir_version
		declared_versions = pkg_meta.get("fhirVersions", [])
		if declared_versions:
			declared_version = declared_versions[0]
			if declared_version != version_name:
				frappe.log_error(
					message=f"Declared version '{declared_version}' and FHIR Version '{version_name}' does not match, \
						but proceeding with Structure Definition import.",
					title="FHIR Version Mismatch",
				)

		# TODO: traverse .json files under pkg_root/StructureDefinition
		json_paths = list(pkg_root.rglob("*.json"))

		if not json_paths:
			frappe.throw("No JSON files found in the FHIR package.")
		else:
			frappe.log_error(f"{pkg_root}\n{json_paths}")

		# all set, start import
		for sd_file in json_paths:
			try:
				with open(sd_file, "r", encoding="utf-8") as f:
					sd_data = json.load(f)
			except Exception as e:
				frappe.log_error(
					message=f"Failed to load JSON from '{sd_file}': {e}",
					title="Structure Definition json load Error",
				)
				continue

			# verify read data
			if sd_data.get("resourceType") != "StructureDefinition":
				frappe.log_error(
					message=f"Failed to load json from '{sd_file}'.\n{json.dumps(sd_data, indent=1)}",
					title="Invalid JSON found, skipping",
				)
				continue

			sd_url = sd_data.get("url")
			if not sd_url:
				frappe.log_error(
					message=f"Structure Definition '{sd_file}' has no 'url' field.\n{json.dumps(sd_data, indent=1)}",
					title="Structure Definition does not contain url property",
				)
				continue

			existing_name = frappe.db.get_value(
				"FHIR Structure Definition",
				{"url": sd_url, "fhir_profile": profile_name, "fhir_version": version_name},
			)

			if existing_name:
				sd = frappe.get_doc("FHIR Structure Definition", existing_name)
				sd.set("element_paths", [])
				frappe.log_error(
					message=f"Structure Definition '{sd_file}' exists.\nURL: {sd_url}\n{version_name} {profile_name if profile_name else ''}",
					title="Re-importing Structure Definition",
				)
			else:
				sd = frappe.new_doc("FHIR Structure Definition")

			sd.fhir_sd = sd_data.get("id")
			sd.fhir_version = version_name
			sd.fhir_profile = profile_name if profile_name else ""
			sd.url = sd_url
			sd.kind = sd_data.get("kind").capitalize()
			sd.status = sd_data.get("status").capitalize()
			sd.sd_type = "base"
			sd.sd_version = sd_data.get("version")
			sd.publisher = sd_data.get("publisher")

			sd.sd = json.dumps(sd_data, indent=1)

			# fhir elements from snapshot
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
				if isinstance(types, list):
					if all(isinstance(t, dict) and t.get("code") for t in types):
						# if all are list of dict join values into a comma‐separated string
						row.type = ",".join([str(t.get("code")) for t in types])
					else:
						# should be list join into a comma‐separated string
						row.type = ",".join([str(t) for t in types])
				else:
					# a string
					row.type = str(types)

			try:
				sd.save(ignore_permissions=True)
			except Exception as e:
				# frappe.log_error(
				# 	message=f"Error saving FHIR Structure Definition '{sd_url}'\nTraceback:{e}\n{json.dumps(sd.as_json(), indent=1)}",
				# 	title="Could not save FHIR Structure Definition"
				# )
				continue


def yield_element_paths(sd):
	if isinstance(sd, str):
		sd = json.loads(sd)

	elements = sd.get("snapshot", {}).get("element", [])
	for el in elements:
		yield frappe._dict(
			{
				"path": el.get("path"),
				"min": el.get("min"),
				"max": el.get("max"),
				"type": ", ".join([t.get("code") for t in el.get("type", []) if "code" in t]),
			}
		)
