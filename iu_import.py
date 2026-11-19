"""Decrypt the encrypted IU calendar export inside GitHub Actions only.

Only ciphertext is committed to GitHub. The secret key lives exclusively in
GitHub Actions Secrets and in the user's locally downloaded key file.
"""
import base64
import json
import pathlib
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"Unsere Zeit | IU ICS | v1"
MAX_CIPHERTEXT_BYTES = 500_000
MAX_PLAINTEXT_BYTES = 400_000


class IUImportError(ValueError):
    """Safe error: never contains calendar content or secret key."""


def load_iu_ics(key_hex, filename):
    if not isinstance(key_hex, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", key_hex.strip()):
        raise IUImportError("Invalid IU import key.")
    path = pathlib.Path(filename)
    try:
        if path.stat().st_size > MAX_CIPHERTEXT_BYTES:
            raise IUImportError("IU import file is too large.")
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(envelope, dict) or envelope.get("v") != 1 or envelope.get("alg") != "AES-256-GCM":
            raise IUImportError("Invalid IU import format.")
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
        if len(nonce) != 12 or not 16 <= len(ciphertext) <= MAX_CIPHERTEXT_BYTES:
            raise IUImportError("Invalid IU ciphertext.")
        plain = AESGCM(bytes.fromhex(key_hex.strip())).decrypt(nonce, ciphertext, AAD)
        if len(plain) > MAX_PLAINTEXT_BYTES:
            raise IUImportError("IU import plaintext is too large.")
        text = plain.decode("utf-8-sig")
        if "BEGIN:VCALENDAR" not in text[:128] or "END:VCALENDAR" not in text[-128:]:
            raise IUImportError("IU import is not an ICS calendar.")
        return text
    except IUImportError:
        raise
    except Exception:
        raise IUImportError("IU import could not be decrypted or read.") from None