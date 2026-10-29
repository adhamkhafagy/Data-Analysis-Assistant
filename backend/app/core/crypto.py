from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.core.config import get_settings


class CredentialCipher:
    """Environment-backed authenticated encryption; replaceable by managed KMS later."""

    def __init__(self, key: str | SecretStr | None = None):
        raw = key.get_secret_value() if isinstance(key, SecretStr) else key
        raw = raw if raw is not None else get_settings().data_source_encryption_key.get_secret_value()
        try:
            self._fernet = Fernet(raw.encode("ascii"))
        except (ValueError, UnicodeEncodeError, AttributeError):
            raise ValueError("DATA_SOURCE_ENCRYPTION_KEY must be a valid Fernet key") from None

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeEncodeError):
            raise ValueError("Stored credential cannot be decrypted with the configured key") from None
