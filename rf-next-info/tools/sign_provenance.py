from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from tools.sign_update_manifest import _b64, _private_key


PROVENANCE_SIGNATURE_CONTEXT = b"RFQOL-PROVENANCE-V1\0"


def create_signature(provenance: Path, key_id: str, private_key: Path) -> dict:
    raw = provenance.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("Procedência excede 1 MiB")
    document = json.loads(raw)
    if (
        document.get("product") != "rf-qol"
        or document.get("release") is not True
        or document.get("authenticode") is not False
        or not document.get("commit")
        or not document.get("installer_sha256")
        or not document.get("manifest_sha256")
    ):
        raise ValueError("Procedência de release incompleta")
    if not key_id.startswith("update-") or key_id.endswith("-pending"):
        raise ValueError("key_id de update inválido")
    return {
        "signature_version": 1,
        "product": "rf-qol",
        "key_id": key_id,
        "file": provenance.name,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "signature": _b64(
            _private_key(private_key).sign(PROVENANCE_SIGNATURE_CONTEXT + raw)
        ),
    }


def verify_signature(
    provenance: Path, signature: dict, public_keys: dict[str, str]
) -> None:
    raw = provenance.read_bytes()
    expected = {
        "signature_version",
        "product",
        "key_id",
        "file",
        "size",
        "sha256",
        "signature",
    }
    if set(signature) != expected or signature["product"] != "rf-qol":
        raise ValueError("Assinatura de procedência inválida")
    if (
        signature["file"] != provenance.name
        or signature["size"] != len(raw)
        or signature["sha256"] != hashlib.sha256(raw).hexdigest()
    ):
        raise ValueError("Procedência alterada")
    public = public_keys.get(signature["key_id"])
    if not public:
        raise ValueError("Chave de procedência desconhecida")
    try:
        Ed25519PublicKey.from_public_bytes(
            base64.urlsafe_b64decode(public + "=" * (-len(public) % 4))
        ).verify(
            base64.urlsafe_b64decode(
                signature["signature"] + "=" * (-len(signature["signature"]) % 4)
            ),
            PROVENANCE_SIGNATURE_CONTEXT + raw,
        )
    except Exception as error:
        raise ValueError("Assinatura de procedência inválida") from error


def main() -> int:
    parser = argparse.ArgumentParser(description="Assina procedência local do RF QOL")
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    signature = create_signature(
        args.provenance.resolve(strict=True), args.key_id, args.private_key
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(signature, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
