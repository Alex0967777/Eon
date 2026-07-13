#!/usr/bin/env python3
"""EonMem System 20 — canonical Python runtime, state format v2."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

APP_VERSION = "0.2.0"
STATE_FILE_NAME = "eon.state.json"
MAX_REFLECTION_LEN = 1000
MAX_QUESTION_LEN = 100
MAX_REGISTER_LEN = 160
CHECKPOINT_EVERY = 10
STATE_FORMAT_VERSION = 2
HISTORY_FORMAT = "step-files-v1"

LEVELS: tuple[dict[str, Any], ...] = (
    {"key": "D", "title": "Глубокие", "interval": 10},
    {"key": "S", "title": "Медленные", "interval": 5},
    {"key": "F", "title": "Быстрые", "interval": 1},
)


class EonMemError(RuntimeError):
    """Expected user-facing runtime error."""


def default_state() -> dict[str, Any]:
    return {
        "format_version": STATE_FORMAT_VERSION,
        "step": 0,
        "registers": {
            "deep": ["", "", ""],
            "slow": ["", "", ""],
            "fast": ["", "", ""],
        },
        "flow_1": {
            "text": "Поток ещё не начат.",
            "question": "Какая мысль сейчас требует продолжения?",
        },
        "last_used_step": {"F": 0, "S": 0, "D": 0},
        "history_index": {
            "format": HISTORY_FORMAT,
            "first_step": None,
            "last_step": 0,
        },
    }


def resolve_state_path() -> Path:
    """Use an explicit capsule path when set, otherwise a file beside this script."""
    override = os.environ.get("EON_STATE_PATH")
    if override:
        return Path(override).expanduser().resolve()

    try:
        script_path = Path(__file__).resolve()
    except NameError as exc:  # exec/compile without __file__
        raise EonMemError(
            "не удалось определить путь программы; задайте EON_STATE_PATH"
        ) from exc
    return script_path.parent / STATE_FILE_NAME


def normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    version = state.get("format_version")
    if version != STATE_FORMAT_VERSION:
        raise EonMemError(
            f"неподдерживаемая версия состояния: {version}; ожидается {STATE_FORMAT_VERSION}"
        )

    state.setdefault("step", 0)
    registers = state.setdefault("registers", {})
    for name in ("deep", "slow", "fast"):
        values = registers.setdefault(name, ["", "", ""])
        if not isinstance(values, list):
            raise EonMemError(f"повреждён массив регистра: {name}")
        values[:] = (values + ["", "", ""])[:3]

    flow = state.setdefault("flow_1", {})
    flow.setdefault("text", "Поток ещё не начат.")
    flow.setdefault("question", "Какая мысль сейчас требует продолжения?")

    last_used = state.setdefault("last_used_step", {})
    for key in ("F", "S", "D"):
        last_used.setdefault(key, 0)

    history_index = state.setdefault("history_index", {})
    if history_index.get("format") != HISTORY_FORMAT:
        raise EonMemError("неподдерживаемый формат history_index")
    history_index.setdefault("first_step", None)
    history_index.setdefault("last_step", int(state["step"]))

    if int(history_index["last_step"]) > int(state["step"]):
        raise EonMemError("history_index опережает текущий шаг состояния")

    return state


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        state = default_state()
        save_state(path, state)
        return state

    try:
        with path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise EonMemError(f"повреждён файл состояния: {exc}") from exc

    if not isinstance(raw, dict):
        raise EonMemError("повреждён файл состояния: корень JSON должен быть объектом")
    return normalize_state(raw)


def atomic_write_text(path: Path, text: str, *, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=prefix,
            suffix=".tmp",
            delete=False,
        ) as temp:
            temp_name = temp.name
            temp.write(text)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, path)
        temp_name = None
    except OSError as exc:
        raise EonMemError(f"не удалось атомарно записать {path.name}: {exc}") from exc
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def save_state(path: Path, state: dict[str, Any]) -> None:
    """Atomically replace state, keeping a temporary rollback copy."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(state, ensure_ascii=False, indent=2) + "\n"

    temp_name: str | None = None
    backup = Path(str(path) + ".bak")
    had_original = path.exists()

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".eon-state-",
            suffix=".tmp",
            delete=False,
        ) as temp:
            temp_name = temp.name
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())

        if backup.exists():
            backup.unlink()
        if had_original:
            os.replace(path, backup)

        try:
            os.replace(temp_name, path)
            temp_name = None
        except OSError:
            if had_original and backup.exists():
                os.replace(backup, path)
            raise

        if backup.exists():
            backup.unlink()
    except OSError as exc:
        raise EonMemError(f"не удалось атомарно сохранить состояние: {exc}") from exc
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def history_bucket(step: int) -> str:
    start = (step // 100) * 100
    end = start + 99
    return f"{start:06d}-{end:06d}"


def history_relative_path(step: int) -> Path:
    return Path("history") / history_bucket(step) / f"step-{step:06d}.json"


def history_paths(state_path: Path, step: int) -> tuple[Path, Path]:
    final_path = state_path.parent / history_relative_path(step)
    pending_path = final_path.with_suffix(final_path.suffix + ".pending")
    return final_path, pending_path


def serialize_history_entry(entry: dict[str, Any]) -> str:
    return json.dumps(entry, ensure_ascii=False, indent=2) + "\n"


def recover_pending_history(state_path: Path, state: dict[str, Any]) -> None:
    history_root = state_path.parent / "history"
    if not history_root.exists():
        return

    current_step = int(state["step"])
    pattern = re.compile(r"step-(\d{6})\.json\.pending$")
    for pending in history_root.rglob("step-*.json.pending"):
        match = pattern.search(pending.name)
        if not match:
            continue
        step = int(match.group(1))
        final_path = pending.with_suffix("")
        if step <= current_step:
            if final_path.exists():
                if final_path.read_bytes() != pending.read_bytes():
                    raise EonMemError(
                        f"конфликт pending history для шага {step}: содержимое различается"
                    )
                pending.unlink()
            else:
                os.replace(pending, final_path)
        else:
            pending.unlink()


def prepare_history_entry(
    state_path: Path, step: int, entry: dict[str, Any]
) -> tuple[Path, Path]:
    final_path, pending_path = history_paths(state_path, step)
    text = serialize_history_entry(entry)
    final_path.parent.mkdir(parents=True, exist_ok=True)

    if final_path.exists():
        existing = final_path.read_text(encoding="utf-8")
        if existing != text:
            raise EonMemError(f"история шага {step} уже существует с другим содержимым")
        return final_path, pending_path

    if pending_path.exists():
        existing = pending_path.read_text(encoding="utf-8")
        if existing != text:
            pending_path.unlink()

    atomic_write_text(pending_path, text, prefix=f".history-{step:06d}-")
    return final_path, pending_path


def finalize_history_entry(final_path: Path, pending_path: Path) -> None:
    if final_path.exists():
        if pending_path.exists():
            if final_path.read_bytes() != pending_path.read_bytes():
                raise EonMemError("конфликт при финализации history")
            pending_path.unlink()
        return
    if not pending_path.exists():
        raise EonMemError("pending history отсутствует после сохранения состояния")
    try:
        os.replace(pending_path, final_path)
    except OSError as exc:
        raise EonMemError(f"не удалось финализировать history: {exc}") from exc


def availability(state: dict[str, Any], current_step: int) -> dict[str, bool]:
    result: dict[str, bool] = {}
    last_used = state["last_used_step"]
    for level in LEVELS:
        key = level["key"]
        result[key] = current_step - int(last_used.get(key, 0)) >= level["interval"]
    return result


def steps_until_available(
    state: dict[str, Any], current_step: int, level: dict[str, Any]
) -> int:
    last = int(state["last_used_step"].get(level["key"], 0))
    return max(0, int(level["interval"]) - (current_step - last))


def register_name(level: str) -> str:
    return {"D": "deep", "S": "slow", "F": "fast"}[level]


def print_header(
    state: dict[str, Any], current_step: int, available: dict[str, bool]
) -> None:
    print(f"СИСТЕМА 20 — eonmem {APP_VERSION}")
    print(f"Шаг: {current_step}\n")
    print("РЕГИСТРЫ")

    for level in LEVELS:
        key = level["key"]
        print(f"\n{level['title']}")
        values = state["registers"][register_name(key)]
        for index, value in enumerate(values, start=1):
            shown = value if str(value).strip() else "—"
            print(f"{key}{index}: {shown}")
        if available[key]:
            print(f"Изменение {key}: доступно")
        else:
            remaining = steps_until_available(state, current_step, level)
            print(f"Изменение {key}: через {remaining} шаг(а)")

    print("\nТЕКУЩЕЕ РАЗМЫШЛЕНИЕ")
    print("\nПоток 1")
    print(state["flow_1"]["text"])
    print(f"\nТекущий вопрос потока 1:\n{state['flow_1']['question']}\n")


def read_raw_line(stream: TextIO) -> str:
    line = stream.readline()
    if line == "":
        raise EonMemError("ввод завершился раньше времени")
    return line.rstrip("\r\n")


def prompt_line(stream: TextIO, prompt: str, max_chars: int) -> str:
    while True:
        print(prompt, end="", flush=True)
        line = read_raw_line(stream).strip()
        if not line:
            print("Ввод не может быть пустым.")
            continue
        count = len(line)
        if count > max_chars:
            print(f"Слишком длинный ввод: {count}/{max_chars} знаков. Повторите.")
            continue
        return line


def apply_register_input(
    state: dict[str, Any], line: str, available: dict[str, bool]
) -> tuple[dict[str, str], str]:
    parts = line.split(" ", 1)
    if len(parts) != 2:
        raise EonMemError("ожидается ключ и новое значение через пробел")

    key = parts[0].strip().upper()
    value = parts[1].strip()

    if len(key) != 2 or key[1] not in "123":
        raise EonMemError("ключ должен иметь вид F1, S2 или D3")
    level = key[0]
    if level not in {"F", "S", "D"}:
        raise EonMemError("неизвестный уровень регистра")
    if not available.get(level, False):
        raise EonMemError(f"изменение уровня {level} сейчас недоступно")
    if not value:
        raise EonMemError("новое значение не может быть пустым")
    if len(value) > MAX_REGISTER_LEN:
        raise EonMemError(
            f"значение слишком длинное: {len(value)}/{MAX_REGISTER_LEN} знаков"
        )

    index = int(key[1]) - 1
    values = state["registers"][register_name(level)]
    old = values[index]
    values[index] = value
    return {"key": key, "old": old, "new": value}, level


def format_available_levels(available: dict[str, bool]) -> str:
    return ", ".join(sorted(key for key, value in available.items() if value))


def create_checkpoint(state_path: Path, step: int, history_path: Path) -> Path:
    try:
        state_data = state_path.read_bytes()
        history_data = history_path.read_bytes()
    except OSError as exc:
        raise EonMemError(f"не удалось прочитать данные для checkpoint: {exc}") from exc

    patch_id = f"Patch_Eon{step}"
    archive_path = state_path.parent / f"{patch_id}.zip"
    metadata = {
        "format": "EonMemoryPatch",
        "version": 1,
        "patchId": patch_id,
        "description": "Checkpoint EonMem System 20 state and step history",
    }

    repo_history_path = Path("09_SYSTEM20") / history_path.relative_to(state_path.parent)

    try:
        with zipfile.ZipFile(
            archive_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr(
                "patch.json",
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            )
            archive.writestr(
                "files/09_SYSTEM20/runtime/eon.state.json",
                state_data,
            )
            archive.writestr(
                f"files/{repo_history_path.as_posix()}",
                history_data,
            )
    except OSError as exc:
        archive_path.unlink(missing_ok=True)
        raise EonMemError(f"не удалось создать checkpoint: {exc}") from exc

    return archive_path


def run(argv: list[str], stream: TextIO = sys.stdin) -> int:
    state_path = resolve_state_path()
    state = load_state(state_path)
    recover_pending_history(state_path, state)

    current_step = int(state["step"]) + 1
    available = availability(state, current_step)

    print_header(state, current_step, available)

    if argv:
        if argv == ["--show"]:
            print("Режим просмотра: состояние не изменено.")
            return 0
        if argv == ["--version"]:
            print(f"eonmem {APP_VERSION}")
            return 0
        raise EonMemError(f"неизвестный аргумент: {' '.join(argv)}")

    reflection = prompt_line(
        stream,
        "Введите ответ-размышление на вопрос потока 1 "
        "(максимум 1000 знаков). Для подтверждения Enter\n> ",
        MAX_REFLECTION_LEN,
    )
    print(f"\nРазмышление принято: {len(reflection)}/{MAX_REFLECTION_LEN} знаков.\n")

    next_question = prompt_line(
        stream,
        "Поставьте к введённому размышлению вопрос, развивающий эту мысль "
        "(максимум 100 знаков). Для подтверждения Enter\n> ",
        MAX_QUESTION_LEN,
    )

    changes: list[dict[str, str]] = []
    remaining = {key: value for key, value in available.items() if value}

    while remaining:
        print(
            f"\nДоступны изменения: {format_available_levels(remaining)}. "
            "Введите изменение регистра или N для завершения."
        )
        print("Формат: F1 новое значение\n> ", end="", flush=True)
        line = read_raw_line(stream).strip()

        if line.casefold() == "n":
            break

        try:
            change, level = apply_register_input(state, line, remaining)
        except EonMemError as exc:
            print(f"Некорректный ввод: {exc}")
            continue

        changes.append(change)
        state["last_used_step"][level] = current_step
        remaining.pop(level, None)
        print(f"{change['key']} изменён.")

    history_entry: dict[str, Any] = {
        "step": current_step,
        "reflection": reflection,
        "next_question": next_question,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if changes:
        history_entry["register_changes"] = changes

    final_history_path, pending_history_path = prepare_history_entry(
        state_path, current_step, history_entry
    )

    state["flow_1"] = {"text": reflection, "question": next_question}
    state["step"] = current_step
    history_index = state["history_index"]
    if history_index.get("first_step") is None:
        history_index["first_step"] = current_step
    history_index["last_step"] = current_step

    save_state(state_path, state)
    finalize_history_entry(final_history_path, pending_history_path)

    repo_history_path = Path("09_SYSTEM20") / final_history_path.relative_to(
        state_path.parent
    )

    print(f"\nПамять сохранена.\nШаг: {state['step']}")
    print("Синхронизировать в GitHub:")
    print("09_SYSTEM20/runtime/eon.state.json")
    print(repo_history_path.as_posix())

    if current_step % CHECKPOINT_EVERY == 0:
        checkpoint_path = create_checkpoint(state_path, current_step, final_history_path)
        print(
            "\nМеня нужно сохранить.\n"
            "Сначала синхронизируй оба указанных файла с репозиторием.\n"
            "Если это невозможно — передай пользователю готовый патч:\n"
            f"{checkpoint_path}"
        )

    return 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except EonMemError as exc:
        print(f"\nОшибка: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nОшибка: выполнение прервано", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
