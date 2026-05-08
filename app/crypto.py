import base64
import hashlib

from cryptography.fernet import Fernet
from flask import current_app


def _fernet() -> Fernet:
    raw_key = current_app.config.get("ENCRYPTION_KEY", "").strip()
    if raw_key:
        key_material = raw_key.encode("utf-8")
    else:
        key_material = current_app.config["SECRET_KEY"].encode("utf-8")
    derived = hashlib.sha256(key_material).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_value(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(value: str) -> str:
    if not value:
        return ""
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")

