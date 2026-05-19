"""Verify Recall.ai webhook signatures (workspace secret whsec_...)."""

from __future__ import annotations

import base64
import hmac
import hashlib


def verify_recall_request(
    headers: dict[str, str],
    raw_body: bytes,
    secret: str,
) -> bool:
    """
    Recall signs: HMAC-SHA256 over "{webhook-id}.{webhook-timestamp}.{payload}".
    Header format: webhook-signature: v1,<base64_sig> [multiple during rotation]
    """
    if not secret or not secret.startswith("whsec_"):
        return False

    msg_id = headers.get("webhook-id") or headers.get("svix-id")
    msg_timestamp = headers.get("webhook-timestamp") or headers.get("svix-timestamp")
    msg_signature = headers.get("webhook-signature") or headers.get("svix-signature")

    if not msg_id or not msg_timestamp or not msg_signature:
        return False

    key = base64.b64decode(secret.removeprefix("whsec_"))
    payload_str = raw_body.decode("utf-8")
    signed_content = f"{msg_id}.{msg_timestamp}.{payload_str}".encode()
    expected_sig = base64.b64encode(
        hmac.new(key, signed_content, hashlib.sha256).digest()
    ).decode()

    for versioned_sig in msg_signature.split():
        if "," not in versioned_sig:
            continue
        version, signature = versioned_sig.split(",", 1)
        if version != "v1":
            continue
        try:
            sig_bytes = base64.b64decode(signature)
            expected_bytes = base64.b64decode(expected_sig)
        except Exception:
            continue
        if len(sig_bytes) == len(expected_bytes) and hmac.compare_digest(
            sig_bytes, expected_bytes
        ):
            return True
    return False


def normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items()}
