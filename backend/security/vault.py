import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from backend.core.config import get_settings


class VaultError(RuntimeError):
    pass


def _key_file() -> Path:
    directory = get_settings().security_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "master.key"


def _key() -> bytes:
    configured = get_settings().master_key
    if configured:
        return base64.urlsafe_b64encode(hashlib.sha256(configured.encode()).digest())
    path = _key_file()
    if not path.exists():
        path.write_bytes(Fernet.generate_key())
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    value = path.read_bytes().strip()
    if len(value) != 44:
        raise VaultError("The local master key file is invalid.")
    return value


def encrypt_secret(value: str) -> str:
    return Fernet(_key()).encrypt(value.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return Fernet(_key()).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise VaultError("Secret decryption failed; the key does not match.") from exc
