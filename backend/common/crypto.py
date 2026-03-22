import base64
import hashlib
import os

from cryptography.fernet import Fernet
from django.conf import settings


def _derive_encryption_key() -> bytes:
    configured_key = os.getenv("KUBOARD_ENCRYPTION_KEY", "").strip()
    if configured_key:
        digest = hashlib.sha256(configured_key.encode("utf-8")).digest()
    else:
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet:
    return Fernet(_derive_encryption_key())


def encrypt_text(value: str) -> str:
    return get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str) -> str:
    return get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")

