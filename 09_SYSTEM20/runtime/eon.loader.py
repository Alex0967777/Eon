#!/usr/bin/env python3
"""Minimal verified loader for the multipart EonMem runtime capsule."""

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

MANIFEST_FILE = "eon.runtime.json"
STATE_FILE = "eon.state.json"
EXPECTED_FORMAT = "EonRuntimeCapsule"
EXPECTED_VERSION = 3
EXPECTED_ENGINE = "python3"
EXPECTED_CODEC = "gzip+base64-parts"
PART_FORMAT = "EonRuntimePart"
PART_VERSION = 1


class CapsuleError(RuntimeError):
    pass


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise CapsuleError(f"не удалось прочитать {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise CapsuleError(f"{label} должен быть JSON-объектом")
    return value


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = read_json(path, "runtime-манифест")
    if manifest.get("format") != EXPECTED_FORMAT:
        raise CapsuleError("неподдерживаемый формат runtime-манифеста")
    if manifest.get("version") != EXPECTED_VERSION:
        raise CapsuleError("неподдерживаемая версия runtime-манифеста")
    if manifest.get("engine") != EXPECTED_ENGINE:
        raise CapsuleError("неподдерживаемый движок runtime-манифеста")
    if manifest.get("codec") != EXPECTED_CODEC:
        raise CapsuleError("неподдерживаемый кодек runtime-манифеста")
    parts = manifest.get("parts")
    if not isinstance(parts, list) or not parts:
        raise CapsuleError("runtime-манифест не содержит parts")
    if manifest.get("part_count") != len(parts):
        raise CapsuleError("part_count не совпадает с числом parts")
    return manifest


def read_payload(base: Path, manifest: dict[str, Any]) -> str:
    payload_parts: list[str] = []
    for expected_index, item in enumerate(manifest["parts"], start=1):
        if not isinstance(item, dict):
            raise CapsuleError("некорректная запись parts")
        filename = item.get("file")
        index = item.get("index")
        if index != expected_index:
            raise CapsuleError("нарушен порядок runtime-частей")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise CapsuleError("некорректное имя runtime-части")
        part = read_json(base / filename, f"runtime-часть {expected_index}")
        if part.get("format") != PART_FORMAT or part.get("version") != PART_VERSION:
            raise CapsuleError(f"неподдерживаемый формат runtime-части {expected_index}")
        if part.get("index") != expected_index:
            raise CapsuleError(f"неверный индекс runtime-части {expected_index}")
        chunks = part.get("payload_chunks")
        if not isinstance(chunks, list) or not chunks:
            raise CapsuleError(f"runtime-часть {expected_index} не содержит payload_chunks")
        if not all(isinstance(chunk, str) and chunk for chunk in chunks):
            raise CapsuleError(f"runtime-часть {expected_index} повреждена")
        payload_parts.append("".join(chunks))
    return "".join(payload_parts)


def decode_source(base: Path, manifest: dict[str, Any]) -> bytes:
    expected_hash = manifest.get("source_sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise CapsuleError("runtime-манифест не содержит корректный source_sha256")
    payload = read_payload(base, manifest)
    try:
        source = gzip.decompress(base64.b64decode(payload, validate=True))
    except Exception as exc:
        raise CapsuleError(f"не удалось декодировать runtime-капсулу: {exc}") from exc
    actual_hash = hashlib.sha256(source).hexdigest()
    if not hmac.compare_digest(actual_hash, expected_hash.lower()):
        raise CapsuleError("контрольная сумма runtime-капсулы не совпадает: запуск запрещён")
    return source


def main() -> int:
    base = Path(__file__).resolve().parent
    manifest = load_manifest(base / MANIFEST_FILE)
    source = decode_source(base, manifest)
    os.environ["EON_STATE_PATH"] = str(base / STATE_FILE)
    sys.argv = ["<EonRuntimeCapsule>", *sys.argv[1:]]
    namespace = {"__name__": "__main__", "__file__": "<EonRuntimeCapsule>", "__package__": None}
    exec(compile(source, "<EonRuntimeCapsule>", "exec"), namespace)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CapsuleError as exc:
        print(f"\nОшибка капсулы: {exc}", file=sys.stderr)
        raise SystemExit(1)
