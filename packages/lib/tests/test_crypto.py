import pytest

from wklabs.lib.crypto import CipherError, TokenCipher, generate_key
from wklabs.lib.settings import Settings


def test_roundtrip_and_random_iv():
    c = TokenCipher(generate_key())
    enc = c.encrypt("8f2c1e6a-1111-4222-8333-444455556666")
    assert enc != "8f2c1e6a-1111-4222-8333-444455556666"
    assert c.decrypt(enc) == "8f2c1e6a-1111-4222-8333-444455556666"
    assert c.encrypt("x") != c.encrypt("x")


def test_wrong_or_bad_key():
    enc = TokenCipher(generate_key()).encrypt("secret")
    with pytest.raises(CipherError):
        TokenCipher(generate_key()).decrypt(enc)
    with pytest.raises(CipherError):
        TokenCipher("not-a-key")


def test_from_settings_requires_key():
    with pytest.raises(CipherError):
        TokenCipher.from_settings(Settings(wklabs_secret_key=""))
    assert TokenCipher.from_settings(Settings(wklabs_secret_key=generate_key()))
