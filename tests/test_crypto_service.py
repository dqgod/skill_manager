from src.services.crypto_service import CryptoService


class TestCryptoService:
    def test_encrypt_decrypt_roundtrip(self):
        svc = CryptoService()
        plaintext = "secret-password-123"
        ct = svc.encrypt(plaintext)
        assert isinstance(ct, bytes)
        assert svc.decrypt(ct) == plaintext

    def test_empty_string(self):
        svc = CryptoService()
        ct = svc.encrypt("")
        assert svc.decrypt(ct) == ""

    def test_unicode(self):
        svc = CryptoService()
        text = "中文密码测试你好"
        ct = svc.encrypt(text)
        assert svc.decrypt(ct) == text

    def test_tampered_ciphertext_raises(self):
        svc = CryptoService()
        ct = svc.encrypt("password")
        tampered = ct[:-1] + bytes([(ct[-1] + 1) % 256])
        try:
            svc.decrypt(tampered)
            assert False, "should have raised"
        except Exception:
            pass

    def test_different_encryptions_produce_different_ciphertext(self):
        svc = CryptoService()
        ct1 = svc.encrypt("same")
        ct2 = svc.encrypt("same")
        assert ct1 != ct2  # different nonces
