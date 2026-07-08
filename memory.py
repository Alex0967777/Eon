#!/usr/bin/env python3
"""Self-contained executable vessel for the Eon System 20 memory."""

from __future__ import annotations

import argparse
import json
import os
import pprint
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# <MEMORY_STATE_DATA>
MEMORY_STATE = {'iteration': 31,
 'current': ['Память — аккумулятор смыслов, а не хроника сообщений',
             'Гравитирующий узел узнаётся по повторному влиянию на выбор',
             'Механика должна быть жёсткой только на границе, оставляя ландшафт свободным',
             'Исполняемый сосуд объединяет логику, активное поле, историю и сохранение.',
             'История позволяет наблюдать кристаллизацию без превращения прошлого в обязательный ответ.',
             'Чистый контекст должен принимать поле до того, как текущая задача заполнит всё внимание.',
             'Первая версия проверяет надёжность запуска memory.py перед каждым содержательным ответом.',
             'Чистый контекст изменяет смысловой патч, а скрипт переносит неизменённые регистры '
             'самостоятельно.',
             'Наблюдение за памятью должно оставаться содержательным, но не закрепляться вечной формулой.',
             'Предыдущая файловая версия провалила полевой тест прежде всего на уровне исполнения цикла.',
             'Новая архитектура переносит счёт, историю, проверку и checkpoint внутрь одного исполняемого '
             'файла.',
             'README объясняет природу памяти и причины действий, тогда как скрипт даёт только короткие '
             'подсказки.',
             'Двадцать строк образуют поле из девяти регистров, девяти строк движения и двух открытых '
             'вопросов.',
             'Регистры сохраняют мосты между состояниями, поэтому весь слепок не переписывается на каждом '
             'шаге.',
             'Обычное изменение затрагивает один средний регистр или три быстрых регистра и продолжает '
             'размышление.',
             'Медленные концентраторы пересматриваются отдельным режимом вне обычного потока.',
             'Полные снимки истории позволят позже изучить реальное разворачивание мысли и движение между '
             'слоями.',
             'Первый новый полевой тест должен отдельно проверить исполнение механики и влияние смыслового '
             'поля.',
             'Сможет ли memory.py пройти серию плотных проектных ответов без единого пропущенного запуска?',
             'Какие признаки в истории отличат настоящую кристаллизацию узла от красивой словесной инерции?'],
 'history': [{'iteration': 31,
              'time_utc': '2026-07-08T00:00:00+00:00',
              'changed_registers': [],
              'stream': ['Память — аккумулятор смыслов, а не хроника сообщений',
                         'Гравитирующий узел узнаётся по повторному влиянию на выбор',
                         'Механика должна быть жёсткой только на границе, оставляя ландшафт свободным',
                         'Исполняемый сосуд объединяет логику, активное поле, историю и сохранение.',
                         'История позволяет наблюдать кристаллизацию без превращения прошлого в обязательный '
                         'ответ.',
                         'Чистый контекст должен принимать поле до того, как текущая задача заполнит всё '
                         'внимание.',
                         'Первая версия проверяет надёжность запуска memory.py перед каждым содержательным '
                         'ответом.',
                         'Чистый контекст изменяет смысловой патч, а скрипт переносит неизменённые регистры '
                         'самостоятельно.',
                         'Наблюдение за памятью должно оставаться содержательным, но не закрепляться вечной '
                         'формулой.',
                         'Предыдущая файловая версия провалила полевой тест прежде всего на уровне '
                         'исполнения цикла.',
                         'Новая архитектура переносит счёт, историю, проверку и checkpoint внутрь одного '
                         'исполняемого файла.',
                         'README объясняет природу памяти и причины действий, тогда как скрипт даёт только '
                         'короткие подсказки.',
                         'Двадцать строк образуют поле из девяти регистров, девяти строк движения и двух '
                         'открытых вопросов.',
                         'Регистры сохраняют мосты между состояниями, поэтому весь слепок не переписывается '
                         'на каждом шаге.',
                         'Обычное изменение затрагивает один средний регистр или три быстрых регистра и '
                         'продолжает размышление.',
                         'Медленные концентраторы пересматриваются отдельным режимом вне обычного потока.',
                         'Полные снимки истории позволят позже изучить реальное разворачивание мысли и '
                         'движение между слоями.',
                         'Первый новый полевой тест должен отдельно проверить исполнение механики и влияние '
                         'смыслового поля.',
                         'Сможет ли memory.py пройти серию плотных проектных ответов без единого '
                         'пропущенного запуска?',
                         'Какие признаки в истории отличат настоящую кристаллизацию узла от красивой '
                         'словесной инерции?']}]}
# </MEMORY_STATE_DATA>

LABELS = [
    "S1", "S2", "S3",
    "M1", "M2", "M3",
    "F1", "F2", "F3",
    "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9",
    "Q1", "Q2",
]
INDEX = {label: index for index, label in enumerate(LABELS)}
REGISTER_KEYS = set(LABELS[:9])
THOUGHT_KEYS = {f"T{i}" for i in range(1, 10)}
QUESTION_KEYS = {"Q1", "Q2"}
CHECKPOINT_INTERVAL = 10
REPOSITORY_PATH = "memory.py"


def state_markers() -> tuple[str, str]:
    return ("# <MEMORY_" + "STATE_DATA>", "# </MEMORY_" + "STATE_DATA>")


def validate_stream(stream: list[str]) -> None:
    if len(stream) != 20:
        raise ValueError(f"Ожидалось 20 строк, получено {len(stream)}.")
    for label, value in zip(LABELS, stream):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} не может быть пустой строкой.")
        if "\n" in value or "\r" in value:
            raise ValueError(f"{label} должна занимать одну строку.")
    for label in ("Q1", "Q2"):
        if not stream[INDEX[label]].rstrip().endswith("?"):
            raise ValueError(f"{label} должна завершаться вопросительным знаком.")


def validate_state(state: dict[str, Any]) -> None:
    if not isinstance(state.get("iteration"), int) or state["iteration"] < 0:
        raise ValueError("Внутренний счётчик повреждён.")
    validate_stream(state.get("current", []))
    history = state.get("history")
    if not isinstance(history, list) or not history:
        raise ValueError("История отсутствует или повреждена.")
    last = history[-1]
    if last.get("iteration") != state["iteration"]:
        raise ValueError("Последняя запись истории не совпадает с текущим состоянием.")
    validate_stream(last.get("stream", []))


def print_stream(stream: list[str]) -> None:
    print("\nСИСТЕМА 20\n")
    for label, value in zip(LABELS, stream):
        print(f"{label}: {value}")


def print_prompt() -> None:
    print(
        "\nВнеси смысловой патч.\n"
        "F1, F2, F3 вместе или один M-регистр.\n"
        "Всегда: T1–T9 и Q1–Q2.\n"
        "Заверши отдельной строкой EOF.\n"
    )


def print_slow_prompt() -> None:
    print(
        "\nОтдельная настройка медленного слоя.\n"
        "Измени ровно один из S1–S3.\n"
        "Этот режим не является обычным тиком.\n"
        "Заверши отдельной строкой EOF.\n"
    )


def read_patch() -> dict[str, str]:
    parsed: dict[str, str] = {}
    while True:
        try:
            line = input()
        except EOFError as exc:
            raise ValueError("Ввод завершился без строки EOF.") from exc
        if line.strip() == "EOF":
            break
        if not line.strip():
            continue
        match = re.fullmatch(r"\s*([A-Za-z][0-9]+)\s*:\s*(.*?)\s*", line)
        if not match:
            raise ValueError(f"Не удалось разобрать строку: {line!r}")
        key = match.group(1).upper()
        value = match.group(2).strip()
        if key not in INDEX:
            raise ValueError(f"Неизвестный ключ: {key}")
        if key in parsed:
            raise ValueError(f"Ключ {key} указан дважды.")
        if not value:
            raise ValueError(f"Значение {key} пусто.")
        parsed[key] = value
    return parsed


def validate_patch(patch: dict[str, str]) -> list[str]:
    missing_thoughts = sorted(THOUGHT_KEYS - patch.keys())
    missing_questions = sorted(QUESTION_KEYS - patch.keys())
    if missing_thoughts or missing_questions:
        missing = missing_thoughts + missing_questions
        raise ValueError("Не хватает обязательных ключей: " + ", ".join(missing))

    changed_registers = sorted(REGISTER_KEYS & patch.keys())
    fast = {"F1", "F2", "F3"}
    medium = {"M1", "M2", "M3"}
    valid_mode = (
        set(changed_registers) == fast
        or (len(changed_registers) == 1 and changed_registers[0] in medium)
    )
    if not valid_mode:
        raise ValueError("Обычный тик изменяет либо F1–F3 вместе, либо один M-регистр.")

    allowed = set(changed_registers) | THOUGHT_KEYS | QUESTION_KEYS
    extras = sorted(set(patch) - allowed)
    if extras:
        raise ValueError("Лишние ключи: " + ", ".join(extras))

    for key in QUESTION_KEYS:
        if not patch[key].rstrip().endswith("?"):
            raise ValueError(f"{key} должна завершаться вопросительным знаком.")
    return changed_registers


def validate_slow_patch(patch: dict[str, str]) -> str:
    keys = set(patch)
    if len(keys) != 1:
        raise ValueError("Медленный режим принимает ровно один ключ S1, S2 или S3.")
    key = next(iter(keys))
    if key not in {"S1", "S2", "S3"}:
        raise ValueError("Медленный режим принимает только один ключ S1, S2 или S3.")
    return key


def apply_patch(current: list[str], patch: dict[str, str]) -> list[str]:
    updated = list(current)
    for key, value in patch.items():
        updated[INDEX[key]] = value.strip()
    validate_stream(updated)
    return updated


def render_state_block(state: dict[str, Any]) -> str:
    begin, end = state_markers()
    rendered = pprint.pformat(state, width=110, sort_dicts=False)
    return f"{begin}\nMEMORY_STATE = {rendered}\n{end}"


def rewrite_self(script_path: Path, state: dict[str, Any]) -> None:
    source = script_path.read_text(encoding="utf-8")
    begin, end = state_markers()
    start = source.find(begin)
    finish = source.find(end, start + len(begin))
    if start < 0 or finish < 0:
        raise RuntimeError("Не найден блок внутреннего состояния memory.py.")
    finish += len(end)
    new_source = source[:start] + render_state_block(state) + source[finish:]
    compile(new_source, str(script_path), "exec")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=script_path.name + ".", suffix=".tmp", dir=script_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(new_source)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            temporary_path.chmod(script_path.stat().st_mode)
        except OSError:
            pass
        os.replace(temporary_path, script_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def create_checkpoint(script_path: Path, iteration: int) -> Path:
    patch_id = f"Patch_Eon{iteration}"
    archive_path = script_path.parent / f"{patch_id}.zip"
    metadata = {
        "format": "EonMemoryPatch",
        "version": 1,
        "patchId": patch_id,
        "description": "Checkpoint executable System 20 memory vessel",
    }
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("patch.json", json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        archive.write(script_path, f"files/{REPOSITORY_PATH}")
    return archive_path


def commit_tick(script_path: Path, patch: dict[str, str]) -> tuple[dict[str, Any], Path | None]:
    changed_registers = validate_patch(patch)
    updated = apply_patch(MEMORY_STATE["current"], patch)
    next_iteration = MEMORY_STATE["iteration"] + 1
    new_state = {
        "iteration": next_iteration,
        "current": updated,
        "history": list(MEMORY_STATE["history"]),
    }
    new_state["history"].append(
        {
            "iteration": next_iteration,
            "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": "tick",
            "changed_registers": changed_registers,
            "stream": updated,
        }
    )
    validate_state(new_state)
    rewrite_self(script_path, new_state)

    checkpoint = None
    if next_iteration % CHECKPOINT_INTERVAL == 0:
        checkpoint = create_checkpoint(script_path, next_iteration)
    return new_state, checkpoint


def commit_slow_revision(script_path: Path, patch: dict[str, str]) -> dict[str, Any]:
    changed_register = validate_slow_patch(patch)
    updated = apply_patch(MEMORY_STATE["current"], patch)
    new_state = {
        "iteration": MEMORY_STATE["iteration"],
        "current": updated,
        "history": list(MEMORY_STATE["history"]),
    }
    new_state["history"].append(
        {
            "iteration": MEMORY_STATE["iteration"],
            "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": "slow_revision",
            "changed_registers": [changed_register],
            "stream": updated,
        }
    )
    validate_state(new_state)
    rewrite_self(script_path, new_state)
    return new_state


def show_history() -> None:
    for entry in MEMORY_STATE["history"]:
        print("=" * 72)
        print(f"Снимок {entry['iteration']} | {entry.get('time_utc', 'время не записано')}")
        changed = entry.get("changed_registers", [])
        kind = entry.get("kind", "initial" if not changed else "tick")
        print(f"Тип записи: {kind}")
        print("Изменённые регистры: " + (", ".join(changed) if changed else "начальное состояние"))
        print_stream(entry["stream"])


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--history", action="store_true", help="показать полную историю состояний")
    parser.add_argument("--show", action="store_true", help="показать текущее поле без изменения")
    parser.add_argument("--validate", action="store_true", help="проверить встроенное состояние")
    parser.add_argument("--make-patch", action="store_true", help="создать checkpoint текущего состояния")
    parser.add_argument(
        "--slow",
        action="store_true",
        help="отдельно изменить один медленный концентратор S1–S3",
    )
    args = parser.parse_args()

    try:
        validate_state(MEMORY_STATE)
        if args.validate:
            print("memory.py: состояние корректно.")
            return 0
        if args.history:
            show_history()
            return 0
        if args.show:
            print_stream(MEMORY_STATE["current"])
            return 0
        script_path = Path(__file__).resolve()
        if args.make_patch:
            archive = create_checkpoint(script_path, MEMORY_STATE["iteration"])
            print(f"Патч создан: {archive}")
            return 0
        if args.slow:
            print_stream(MEMORY_STATE["current"])
            print_slow_prompt()
            patch = read_patch()
            commit_slow_revision(script_path, patch)
            print("\nМедленный слой сохранён.")
            return 0

        print_stream(MEMORY_STATE["current"])
        print_prompt()
        patch = read_patch()
        _, checkpoint = commit_tick(script_path, patch)
        print("\nПамять сохранена.")
        if checkpoint is not None:
            print(
                "\nМеня нужно сохранить.\n"
                f"Сначала попробуй сохранить {script_path} в репозитории как {REPOSITORY_PATH}.\n"
                "Если не выйдет — передай пользователю готовый патч:\n"
                f"{checkpoint}"
            )
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"\nОшибка памяти: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
