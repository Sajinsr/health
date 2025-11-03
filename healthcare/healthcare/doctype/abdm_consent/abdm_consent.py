# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

from datetime import datetime, timedelta

import json
import os

import frappe
from frappe.model.document import Document

from healthcare.regional.india.abdm.utils import (
	generate_unique_id,
	get_abdm_settings,
	get_token_for_hiecm,
)

import base64

from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes, serialization



class ABDMConsent(Document):
	def validate(self):
		if self.data_push_url and self.key_material and self.transaction_id:
			settings = get_abdm_settings()
			if not settings or not settings.consent_base_url:
				frappe.throw(
					title="Configuration Missing",
					msg="Consent Management Base URL not configured in ABDM Settings.",
				)

			# auth_token = get_token_for_hiecm()

			# if not auth_token or not auth_token.get("accessToken"):
			# 	frappe.throw(
			# 		title="Unable to fetch valid access token",
			# 		msg=f"Consent Management Base URL not configured in ABDM Settings.<br><br>Traceback: {auth_token.get('traceback')}",
			# 	)

			# auth_prefix = "Bearer " if auth_token.get("tokenType", "").lower() == "bearer" else ""
			# authorization = auth_prefix + auth_token.get("accessToken")

			# headers = {
			# 	"Content-Type": "application/json",
			# 	"REQUEST-ID": generate_unique_id(),
			# 	"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
			# 	"X-CM-ID": settings.x_cm_id,
			# 	"Authorization": authorization,
			# }

			payload = {
				"pageNumber": 0,
				"pageCount": 1,
				"transactionId": self.transaction_id,
				"entries": self.build_entries(),
				# "keyMaterial": self.get_key_material(),
			}

	def build_entries(self):
		"""
		[
			{
				"content": "Encrypted content of data packaged in FHIR bundle",
				"media": "mimetype of the content.",
				"checksum": "string",
				"careContextReference": "1931-nd2"
			}
		]
		"""

		if self.care_contexts:
			care_contexts = json.loads(self.care_contexts or "{}")
			consent_detail = json.loads(self.consent_detail or "{}")
			hi_types = consent_detail.get("hiTypes") or []

			documents_details = []
			for item in care_contexts:
				details = get_document_details(item, hi_types)

				if details:
					documents_details.append(details)

			bundle = {}
			if documents_details:
				bundle = build_fhir_bundle(documents_details)

			print("\n\n\n111", bundle)

			encrypted_bundle_details = None
			if self.key_material:
				encrypted_bundle_details = get_encrypted_bundle(bundle, self.key_material)

			if encrypted_bundle_details:
				print("\n\n2222", encrypted_bundle_details)



def get_document_details(item, hi_types=[]):
	item_ref = item.get("careContextReference")

	if not item_ref:
		return

	if not hi_types or len(hi_types) == 0:
		hi_types = [
			"Prescription",
			"DiagnosticReport",
			"OPConsultation",
			"DischargeSummary",
			"ImmunizationRecord",
			"HealthDocumentRecord",
			"WellnessRecord",
			"Invoice",
		]

	doctype_map = {
		"OPConsultation": "Patient Encounter",
		"Prescription": "Medication Request",
		"WellnessRecord": "Therapy Session",
		"DiagnosticReport": "Diagnostic Report",
		"DischargeSummary": "Discharge Summary",
		"HealthDocumentRecord": "Patient Medical Record",
		"Invoice": "Sales Invoice",
	}

	doc_details = {}
	for type in hi_types:
		doc_exists = frappe.db.exists(doctype_map[type], item_ref)

		if doc_exists:
			doc_details.update({"doctype": doctype_map[type], "docname": item_ref})
			break

	return doc_details


def build_fhir_bundle(documents_details):
	"""
	Builds a FHIR Bundle for given document details
	Args:
		documents_details: List of dicts with `doctype` and `docname`
	Returns:
		dict: FHIR Bundle object (ready for encryption)
	"""

	from frappe.utils import get_url

	bundle = {
		"resourceType": "Bundle",
		"type": "document",
		"identifier": {"system": get_url(), "value": generate_unique_id()},
		"timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
		"entry": [],
	}

	for item in documents_details:
		doc = frappe.get_doc(item.get("doctype"), item.get("docname"))

		resource_data = get_resource(doc)
		entries = []
		if resource_data:
			entries.append(resource_data)
		bundle["entry"] = entries

	return bundle


def get_resource(doc):
	data = {}
	if doc.doctype == "Patient Encounter":
		data = generate_fhir_composition(doc.name)
	# data = {
	# 	"fullUrl": "urn:uuid:HLC-ENC-2025-00014",
	# 	"resource": {
	# 		"resourceType": "Composition",
	# 		"id": "HLC-ENC-2025-00014",
	# 		"meta": {
	# 			"versionId": "1",
	# 			"lastUpdated": "2025-10-27T15:33:06+05:30",
	# 			"profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/OPConsultRecord"],
	# 		},
	# 		"language": "en-IN",
	# 		"identifier": {"system": "https://ndhm.in/phr", "value": "HLC-ENC-2025-00014"},
	# 		"status": "final",
	# 		"type": {
	# 			"coding": [
	# 				{
	# 					"system": "http://snomed.info/sct",
	# 					"code": "371530004",
	# 					"display": "Clinical consultation report",
	# 				}
	# 			],
	# 			"text": "Clinical Consultation report",
	# 		},
	# 		"subject": {"reference": "urn:uuid:patient-sajin", "display": "Sajin"},
	# 		"encounter": {"reference": "urn:uuid:HLC-ENC-2025-00014", "display": "Encounter"},
	# 		"date": "2025-10-27T15:33:06+05:30",
	# 		"author": [
	# 			{"reference": "urn:uuid:HLC-PRAC-2020-00002", "display": "Dr. Rucha Mahabal"}
	# 		],
	# 		"title": "Consultation Report",
	# 		"custodian": {"reference": "urn:uuid:CH-Centre", "display": "CH Centre"},
	# 		"section": [
	# 			{
	# 				"title": "Chief complaints",
	# 				"code": {
	# 					"coding": [
	# 						{
	# 							"system": "http://snomed.info/sct",
	# 							"code": "422843007",
	# 							"display": "Chief complaint section",
	# 						}
	# 					]
	# 				},
	# 				"entry": [{"reference": "urn:uuid:symptom-cold", "display": "Cold"}],
	# 			},
	# 			{
	# 				"title": "Medical History",
	# 				"code": {
	# 					"coding": [
	# 						{
	# 							"system": "http://snomed.info/sct",
	# 							"code": "371529009",
	# 							"display": "History and physical report",
	# 						}
	# 					]
	# 				},
	# 				"entry": [{"reference": "urn:uuid:diagnosis-covid19", "display": "COVID-19"}],
	# 			},
	# 			{
	# 				"title": "Investigation Advice",
	# 				"code": {
	# 					"coding": [
	# 						{
	# 							"system": "http://snomed.info/sct",
	# 							"code": "721963009",
	# 							"display": "Order document",
	# 						}
	# 					]
	# 				},
	# 				"entry": [
	# 					{"reference": "urn:uuid:labtest-lipidprofile", "display": "LIPID PROFILE"},
	# 					{
	# 						"reference": "urn:uuid:labtest-cbc",
	# 						"display": "Complete Blood Count (CBC)",
	# 					},
	# 				],
	# 			},
	# 			{
	# 				"title": "Medications",
	# 				"code": {
	# 					"coding": [
	# 						{
	# 							"system": "http://snomed.info/sct",
	# 							"code": "721912009",
	# 							"display": "Medication summary document",
	# 						}
	# 					]
	# 				},
	# 				"entry": [
	# 					{
	# 						"reference": "urn:uuid:medication-aceclofenac",
	# 						"display": "Aceclofenac 100mg Tablet, 0-0-1 for 1 Day",
	# 					},
	# 					{
	# 						"reference": "urn:uuid:medication-azythromycin",
	# 						"display": "Azythromycin 100mg Tablet, 1-1-1 for 2 Day",
	# 					},
	# 				],
	# 			},
	# 			{
	# 				"title": "Procedure",
	# 				"code": {
	# 					"coding": [
	# 						{
	# 							"system": "http://snomed.info/sct",
	# 							"code": "371525003",
	# 							"display": "Clinical procedure report",
	# 						}
	# 					]
	# 				},
	# 				"entry": [{"reference": "urn:uuid:procedure-covid19", "display": "Covid 19"}],
	# 			},
	# 			{
	# 				"title": "Therapies",
	# 				"code": {
	# 					"coding": [
	# 						{
	# 							"system": "http://snomed.info/sct",
	# 							"code": "736271009",
	# 							"display": "Outpatient care plan",
	# 						}
	# 					]
	# 				},
	# 				"entry": [
	# 					{
	# 						"reference": "urn:uuid:therapy-upperlimb",
	# 						"display": "Intensive Upper Limb Training - 2 sessions",
	# 					},
	# 					{
	# 						"reference": "urn:uuid:therapy-rehab",
	# 						"display": "Rehab Foundation - 3 sessions",
	# 					},
	# 				],
	# 			},
	# 			{
	# 				"title": "Codification Table",
	# 				"code": {
	# 					"coding": [
	# 						{
	# 							"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
	# 							"code": "CPT4",
	# 							"display": "Current Procedural Terminology",
	# 						}
	# 					]
	# 				},
	# 				"entry": [
	# 					{
	# 						"reference": "urn:uuid:codification-cpt4",
	# 						"display": "Procedures - medical, surgical, and diagnostic services",
	# 					}
	# 				],
	# 			},
	# 		],
	# 	},
	# }

	return data


def generate_fhir_composition(encounter_id):
	"""Generate FHIR Composition JSON from Patient Encounter"""
	encounter = frappe.get_doc("Patient Encounter", encounter_id)

	def urn(resource_type, name):
		return f"urn:uuid:{resource_type}-{name.replace(' ', '').lower()}"

	# Current timestamp in ISO format
	last_updated = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+05:30")

	# Base composition
	composition = {
		"fullUrl": f"urn:uuid:{encounter.name}",
		"resource": {
			"resourceType": "Composition",
			"id": encounter.name,
			"meta": {
				"versionId": "1",
				"lastUpdated": last_updated,
				"profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/OPConsultRecord"],
			},
			"language": "en-IN",
			"identifier": {"system": "https://ndhm.in/phr", "value": encounter.name},
			"status": "final",
			"type": {
				"coding": [
					{
						"system": "http://snomed.info/sct",
						"code": "371530004",
						"display": "Clinical consultation report",
					}
				],
				"text": "Clinical Consultation report",
			},
			"subject": {
				"reference": urn("patient", encounter.patient_name),
				"display": encounter.patient_name,
			},
			"encounter": {"reference": f"urn:uuid:{encounter.name}", "display": "Encounter"},
			"date": last_updated,
			"author": [
				{
					"reference": f"urn:uuid:{encounter.practitioner}",
					"display": f"Dr. {encounter.practitioner_name}",
				}
			],
			"title": "Consultation Report",
			"custodian": {
				"reference": urn("org", encounter.company),
				"display": encounter.company,
			},
			"section": [],
		},
	}

	# Helper to append section
	def add_section(title, code, display, entries):
		if entries:
			section = {
				"title": title,
				"code": {
					"coding": [
						{"system": "http://snomed.info/sct", "code": code, "display": display}
					]
				},
				"entry": entries,
			}
			composition["resource"]["section"].append(section)

	# Chief complaints
	complaints = [
		{"reference": urn("symptom", s.complaint), "display": s.complaint}
		for s in encounter.symptoms
	]
	add_section("Chief complaints", "422843007", "Chief complaint section", complaints)

	# Diagnosis
	diagnoses = [
		{"reference": urn("diagnosis", d.diagnosis), "display": d.diagnosis}
		for d in encounter.diagnosis
	]
	add_section("Medical History", "371529009", "History and physical report", diagnoses)

	# Lab Tests
	labs = [
		{"reference": urn("labtest", l.observation_template), "display": l.observation_template}
		for l in encounter.lab_test_prescription
	]
	add_section("Investigation Advice", "721963009", "Order document", labs)

	# Medications
	meds = []
	for m in encounter.drug_prescription:
		display = f"{m.drug_name} {m.strength}{m.strength_uom} {m.dosage_form}, {m.dosage} for {m.period}"
		meds.append({"reference": urn("medication", m.drug_name), "display": display})
	add_section("Medications", "721912009", "Medication summary document", meds)

	# Procedures
	procedures = [
		{"reference": urn("procedure", p.procedure_name), "display": p.procedure_name}
		for p in encounter.procedure_prescription
	]
	add_section("Procedure", "371525003", "Clinical procedure report", procedures)

	# Therapies
	therapies = [
		{
			"reference": urn("therapy", t.therapy_type),
			"display": f"{t.therapy_type} - {t.no_of_sessions} sessions",
		}
		for t in encounter.therapies
	]
	add_section("Therapies", "736271009", "Outpatient care plan", therapies)

	# Codification
	codes = [
		{"reference": urn("codification", c.code), "display": c.definition or c.code_value}
		for c in encounter.codification_table
	]
	add_section("Codification Table", "371530004", "Clinical consultation report", codes)

	return composition


def get_encrypted_bundle(bundle, receiver_key_material):
	return encrypt_fhir_resource(bundle, receiver_key_material)


def generate_sender_key_material():
	"""Generate sender (data sender) ECDH key material compatible with ABDM."""
	private_key = x25519.X25519PrivateKey.generate()
	public_key = private_key.public_key()
	expiry = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"

	nonce = os.urandom(12)  # 96-bit nonce

	key_material = {
		"cryptoAlg": "ECDH",
		"curve": "curve25519",
		"dhPublicKey": {
			"expiry": expiry,
			"parameters": "Ephemeral public key",
			"keyValue": base64.b64encode(
				public_key.public_bytes(
					encoding=serialization.Encoding.Raw,
					format=serialization.PublicFormat.Raw
				)
			).decode()
		},
		"nonce": base64.b64encode(nonce).decode(),
	}

	return key_material, private_key, nonce


def encrypt_fhir_resource(fhir_resource_json, receiver_key_material):
	"""Encrypt the given FHIR resource JSON using ABDM ECDH + AES-GCM encryption."""

	if isinstance(receiver_key_material, str):
		receiver_key_material = json.loads(receiver_key_material)

	# --- Receiver Public Key ---
	receiver_pub_bytes = base64.b64decode(receiver_key_material["dhPublicKey"]["keyValue"])
	receiver_pub_bytes = parse_receiver_pub_key(receiver_key_material)
	print("\n\n\nreceiver_pub_bytes:\n", receiver_pub_bytes, len(receiver_pub_bytes))
	receiver_public_key = x25519.X25519PublicKey.from_public_bytes(receiver_pub_bytes)

	# --- Sender Key Material ---
	sender_key_material, sender_private_key, sender_nonce = generate_sender_key_material()

	# --- Shared Secret ---
	shared_secret = sender_private_key.exchange(receiver_public_key)

	# --- Derive AES Key (SHA256) ---
	digest = hashes.Hash(hashes.SHA256())
	digest.update(shared_secret)
	aes_key = digest.finalize()

	# --- Encrypt FHIR JSON ---
	plaintext = json.dumps(fhir_resource_json).encode("utf-8")
	aesgcm = AESGCM(aes_key)
	ciphertext = aesgcm.encrypt(sender_nonce, plaintext, None)

	# --- Return ABDM Format ---
	return {
		"encryptedData": base64.b64encode(ciphertext).decode(),
		"keyMaterial": sender_key_material,
	}


def parse_receiver_pub_key(key_material):
	key_value = key_material.get("dhPublicKey", {}).get("keyValue")
	pub_bytes = base64.b64decode(key_value)

	# Handle ABDM's 65-byte uncompressed EC point format
	if len(pub_bytes) == 65 and pub_bytes[0] == 0x04:
		# Strip 0x04 prefix and take only X coordinate (next 32 bytes)
		pub_bytes = pub_bytes[1:33]

	if len(pub_bytes) != 32:
		raise ValueError(f"Invalid X25519 key length after normalization: {len(pub_bytes)} bytes (expected 32)")

	return pub_bytes