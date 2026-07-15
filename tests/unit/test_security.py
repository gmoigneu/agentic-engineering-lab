from __future__ import annotations

import hashlib
import hmac

from agentic_lab.api.security import verify_github_signature


def test_verifies_github_hmac_with_constant_time_comparison_contract() -> None:
    body = b'{"repository":{"id":123456}}'
    secret = "test-webhook-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_github_signature(body, signature, secret)
    assert not verify_github_signature(body, signature, "another-secret")
    assert not verify_github_signature(body, None, secret)
