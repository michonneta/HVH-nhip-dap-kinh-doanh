"""Mã hóa file dữ liệu dashboard (GitHub Pages miễn phí là công khai).

AES-256-GCM, khóa sinh từ mật khẩu bằng PBKDF2-SHA256. Trình duyệt giải mã bằng WebCrypto (docs/index.html).
"""
import base64
import gzip
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 200_000


def open_sealed(obj: dict, password: str):
    """Giải mã một file đã seal (dùng khi pipeline cần đọc lại bản nháp)."""
    if not password:
        raise ValueError("Thiếu DASHBOARD_PASSWORD để đọc dữ liệu đã mã hóa")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(obj["salt"]), iterations=obj["iter"])
    aes = AESGCM(kdf.derive(password.encode("utf-8")))
    plain = aes.decrypt(base64.b64decode(obj["iv"]), base64.b64decode(obj["ct"]), None)
    if obj.get("gz"):
        plain = gzip.decompress(plain)
    return json.loads(plain.decode("utf-8"))


class Encryptor:
    """Một salt cho cả lần build để trình duyệt chỉ phải sinh khóa một lần."""

    def __init__(self, password: str):
        self.salt = os.urandom(16)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=self.salt, iterations=ITERATIONS)
        self.aes = AESGCM(kdf.derive(password.encode("utf-8")))

    def seal(self, obj, gz: bool = False) -> dict:
        """gz=True: nén gzip trước khi mã hóa (khối dữ liệu Dashboard); trình duyệt giải nén bằng DecompressionStream."""
        iv = os.urandom(12)
        plain = json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
        if gz:
            plain = gzip.compress(plain, mtime=0)
        b64 = lambda b: base64.b64encode(b).decode("ascii")
        return {"enc": "aes-256-gcm", "kdf": "pbkdf2-sha256", "iter": ITERATIONS, "gz": gz,
                "salt": b64(self.salt), "iv": b64(iv), "ct": b64(self.aes.encrypt(iv, plain, None))}
