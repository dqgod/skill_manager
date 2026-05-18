"""AES-256-GCM 加解密服务"""

import os
import keyring
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SERVICE_NAME = "skill-manager"
KEY_NAME = "aes-key"


class CryptoService:
    def __init__(self):
        key = keyring.get_password(SERVICE_NAME, KEY_NAME)
        if key is None:
            key = AESGCM.generate_key(bit_length=256).hex()
            keyring.set_password(SERVICE_NAME, KEY_NAME, key)
        self._key = bytes.fromhex(key)
        self._aesgcm = AESGCM(self._key)

    def encrypt(self, plaintext: str) -> bytes:
        nonce = os.urandom(12)
        ct = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ct

    def decrypt(self, ciphertext: bytes) -> str:
        nonce, ct = ciphertext[:12], ciphertext[12:]
        return self._aesgcm.decrypt(nonce, ct, None).decode("utf-8")
