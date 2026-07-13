#!/usr/bin/env python3
"""Minimal verified loader for the EonMem JSON runtime capsule."""

from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Any

CAPSULE_FILE = "eon.runtime.json"
STATE_FILE = "eon.state.json"
EXPECTED_FORMAT = "EonRuntimeCapsule"
EXPECTED_VERSION = 1
EXPECTED_ENGINE = "python3"
EXPECTED_CODEC = "gzip+base64"


class CapsuleError(RuntimeError):
    pass


def load_capsule(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            capsule = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise CapsuleError(f"не удалось прочитать runtime-капсулу: {exc}") from exc

    if not isinstance(capsule, dict):
        raise CapsuleError("runtime-капсула должна быть JSON-объектом")
    if capsule.get("format") != EXPECTED_FORMAT:
        raise CapsuleError("неподдерживаемый формат runtime-капсулы")
    if capsule.get("version") != EXPECTED_VERSION:
        raise CapsuleError("неподдерживаемая версия runtime-капсулы")
    if capsule.get("engine") != EXPECTED_ENGINE:
        raise CapsuleError("неподдерживаемый движок runtime-капсулы")
    if capsule.get("codec") != EXPECTED_CODEC:
        raise CapsuleError("неподдерживаемый кодек runtime-капсулы")
    return capsule


def decode_source(capsule: dict[str, Any]) -> bytes:
    payload = capsule.get("payload")
    expected_hash = capsule.get("source_sha256")
    if not isinstance(payload, str) or not payload:
        raise CapsuleError("runtime-капсула не содержит payload")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise CapsuleError("runtime-капсула не содержит корректный source_sha256")

    try:
        compressed = base64.b64decode(payload, validate=True)
        source = gzip.decompress(compressed)
    except Exception as exc:
        raise CapsuleError(f"не удалось декодировать runtime-капсулу: {exc}") from exc

    actual_hash = hashlib.sha256(source).hexdigest()
    if not hmac.compare_digest(actual_hash, expected_hash.lower()):
        raise CapsuleError(
            "контрольная сумма runtime-капсулы не совпадает: запуск запрещён"
        )
    return source


def main() -> int:
    base = Path(__file__).resolve().parent
    capsule_path = base / CAPSULE_FILE
    state_path = base / STATE_FILE

    capsule = load_capsule(capsule_path)
    source = decode_source(capsule)

    os.environ["EON_STATE_PATH"] = str(state_path)
    sys.argv = ["<EonRuntimeCapsule>", *sys.argv[1:]]
    namespace = {
        "__name__": "__main__",
        "__file__": "<EonRuntimeCapsule>",
        "__package__": None,
    }
    exec(compile(source, "<EonRuntimeCapsule>", "exec"), namespace)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CapsuleError as exc:
        print(f"\nОшибка капсулы: {exc}", file=sys.stderr)
        raise SystemExit(1)
