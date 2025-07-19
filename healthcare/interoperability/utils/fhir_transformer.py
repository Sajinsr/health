import re

import frappe
from frappe import _

COMPLEX_FHIR_DATATYPES = [
	"HumanName",
	"Address",
	"ContactPoint",
	"Reference",
	"Period",
	"Identifier",
	"CodeableConcept",
	"Coding",
	"Attachment",
	"Signature",
	"Quantity",
	"Money",
	"Ratio",
	"SampledData",
	"Age",
	"Distance",
	"Count",
	"Range",
	"Duration",
	"Timing",
	"Annotation",
	"Narrative",
	"Extension",
	"BackboneElement",
	"ElementDefinition",
	"Meta",
	"Dosage",
	"RelatedArtifact",
	"UsageContext",
	"DataRequirement",
	"ParameterDefinition",
	"Expression",
	"TriggerDefinition",
]


class FHIRResourceGenerator:
	def __init__(self, resource_map, mappings, frappe_doc):
		self.resource_map = resource_map
		self.mappings = mappings
		self.doc = frappe_doc

	def transform(self):
		resource = {"resourceType": self.resource_map.resource_type}
		for mapping in self.mappings:
			value = self._extract_value(mapping)
			if value is None:
				continue
			self._assign_to_resource(resource, mapping.fhir_path, value, mapping)

		narrative_template = self._get_narrative_template()
		if narrative_template:
			resource["text"] = self._generate_narrative(resource, narrative_template)

		return resource

	def _extract_value(self, mapping):
		if mapping.fixed_value:
			return mapping.fixed_value

		value = self.doc.get(mapping.frappe_field)
		if value is None:
			value = mapping.default_value

		if mapping.pattern_value and value:
			if not re.fullmatch(mapping.pattern_value, str(value)):
				frappe.log_error(_("Value does not match pattern"), f"{mapping.fhir_path}: {value}")
				return None

		if mapping.valueset_url and mapping.binding_strength == "required":
			allowed = self._get_valueset_codes(mapping.valueset_url)
			if value not in allowed:
				frappe.log_error(_("Invalid ValueSet code"), f"{mapping.fhir_path}: {value}")
				return None

		if mapping.fhir_datatype in self._complex_builders():
			return self._complex_builders()[mapping.fhir_datatype](value)

		return value

	def _assign_to_resource(self, resource, path, value, mapping):
		parts = path.removeprefix(self.resource_map.resource_type + ".").split(".")
		current = resource
		for part in parts[:-1]:
			current = current.setdefault(part, [{}])[0]
		leaf = parts[-1]

		if mapping.max == "*":
			current.setdefault(leaf, []).append(value)
		else:
			current[leaf] = value

	def _get_valueset_codes(self, url):
		return ["male", "female", "unknown", "other"]

	def _complex_builders(self):
		return {
			"HumanName": self._build_human_name,
			"Address": self._build_address,
			"Identifier": self._build_identifier,
		}

	def _build_human_name(self, value):
		return {"given": [value]} if isinstance(value, str) else value

	def _build_address(self, value):
		return {"line": [value]} if isinstance(value, str) else value

	def _build_identifier(self, value):
		return {"value": value} if isinstance(value, str) else value

	def _get_narrative_template(self):
		if not self.resource_map.narrative_template:
			return None
		tc_doc = frappe.get_doc("Terms and Conditions", self.resource_map.narrative_template)
		return tc_doc.terms

	def _generate_narrative(self, resource, narrative_template):
		html = frappe.render_template(narrative_template, {"resource": resource})
		print(html)
		return {"status": "generated", "div": html}
