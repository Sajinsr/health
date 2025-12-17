# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import base64
import hashlib
import json
import uuid
from datetime import datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import frappe
from frappe.model.document import Document
from frappe.utils import format_datetime

from healthcare.regional.india.abdm.abdm_config import get_url
from healthcare.regional.india.abdm.utils import (
	generate_unique_id,
	get_abdm_settings,
	get_token_for_hiecm,
	request_and_post,
)


class ABDMConsent(Document):
	def validate(self):
		if self.data_push_url and self.key_material and self.transaction_id:
			headers = {"Content-Type": "application/json"}

			entries, keyMaterial = self.build_entries()

			payload = {
				"pageNumber": 0,
				"pageCount": 1,
				"transactionId": self.transaction_id,
				"entries": entries,
				"keyMaterial": keyMaterial,
			}

			frappe.log_error(message=payload, title="Data push-Payload")

			response = request_and_post(
				self.data_push_url,
				payload,
				headers,
				"POST",
				"Calling Data push URL",
				frappe.db.exists("Patient", {"abha_address": self.abha_address}),
			)

			sessionStatus = "FAILED"
			hiStatus = "ERRORED"

			if not response.get("traceback") and response in ["", None]:
				sessionStatus = "TRANSFERRED"
				hiStatus = "OK"

			send_dataflow_notify(self.consent_id, self.transaction_id, sessionStatus, hiStatus)

	def build_entries(self):
		"""
		[
		        {
		                "content": "Encrypted content of data packaged in FHIR bundle",
		                "media": "application/fhir+json",
		                "checksum": "string",
		                "careContextReference": "1931-nd2"
		        }
		]
		"""

		entries = []
		keyMaterial = {}
		if self.care_contexts:
			care_contexts = json.loads(self.care_contexts or "{}")
			consent_detail = json.loads(self.consent_detail or "{}")
			hi_types = consent_detail.get("hiTypes") or []

			for item in care_contexts:
				details = get_document_details(item, hi_types)

				if details:
					bundle = get_bundle(details)
					checksum = generate_checksum(bundle)
					if bundle:
						encypted_bundle = get_encrypted_bundle(bundle, self.key_material)
						entries.append(
							{
								"content": encypted_bundle.get("ciphertext"),
								"media": "application/fhir+json",
								"checksum": checksum,
								"careContextReference": item.get("careContextReference"),
							}
						)
						keyMaterial = self.key_material
						if isinstance(keyMaterial, str):
							keyMaterial = json.loads(keyMaterial)

						keyMaterial["dhPublicKey"]["keyValue"] = encypted_bundle.get("senderPublicKey")
						keyMaterial["nonce"] = encypted_bundle.get("nonce")

		if entries:
			return entries, keyMaterial


def generate_checksum(bundle):
	plaintext = json.dumps(bundle, separators=(",", ":")).encode("utf-8")
	sha = hashlib.sha256(plaintext).digest()
	return base64.b64encode(sha).decode()


def get_document_details(item, hi_types):
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
		if type != "ImmunizationRecord":
			doc_exists = frappe.db.exists(doctype_map[type], item_ref)

			if doc_exists:
				doc_details.update({"doctype": doctype_map[type], "docname": item_ref})
				break

	return doc_details


def get_bundle(item):
	bundle = {}
	if item.get("doctype") == "Patient Encounter":
		bundle = make_op_consultation_resource(item)

	return bundle


def make_op_consultation_resource(item):
	def add_section(title, code, display, entries):
		if entries:
			section = {
				"title": title,
				"code": {"coding": [{"system": "http://snomed.info/sct", "code": code, "display": display}]},
				"entry": entries,
			}
			section_entries.append(section)

	doc = frappe.get_doc(item.get("doctype"), item.get("docname"))
	author_ref = {
		"reference": doc.get("practitioner"),
		"display": doc.get("practitioner_name"),
	}
	subject_ref = {"reference": doc.get("patient"), "display": doc.get("patient_name")}
	composition_type = [
		{
			"system": "https://ndhm.gov.in/sct",
			"code": "440545006",
			"display": "Prescription record",
		}
	]
	encounter = {"reference": f"urn:uuid:Encounter/{doc.name}", "display": "Encounter"}
	section_entries = []

	# Chief complaints
	complaints = [{"reference": f"urn:uuid:{s.name}", "display": s.complaint} for s in doc.symptoms]
	add_section("Chief complaints", "422843007", "Chief complaint section", complaints)

	# Diagnosis
	diagnoses = [{"reference": f"urn:uuid:{d.name}", "display": d.diagnosis} for d in doc.diagnosis]
	add_section("Medical History", "371529009", "History and physical report", diagnoses)

	# Lab Tests
	labs = [
		{"reference": f"urn:uuid:{l.name}", "display": l.observation_template}
		for l in doc.lab_test_prescription
	]
	add_section("Investigation Advice", "721963009", "Order document", labs)

	# Medications
	meds = []
	for m in doc.drug_prescription:
		display = (
			f"{m.drug_name} {m.strength}{m.strength_uom} {m.dosage_form}, {m.dosage} for {m.period}"
		)
		meds.append({"reference": f"urn:uuid:{m.name}", "display": display})
	add_section("Medications", "721912009", "Medication summary document", meds)

	# Procedures
	procedures = [
		{"reference": f"urn:uuid:{p.name}", "display": p.procedure_name}
		for p in doc.procedure_prescription
	]
	add_section("Procedure", "371525003", "Clinical procedure report", procedures)

	# Therapies
	therapies = [
		{
			"reference": f"urn:uuid:{t.name}",
			"display": f"{t.therapy_type} - {t.no_of_sessions} sessions",
		}
		for t in doc.therapies
	]
	add_section("Therapies", "736271009", "Outpatient care plan", therapies)

	composition = make_composition(
		doc.title, author_ref, subject_ref, section_entries, composition_type, encounter
	)

	resources = make_resources(doc)

	identifier = {"system": "http://abdm.earthianslive.com", "value": doc.name}
	return make_bundle(resources, composition, identifier, "document")


def make_resources(doc):
	resources = []
	if doc.doctype == "Patient Encounter":
		resources.append(make_encounter_resource(doc))

		# if doc.drug_prescription:
		# 	resources.append(make_drug_resources(doc.drug_prescription))

	return resources


def make_encounter_resource(doc):
	enc_id = f"Encounter/{doc.name}"
	resource = {
		"resourceType": "Encounter",
		"id": enc_id,
		"meta": {
			"lastUpdated": format_datetime(doc.modified, "yyyy-MM-ddTHH:mm:ss.SSS'+05:30'"),
			"profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/Encounter"],
		},
		"text": {
			"status": "generated",
			"div": get_medical_record(doc),
		},
		"identifier": [{"system": "https://ndhm.in", "value": "S100"}],
		"status": "finished",
		"class": {
			"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
			"code": "AMB",
			"display": "ambulatory",
		},
		"subject": {
			"reference": f"urn:uuid:{doc.patient}",
			"display": "Patient",
		},
		"period": {"start": f"{doc.encounter_date}T{doc.encounter_time}+05:30"},
		"diagnosis": [],
	}

	for d in doc.diagnosis:
		resource["diagnosis"].append(
			{
				"condition": {
					"reference": f"urn:uuid:{d.name}",
					"display": "Condition",
				},
				"use": {
					"coding": [
						{
							"system": "http://snomed.info/sct",
							"code": "39154008",
							"display": "Clinical diagnosis",
						}
					]
				},
			}
		)

	return resource


def get_medical_record(doc):
	record = frappe.db.exists(
		"Patient Medical Record", {"reference_doctype": doc.doctype, "reference_name": doc.name}
	)

	if record:
		return frappe.db.get_value("Patient Medical Record", record, "subject")


def get_encrypted_bundle(bundle, receiver_key_material):
	if isinstance(receiver_key_material, str):
		receiver_key_material = json.loads(receiver_key_material)

	receiver_public_key = (
		receiver_key_material.get("dhPublicKey").get("keyValue")
		if receiver_key_material.get("dhPublicKey")
		else ""
	)
	nonce = receiver_key_material.get("nonce")

	return encrypt_fhir_resource(bundle, receiver_public_key, nonce)


def encrypt_fhir_resource(fhir_resource_json, receiver_public_key_b64, nonce_b64):
	"""
	Encrypt healthcare payload using:
	- ECDH (X25519)
	- HKDF (SHA256)
	- AES-256-GCM
	"""

	# -------------------------------
	# Decode inputs
	# -------------------------------
	decoded_key = base64.b64decode(receiver_public_key_b64)

	if len(decoded_key) < 32:
		frappe.throw("Invalid ABDM dhPublicKey received")

	# ABDM embeds raw X25519 key in LAST 32 bytes
	raw_x25519_key = decoded_key[-32:]

	receiver_public_key = x25519.X25519PublicKey.from_public_bytes(raw_x25519_key)

	# -------------------------------
	# Decode nonce
	# -------------------------------
	nonce = base64.b64decode(nonce_b64)

	# -------------------------------
	# Generate sender ephemeral key pair
	# -------------------------------
	sender_private_key = x25519.X25519PrivateKey.generate()
	sender_public_key = sender_private_key.public_key()

	# -------------------------------
	# Perform ECDH
	# -------------------------------
	shared_secret = sender_private_key.exchange(receiver_public_key)

	# -------------------------------
	# Derive symmetric key
	# -------------------------------
	derived_key = HKDF(
		algorithm=hashes.SHA256(), length=32, salt=None, info=b"healthcare-data-encryption"
	).derive(shared_secret)

	# -------------------------------
	# Encrypt payload
	# -------------------------------
	aesgcm = AESGCM(derived_key)

	plaintext_bytes = json.dumps(fhir_resource_json).encode("utf-8")

	ciphertext = aesgcm.encrypt(nonce=nonce, data=plaintext_bytes, associated_data=None)

	# -------------------------------
	# Export sender public key (raw)
	# -------------------------------
	sender_public_key_bytes = sender_public_key.public_bytes(
		encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
	)

	# -------------------------------
	# Return ABDM-compliant payload
	# -------------------------------
	return {
		"ciphertext": base64.b64encode(ciphertext).decode(),
		"senderPublicKey": base64.b64encode(sender_public_key_bytes).decode(),
		"nonce": nonce_b64,
	}


def parse_receiver_pub_key(key_material):
	key_value = key_material.get("dhPublicKey", {}).get("keyValue")
	pub_bytes = base64.b64decode(key_value)

	# Handle ABDM's 65-byte uncompressed EC point format
	if len(pub_bytes) == 65 and pub_bytes[0] == 0x04:
		# Strip 0x04 prefix and take only X coordinate (next 32 bytes)
		pub_bytes = pub_bytes[1:33]

	if len(pub_bytes) != 32:
		raise ValueError(
			f"Invalid X25519 key length after normalization: {len(pub_bytes)} bytes (expected 32)"
		)

	return pub_bytes


def make_composition(title, author_ref, subject_ref, section_entries, composition_type, encounter):
	"""Create a FHIR Composition resource referencing other resources."""
	composition_id = str(uuid.uuid4())  # frappe.generate_hash(length=64)

	return {
		"resourceType": "Composition",
		"id": composition_id,
		"status": "final",
		"type": {
			"coding": (composition_type if isinstance(composition_type, list) else [composition_type])
		},
		"title": title,
		"encounter": encounter,
		"date": f"{frappe.utils.now_datetime().isoformat(timespec='seconds')}Z",
		"author": [{"reference": author_ref.get("reference"), "display": author_ref.get("display")}],
		"subject": {
			"reference": subject_ref.get("reference"),
			"display": subject_ref.get("display"),
		},
		"section": section_entries,
	}


def send_dataflow_notify(
	consent_id=None, transaction_id=None, sessionStatus="TRANSFERRED", hiStatus="OK"
):
	if not consent_id or not transaction_id:
		frappe.throw("Missing Consent_id ID or Transaction ID")

	try:
		settings = get_abdm_settings()
		if not settings or not settings.consent_base_url:
			frappe.throw(
				title="Configuration Missing",
				msg="Consent Management Base URL not configured in ABDM Settings.",
			)

		auth_token = get_token_for_hiecm()
		if not auth_token or not auth_token.get("accessToken"):
			frappe.throw("Unable to fetch valid access token for HIE-CM.")

		config = get_url("data_flow_on_notify")
		url = settings.consent_base_url.rstrip("/") + config.get("url")

		auth_prefix = "Bearer " if auth_token.get("tokenType", "").lower() == "bearer" else ""
		authorization = auth_prefix + auth_token.get("accessToken")

		headers = {
			"Content-Type": "application/json",
			"REQUEST-ID": generate_unique_id(),
			"TIMESTAMP": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
			"X-CM-ID": settings.x_cm_id,
			"Authorization": authorization,
		}

		payload = {
			"notification": {
				"consentId": consent_id,
				"transactionId": transaction_id,
				"doneAt": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
				"notifier": {"type": "HIP", "id": settings.get("facility_id")},
				"statusNotification": {
					"sessionStatus": sessionStatus,
					"hipId": settings.get("facility_id"),
					"statusResponses": [
						{
							"careContextReference": "b18d2e56-c5d2-41d0-bbe9-32a8b7579f74",
							"hiStatus": hiStatus,
							"description": "Care context Delivered"
							if hiStatus == "OK"
							else "Care context Failed to Deliver",
						}
					],
				},
			}
		}

		try:
			request_and_post(
				url=url,
				payload=payload,
				headers=headers,
				method=config.get("method"),
				request_name="Data Flow On-Notify Request",
			)
		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(), title="Failed to Process ABDM Data Flow On-Notify Request"
			)
			raise e

	except Exception as e:
		frappe.log_error(
			message=frappe.get_traceback(), title="Failed to Process ABDM Data Flow On-Notify Request"
		)
		raise e


def make_bundle(resources, composition, identifier, bundle_type="transaction"):
	"""Combine Composition + other resources into a transaction Bundle."""
	bundle = {
		"resourceType": "Bundle",
		"type": bundle_type,
		"id": frappe.generate_hash(length=64),
		"identifier": identifier,
		"timestamp": f"{frappe.utils.now_datetime().isoformat(timespec='seconds')}Z",
		"entry": [],
	}

	# add composition first
	bundle["entry"].append(make_resource_entry(composition))

	# then add other resources
	for resource in resources:
		bundle["entry"].append(make_resource_entry(resource))

	return bundle


def make_resource_entry(resource):
	"""Wrap a resource in a Bundle.entry structure."""
	return {
		"fullUrl": f"urn:uuid:{resource['id']}",
		"resource": resource,
	}
