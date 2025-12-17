# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import base64
import hashlib
import json
import os
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

			if entries and keyMaterial:
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
					if bundle:
						encypted_bundle = get_encrypted_bundle(bundle, self.key_material)
						entries.append(
							{
								"content": encypted_bundle.get("encryptedData"),
								"media": "application/fhir+json",
								"checksum": encypted_bundle.get("checksum"),
								"careContextReference": item.get("careContextReference"),
							}
						)
						keyMaterial = encypted_bundle.get("keyMaterial")

		return entries, keyMaterial


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
	expiry = (
		receiver_key_material.get("dhPublicKey").get("expiry")
		if receiver_key_material.get("dhPublicKey")
		else ""
	)
	nonce = receiver_key_material.get("nonce")

	return encrypt_fhir_bundle(
		fhir_bundle=bundle, hiu_public_key_b64=receiver_public_key, hiu_nonce_b64=nonce, expiry=expiry
	)


def b64decode(data: str) -> bytes:
	return base64.b64decode(data)


def b64encode(data: bytes) -> str:
	return base64.b64encode(data).decode()


def xor_bytes(a: bytes, b: bytes) -> bytes:
	return bytes(x ^ y for x, y in zip(a, b))


def extract_x25519_public_key(raw_key: bytes) -> bytes:
	"""
	ABDM sends uncompressed EC public key:
	04 || X (32 bytes) || Y (32 bytes)

	Curve25519 uses ONLY X
	"""
	if len(raw_key) == 65 and raw_key[0] == 0x04:
		return raw_key[1:33]  # X coordinate
	elif len(raw_key) == 32:
		return raw_key
	else:
		raise ValueError("Invalid HIU public key format")


def encrypt_fhir_bundle(
	fhir_bundle: dict,
	hiu_public_key_b64: str,
	hiu_nonce_b64: str,
	expiry: str,
):
	"""
	ABDM HDCM HIP-side encryption
	"""

	# Decode HIU key material
	hiu_public_key_raw_full = base64.b64decode(hiu_public_key_b64)

	hiu_public_key_raw = extract_x25519_public_key(hiu_public_key_raw_full)
	hiu_nonce = b64decode(hiu_nonce_b64)

	if len(hiu_public_key_raw) != 32:
		raise ValueError("HIU public key must be 32 bytes (Curve25519)")

	if len(hiu_nonce) != 32:
		raise ValueError("HIU nonce must be 32 bytes")

	# Load HIU public key
	hiu_public_key = x25519.X25519PublicKey.from_public_bytes(hiu_public_key_raw)

	# Generate HIP ephemeral key pair
	hip_private_key = x25519.X25519PrivateKey.generate()
	hip_public_key = hip_private_key.public_key()

	# hip_public_key_der = hip_public_key.public_bytes(
	# 	encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo
	# )
	raw_pub = hip_public_key.public_bytes(
		encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
	)

	hip_public_key_der = wrap_x25519_public_key_as_ec_der(raw_pub)

	# Generate HIP nonce
	hip_nonce = os.urandom(32)

	# Compute shared secret (ECDH)
	shared_secret = hip_private_key.exchange(hiu_public_key)
	# 32 bytes

	# XOR nonces
	nonce_xor = xor_bytes(hiu_nonce, hip_nonce)

	# HKDF salt (first 20 bytes)
	salt = nonce_xor[:20]

	# Derive session key (256-bit)
	hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=None)

	session_key = hkdf.derive(shared_secret)

	# AES-GCM IV (last 12 bytes)
	iv = nonce_xor[-12:]

	# Encrypt FHIR bundle
	plaintext = json.dumps(fhir_bundle, separators=(",", ":")).encode("utf-8")

	aesgcm = AESGCM(session_key)
	ciphertext = aesgcm.encrypt(iv, plaintext, None)

	keyValue = base64.b64encode(hip_public_key_der).decode()
	decoded = base64.b64decode(keyValue)
	frappe.log_error(
		message={"length": len(decoded), "starts_with_30": decoded[0] == 0x30},
		title="HIP Public Key DER Check",
	)

	# Prepare ABDM response
	return {
		"encryptedData": b64encode(ciphertext),
		"keyMaterial": {
			"cryptoAlg": "ECDH",
			"curve": "curve25519",
			"dhPublicKey": {
				"expiry": expiry,
				"parameters": "Ephemeral public key",
				"keyValue": keyValue,
			},
			"nonce": b64encode(hip_nonce),
		},
		"checksum": base64.b64encode(hashlib.sha256(plaintext).digest()).decode(),
	}


def wrap_x25519_public_key_as_ec_der(raw_pub: bytes) -> bytes:
	"""
	Wrap raw 32-byte X25519 public key into EC SubjectPublicKeyInfo DER
	ABDM Java compatible
	"""
	if len(raw_pub) != 32:
		raise ValueError("X25519 public key must be 32 bytes")

	# ASN.1 structure:
	# SEQUENCE {
	#   SEQUENCE {
	#     OID id-ecPublicKey (1.2.840.10045.2.1)
	#     OID curve25519 (1.3.101.110)
	#   }
	#   BIT STRING (public key)
	# }

	return (
		b"\x30\x2a"  # SEQUENCE (42)
		b"\x30\x05"  # SEQUENCE
		b"\x06\x03\x2b\x65\x6e"  # OID 1.3.101.110 (X25519)
		b"\x03\x21\x00" + raw_pub  # BIT STRING (33)
	)


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
