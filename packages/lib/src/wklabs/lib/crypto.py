"""Fernet encryption for WaniKani tokens at rest (key: `WKLABS_SECRET_KEY`)."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from .settings import Settings


class CipherError(Exception):
    pass


class TokenCipher:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise CipherError(
                "WKLABS_SECRET_KEY is not a valid Fernet key (run `wklabs gen-key`)"
            ) from exc

    @classmethod
    def from_settings(cls, settings: Settings) -> TokenCipher:
        if not settings.secret_key:
            raise CipherError(
                "WKLABS_SECRET_KEY is not set — run `wklabs gen-key`, put it in the env"
            )
        return cls(settings.secret_key)

    def encrypt(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode()

    def decrypt(self, enc: str) -> str:
        try:
            return self._fernet.decrypt(enc.encode()).decode()
        except InvalidToken as exc:
            raise CipherError("cannot decrypt token — wrong WKLABS_SECRET_KEY?") from exc


def generate_key() -> str:
    return Fernet.generate_key().decode()
