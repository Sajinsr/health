import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from healthcare.interoperability.fhir_engine.fhir_resource_generator import FHIRResourceGenerator

from .test_helpers import FHIRResourceTestMixin
from .test_records.patient_map import patient_map


class TestPatientFHIRResource(IntegrationTestCase, FHIRResourceTestMixin):
	def setUp(self):
		frappe.db.sql("""delete from `tabFHIR Resource Map`""")
		self.patient = frappe.get_doc(
			{
				"doctype": "Patient",
				"patient_name": "Jane H. Doe",
				"first_name": "Jane",
				"last_name": "Doe",
				"mobile": "111111111",
				"sex": "Female",
				"dob": "2000-07-19",
			}
		).insert(ignore_permissions=True)

		if not frappe.db.exists("FHIR Version", "R4.0.1"):
			frappe.get_doc(
				{
					"doctype": "FHIR Version",
					"fhir_version": "R4.0.1",
					"url": "https://hl7.org/fhir/R4",
					"is_active": 1,
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("FHIR Structure Definition", "Patient-4.0.1-R4.0.1"):
			try:
				frappe.get_doc(
					{
						"doctype": "FHIR Structure Definition",
						"fhir_structure_def": "Patient-4.0.1",
						"structure_def_type": "Resource",
						"kind": "Resource",
						"status": "Active",
						"url": "https://hl7.org/fhir/StructureDefinition/Patient",
						"fhir_version": "R4.0.1",
						"fhir_sd": "Patient",
						"sd_version": "4.0.1",
					}
				).insert(ignore_permissions=True)
			except Exception as e:
				print("FHIR Structure Definition insert failed:", e)

		if not frappe.db.exists("Terms and Conditions", "Patient Narrative"):
			frappe.get_doc(
				{
					"doctype": "Terms and Conditions",
					"title": "Patient Narrative",
					"terms": "<p>Sample narrative template</p>",
				}
			).insert(ignore_permissions=True)
		frappe.db.commit()

		if not frappe.db.exists("FHIR Resource Map", "MAP-Patient-Patient-4.0.1-R4.0.1-R4.0.1"):
			frappe.get_doc(
				{
					"doctype": "FHIR Resource Map",
					"name": "MAP-Patient-Patient-4.0.1-R4.0.1-R4.0.1",
					"resource_type": "Patient",
					"fhir_version": "R4.0.1",
					"frappe_doctype": "Patient",
					"narrative_template": "Patient Narrative",
					"fhir_structure_def": "Patient-4.0.1-R4.0.1",
					"map": [
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.id",
							"fhir_datatype": "string",
							"frappe_field": "name",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.language",
							"fhir_datatype": "code",
							"default_value": "en",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.meta.profile",
							"fhir_datatype": "uri",
							"default_value": "https://hl7.org/fhir/StructureDefinition/Patient",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.identifier",
							"fhir_datatype": "Identifier",
							"min": "1",
							"max": "*",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.identifier.system",
							"fhir_datatype": "uri",
							"default_value": "https://marley.health/patient-id",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.identifier.value",
							"fhir_datatype": "string",
							"frappe_field": "name",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.identifier.assigner.display",
							"fhir_datatype": "string",
							"default_value": "Awesome Care",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.name",
							"fhir_datatype": "HumanName",
							"min": "1",
							"max": "*",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.name.text",
							"fhir_datatype": "string",
							"frappe_field": "patient_name",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.name.family",
							"fhir_datatype": "string",
							"frappe_field": "last_name",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.name.given",
							"fhir_datatype": "string",
							"frappe_field": "first_name",
							"min": "0",
							"max": "*",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.name.prefix",
							"fhir_datatype": "string",
							"default_value": "Ms",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.telecom",
							"fhir_datatype": "ContactPoint",
							"min": "1",
							"max": "*",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.telecom.system",
							"fhir_datatype": "code",
							"default_value": "phone",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.telecom.value",
							"fhir_datatype": "string",
							"frappe_field": "mobile",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.telecom.use",
							"fhir_datatype": "code",
							"default_value": "mobile",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.telecom.rank",
							"fhir_datatype": "positiveInt",
							"default_value": 1,
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.gender",
							"fhir_datatype": "code",
							"frappe_field": "sex",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.birthDate",
							"fhir_datatype": "date",
							"frappe_field": "dob",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.deceasedBoolean",
							"fhir_datatype": "boolean",
							"default_value": False,
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.address.line",
							"fhir_datatype": "string",
							"frappe_field": "address",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.address.city",
							"fhir_datatype": "string",
							"frappe_field": "city",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.address.postalCode",
							"fhir_datatype": "string",
							"frappe_field": "pincode",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.address.country",
							"fhir_datatype": "string",
							"frappe_field": "country",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.maritalStatus.coding.system",
							"fhir_datatype": "uri",
							"default_value": "http://hl7.org/fhir/marital-status",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.maritalStatus.coding.code",
							"fhir_datatype": "code",
							"default_value": "M",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.communication.language.coding.system",
							"fhir_datatype": "uri",
							"default_value": "urn:ietf:bcp:47",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.communication.language.coding.code",
							"fhir_datatype": "code",
							"default_value": "en",
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.communication.preferred",
							"fhir_datatype": "boolean",
							"default_value": True,
						},
						{
							"doctype": "FHIR Resource Element Map",
							"fhir_path": "Patient.managingOrganization.reference",
							"fhir_datatype": "string",
							"default_value": "Organization/HLC",
						},
					],
				}
			).insert(ignore_permissions=True)

			frappe.db.commit()

	def test_patient_resource_output(self):
		resource_map = frappe.get_doc("FHIR Resource Map", "MAP-Patient-Patient-4.0.1-R4.0.1-R4.0.1")
		generator = FHIRResourceGenerator(resource_map, self.patient)
		resource = generator.generate()

		self.assert_valid_fhir_resource(resource, "Patient")

		expected = {
			"resourceType": "Patient",
			"id": self.patient.name,
			"identifier": [
				{
					"system": "https://marley.health/patient-id",
					"value": self.patient.name,
				}
			],
			"name": [
				{
					"text": "Jane Doe",
					"family": "Doe",
					"given": ["Jane"],
					"prefix": "Ms",
				}
			],
			"telecom": [
				{
					"system": "phone",
					"value": "111111111",
					"rank": 1,
					"use": "mobile",
				}
			],
			"gender": "female",
			"birthDate": "2000-07-19",
		}

		# Loose match for expected resource structure
		for key in expected:
			self.assertIn(key, resource)
			self.assertEqual(resource[key], expected[key])

	def tearDown(self):
		for doctype in ["FHIR Version", "FHIR Structure Definition", "FHIR Resource Map"]:
			frappe.db.sql("delete from `tab{doctype}`".format(doctype=doctype))
