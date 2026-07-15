from __future__ import annotations

import hashlib
import hmac


def payload_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def verify_github_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
