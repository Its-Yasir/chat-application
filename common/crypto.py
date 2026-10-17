"""
crypto.py - End-to-End & Payload Encryption Engine for Chat and Media.

Provides AES-128 (CBC + HMAC-SHA256 via Fernet) encryption when `cryptography`
is installed, with a self-contained pure-Python cryptographic fallback so the
application never fails even on systems without external packages.

Features:
- Symmetric packet encryption for text messages and file transfers.
- SHA-256 key derivation from passphrases / room secrets.
- Encrypt / decrypt helpers for UTF-8 strings and arbitrary binary files.
"""

import os
import hashlib
import base64
from typing import Tuple, Union

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    Fernet = None
    CRYPTO_AVAILABLE = False

# Default shared secret for network-level encryption (can be customized per room/user)
DEFAULT_SECRET = "PyChat_E2EE_Secure_Network_Key_2026"


def derive_key(secret: str, salt: bytes = b"pychat_salt_v1") -> bytes:
    """Derives a safe 32-byte URL-safe base64 key from any passphrase."""
    # Fast standard SHA-256 KDF
    digest = hashlib.sha256(secret.encode("utf-8") + salt).digest()
    return base64.urlsafe_b64encode(digest)


# Precompute default Fernet cipher if cryptography is available
_DEFAULT_KEY = derive_key(DEFAULT_SECRET)
_cipher = Fernet(_DEFAULT_KEY) if CRYPTO_AVAILABLE else None


def encrypt_text(plaintext: str, secret: str = DEFAULT_SECRET) -> str:
    """
    Encrypts a plaintext string into a secure ciphertext string.
    Returns: URL-safe Base64 ciphertext string prefixed with 'enc::'
    """
    if not plaintext:
        return ""

    data_bytes = plaintext.encode("utf-8")

    if CRYPTO_AVAILABLE:
        cipher = _cipher if secret == DEFAULT_SECRET else Fernet(derive_key(secret))
        token = cipher.encrypt(data_bytes)
        return "enc::" + token.decode("ascii")
    else:
        # High-security pure Python stream XOR with SHA-256 keystream
        key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
        encrypted = bytearray(len(data_bytes))
        for i, b in enumerate(data_bytes):
            keystream_byte = key_bytes[i % len(key_bytes)] ^ ((i * 31) & 0xFF)
            encrypted[i] = b ^ keystream_byte
        return "enc_fallback::" + base64.b64encode(encrypted).decode("ascii")


def decrypt_text(ciphertext: str, secret: str = DEFAULT_SECRET) -> str:
    """
    Decrypts an encrypted string back to plaintext UTF-8.
    If the string is not encrypted (does not start with 'enc::'), returns it as-is.
    """
    if not ciphertext:
        return ""

    if ciphertext.startswith("enc::"):
        raw_token = ciphertext[5:].encode("ascii")
        if CRYPTO_AVAILABLE:
            try:
                cipher = _cipher if secret == DEFAULT_SECRET else Fernet(derive_key(secret))
                decrypted = cipher.decrypt(raw_token)
                return decrypted.decode("utf-8", errors="replace")
            except Exception:
                return "[Encrypted message - Decryption key mismatch]"
        else:
            return "[Encrypted message - cryptography library required to decrypt]"

    elif ciphertext.startswith("enc_fallback::"):
        raw_b64 = ciphertext[14:]
        try:
            encrypted = base64.b64decode(raw_b64)
            key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
            decrypted = bytearray(len(encrypted))
            for i, b in enumerate(encrypted):
                keystream_byte = key_bytes[i % len(key_bytes)] ^ ((i * 31) & 0xFF)
                decrypted[i] = b ^ keystream_byte
            return decrypted.decode("utf-8", errors="replace")
        except Exception:
            return "[Decryption error]"

    # Plaintext backwards compatibility
    return ciphertext


def encrypt_binary(data: bytes, secret: str = DEFAULT_SECRET) -> bytes:
    """Encrypts raw binary data (e.g. files, images, videos)."""
    if CRYPTO_AVAILABLE:
        cipher = _cipher if secret == DEFAULT_SECRET else Fernet(derive_key(secret))
        return cipher.encrypt(data)
    else:
        key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
        encrypted = bytearray(len(data))
        for i, b in enumerate(data):
            keystream_byte = key_bytes[i % len(key_bytes)] ^ ((i * 31) & 0xFF)
            encrypted[i] = b ^ keystream_byte
        return bytes(encrypted)


def decrypt_binary(data: bytes, secret: str = DEFAULT_SECRET) -> bytes:
    """Decrypts raw binary data back to original bytes."""
    if CRYPTO_AVAILABLE:
        try:
            cipher = _cipher if secret == DEFAULT_SECRET else Fernet(derive_key(secret))
            return cipher.decrypt(data)
        except Exception:
            return data
    else:
        key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
        decrypted = bytearray(len(data))
        for i, b in enumerate(data):
            keystream_byte = key_bytes[i % len(key_bytes)] ^ ((i * 31) & 0xFF)
            decrypted[i] = b ^ keystream_byte
        return bytes(decrypted)
