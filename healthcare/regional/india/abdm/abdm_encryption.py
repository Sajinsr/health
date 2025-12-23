import frappe
import base64
import os
from dataclasses import dataclass
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import (
	Encoding,
	PrivateFormat,
	PublicFormat,
	NoEncryption,
)

# ---------------------------------------------------------------------
# Data Models (Java → Python)
# ---------------------------------------------------------------------


@dataclass
class KeyMaterial:
	privateKey: str
	publicKey: str
	nonce: str


@dataclass
class EncryptionRequest:
	receiver_public_key: str
	receiver_nonce: str
	sender_private_key: str
	sender_public_key: str
	sender_nonce: str
	plain_text_data: str


# ---------------------------------------------------------------------
# Base64 helpers
# ---------------------------------------------------------------------


def _b64_encode(data: bytes) -> str:
	return base64.b64encode(data).decode()


def _b64_decode(data: str) -> bytes:
	return base64.b64decode(data)


# ---------------------------------------------------------------------
# XOR of nonces (exact Fidelius logic)
# ---------------------------------------------------------------------


def _xor_of_random(sender_nonce_b64: str, receiver_nonce_b64: str) -> bytes:
	sender = _b64_decode(sender_nonce_b64)
	receiver = _b64_decode(receiver_nonce_b64)

	out = bytearray(len(sender))
	for i in range(len(sender)):
		out[i] = sender[i] ^ receiver[i % len(receiver)]

	return bytes(out)


# ---------------------------------------------------------------------
# Curve25519 ECDH
# ---------------------------------------------------------------------


def _do_ecdh(sender_private_key_b64: str, receiver_public_key_b64: str) -> bytes:
	sender_private = X25519PrivateKey.from_private_bytes(
		_b64_decode(sender_private_key_b64)
	)

	receiver_public_raw = _normalize_x25519_public_key(receiver_public_key_b64)
	receiver_public = X25519PublicKey.from_public_bytes(receiver_public_raw)

	return sender_private.exchange(receiver_public)


def _normalize_x25519_public_key(pubkey_b64: str) -> bytes:
	raw = _b64_decode(pubkey_b64)

	# Fidelius / ABDM format: 65 bytes => 04 + X(32) + Y(32)
	if len(raw) == 65 and raw[0] == 0x04:
		return raw[1:33]  # ONLY X

	# Proper raw X25519 key
	if len(raw) == 32:
		return raw

	raise ValueError(f"Invalid public key length: {len(raw)} bytes")


# ---------------------------------------------------------------------
# HKDF → AES-256
# ---------------------------------------------------------------------


def _generate_aes_key(xor_random: bytes, shared_secret: bytes) -> bytes:
	salt = xor_random[:20]

	hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=None)
	return hkdf.derive(shared_secret)


# ---------------------------------------------------------------------
# AES-GCM Encryption
# ---------------------------------------------------------------------


def _encrypt_data(
	xor_random: bytes, sender_private_key: str, receiver_public_key: str, plaintext: str
) -> str:

	shared_secret = _do_ecdh(sender_private_key, receiver_public_key)
	iv = xor_random[-12:]
	aes_key = _generate_aes_key(xor_random, shared_secret)

	aesgcm = AESGCM(aes_key)
	cipher_text = aesgcm.encrypt(iv, plaintext.encode(), None)

	return _b64_encode(cipher_text)


# ---------------------------------------------------------------------
# keyToShare generation
# ---------------------------------------------------------------------


def _get_key_to_share(sender_public_key_b64: str) -> str:
	raw_x = _normalize_x25519_public_key(sender_public_key_b64)
	ec_65 = b"\x04" + raw_x + b"\x00" * 32
	return _b64_encode(ec_65)


# ---------------------------------------------------------------------
# WHITELISTED: Generate Key Material
# Java: GET /keys/generate
# ---------------------------------------------------------------------


@frappe.whitelist()
def generate_key_material():
	"""
	ABDM-compatible key material generation
	(X25519 + EC-style public key encoding)
	"""

	private_key = X25519PrivateKey.generate()
	public_key = private_key.public_key()

	# Raw X25519 private key (32 bytes)
	private_bytes = private_key.private_bytes(
		encoding=Encoding.Raw,
		format=PrivateFormat.Raw,
		encryption_algorithm=NoEncryption(),
	)

	# Raw X25519 public key (32 bytes)
	public_x = public_key.public_bytes(
		encoding=Encoding.Raw,
		format=PublicFormat.Raw,
	)

	# EC-style public key (65 bytes): 04 + X + Y(zeros)
	public_ec_65 = b"\x04" + public_x + b"\x00" * 32

	nonce_bytes = os.urandom(32)

	return {
		"privateKey": _b64_encode(private_bytes),  # 32 bytes
		"publicKey": _b64_encode(public_ec_65),  # 65 bytes (ABDM-style)
		"nonce": _b64_encode(nonce_bytes),  # 32 bytes
	}


# ---------------------------------------------------------------------
# WHITELISTED: Encrypt Data
# Java: POST /encrypt
# ---------------------------------------------------------------------


@frappe.whitelist()
def encrypt_abdm_data(payload: dict = None):
	"""
	Fidelius equivalent of /encrypt
	"""

	if not payload:
		payload = frappe.local.form_dict

	required = [
		"receiver_public_key",
		"receiver_nonce",
		"sender_private_key",
		"sender_public_key",
		"sender_nonce",
		"plain_text_data",
	]

	for field in required:
		if not payload.get(field):
			frappe.throw(f"Missing required field: {field}")

	xor_random = _xor_of_random(payload["sender_nonce"], payload["receiver_nonce"])

	encrypted_data = _encrypt_data(
		xor_random,
		payload["sender_private_key"],
		payload["receiver_public_key"],
		payload["plain_text_data"],
	)

	key_to_share = _get_key_to_share(payload["sender_public_key"])

	return {"encryptedData": encrypted_data, "keyToShare": key_to_share}
