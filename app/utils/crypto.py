"""登录/改密传输层 RSA 加密（文档要求密码传输加密）."""

from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.config import DATA_DIR

_PRIVATE_KEY_PATH = DATA_DIR / "rsa_private.pem"
_PUBLIC_KEY_PATH = DATA_DIR / "rsa_public.pem"
_private_key: rsa.RSAPrivateKey | None = None
_public_pem: str | None = None


def _ensure_keys() -> None:
    global _private_key, _public_pem
    if _private_key is not None and _public_pem is not None:
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _PRIVATE_KEY_PATH.exists() and _PUBLIC_KEY_PATH.exists():
        _private_key = serialization.load_pem_private_key(
            _PRIVATE_KEY_PATH.read_bytes(), password=None
        )
        _public_pem = _PUBLIC_KEY_PATH.read_text(encoding="utf-8")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _PRIVATE_KEY_PATH.write_bytes(private_pem)
    _PUBLIC_KEY_PATH.write_bytes(public_pem)
    _private_key = key
    _public_pem = public_pem.decode("utf-8")


def get_public_key_pem() -> str:
    _ensure_keys()
    assert _public_pem is not None
    return _public_pem


def decrypt_password(cipher_b64: str) -> str:
    """解密前端 RSA-OAEP(SHA-256) + Base64 后的密文."""
    _ensure_keys()
    assert _private_key is not None
    raw = base64.b64decode(cipher_b64)
    plain = _private_key.decrypt(
        raw,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return plain.decode("utf-8")
