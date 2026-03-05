#!/usr/bin/env python3
"""Валидация датасета перед fine-tune.

Проверяет:
1. Формат JSON — все строки корректный JSON
2. Структура — messages=[system, user, assistant]
3. Роли — правильный порядок (system, user, assistant)
4. Длины — нет пустых, нет слишком коротких, нет слишком длинных
5. Баланс агентов — все 9+ агентов представлены
6. Обрезанные ответы — нет trailing ---, незавершённых предложений
7. Язык — процент русского контента
8. Статистика длин — гистограмма для выбора max_seq_len

Использование:
  python scripts/validate_dataset.py
  python scripts/validate_dataset.py --file datasets/train.jsonl
  python scripts/validate_dataset.py --verbose
"""
import json
import sys
import re
from pathlib import Path
from collections import Counter, defaultdict

# Поддержка кириллицы в Windows stdout
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATASETS_DIR = Path("datasets")

# Агенты AI PILOT
KNOWN_AGENTS = [
    "лиза", "марина", "ирина", "даниил", "кира",
    "леон", "влад", "анна", "вебмастер",
    "lisa", "marina", "iryna", "daniil", "kira",
    "leon", "vlad", "anna", "webmaster",
]

# Признаки обрезанного ответа
TRUNCATION_MARKERS = ["---", "- -", "...", "…"]
INCOMPLETE_ENDINGS = set(",:-([{")


def detect_agent(system_prompt: str) -> str:
    """Определяем агента по system prompt."""
    lower = system_prompt.lower()
    for agent in KNOWN_AGENTS:
        if agent in lower:
            # Нормализуем к русским именам
            mapping = {
                "lisa": "лиза", "marina": "марина", "iryna": "ирина",
                "daniil": "даниил", "kira": "кира", "leon": "леон",
                "vlad": "влад", "anna": "анна", "webmaster": "вебмастер",
            }
            return mapping.get(agent, agent)
    # Общий/образовательный
    if "ai pilot" in lower or "аи пилот" in lower or "ai-pilot" in lower:
        return "платформа"
    return "другое"


def is_russian(text: str) -> bool:
    """Проверяем содержит ли текст кириллицу."""
    cyrillic = len(re.findall(r"[а-яА-ЯёЁ]", text))
    total = len(re.findall(r"\w", text))
    if total == 0:
        return False
    return cyrillic / total > 0.3


def check_truncation(text: str) -> str | None:
    """Проверяем обрезан ли ответ. Возвращает описание проблемы или None."""
    stripped = text.rstrip()
    for marker in TRUNCATION_MARKERS:
        if stripped.endswith(marker):
            return f"trailing '{marker}'"
    if stripped and stripped[-1] in INCOMPLETE_ENDINGS:
        return f"ends with '{stripped[-1]}'"
    return None


def validate_file(filepath: Path, verbose: bool = False) -> dict:
    """Валидация одного JSONL файла."""
    stats = {
        "total_lines": 0,
        "valid_entries": 0,
        "json_errors": 0,
        "structure_errors": 0,
        "role_errors": 0,
        "empty_fields": 0,
        "short_answers": 0,  # <50 символов
        "long_answers": 0,   # >5000 символов
        "truncated": 0,
        "russian_count": 0,
        "agents": Counter(),
        "answer_lengths": [],
        "question_lengths": [],
        "system_lengths": [],
        "issues": [],
    }

    if not filepath.exists():
        stats["issues"].append(f"Файл не найден: {filepath}")
        return stats

    with open(filepath, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            stats["total_lines"] += 1
            line = line.strip()
            if not line:
                continue

            # 1. JSON парсинг
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                stats["json_errors"] += 1
                stats["issues"].append(f"  Строка {line_num}: JSON error: {e}")
                continue

            # 2. Структура
            if not isinstance(entry, dict) or "messages" not in entry:
                stats["structure_errors"] += 1
                stats["issues"].append(f"  Строка {line_num}: нет 'messages'")
                continue

            msgs = entry["messages"]
            if not isinstance(msgs, list) or len(msgs) < 3:
                stats["structure_errors"] += 1
                stats["issues"].append(f"  Строка {line_num}: messages < 3")
                continue

            # 3. Роли
            expected_roles = ["system", "user", "assistant"]
            actual_roles = [m.get("role") for m in msgs[:3]]
            if actual_roles != expected_roles:
                stats["role_errors"] += 1
                stats["issues"].append(f"  Строка {line_num}: роли={actual_roles}")
                continue

            # 4. Содержимое
            system_text = msgs[0].get("content", "").strip()
            user_text = msgs[1].get("content", "").strip()
            answer_text = msgs[2].get("content", "").strip()

            if not system_text or not user_text or not answer_text:
                stats["empty_fields"] += 1
                stats["issues"].append(f"  Строка {line_num}: пустое поле")
                continue

            stats["valid_entries"] += 1

            # 5. Длины
            stats["system_lengths"].append(len(system_text))
            stats["question_lengths"].append(len(user_text))
            stats["answer_lengths"].append(len(answer_text))

            if len(answer_text) < 50:
                stats["short_answers"] += 1
                if verbose:
                    stats["issues"].append(
                        f"  Строка {line_num}: короткий ответ ({len(answer_text)} символов): {answer_text[:80]}..."
                    )

            if len(answer_text) > 5000:
                stats["long_answers"] += 1

            # 6. Обрезка
            trunc = check_truncation(answer_text)
            if trunc:
                stats["truncated"] += 1
                if verbose:
                    stats["issues"].append(f"  Строка {line_num}: обрезан ({trunc})")

            # 7. Язык
            if is_russian(answer_text):
                stats["russian_count"] += 1

            # 8. Агент
            agent = detect_agent(system_text)
            stats["agents"][agent] += 1

    return stats


def print_histogram(lengths: list[int], title: str, bins: list[int] | None = None):
    """Текстовая гистограмма длин."""
    if not lengths:
        return
    if bins is None:
        bins = [0, 100, 250, 500, 1000, 2000, 3000, 5000, 10000]

    print(f"\n  {title}:")
    for i in range(len(bins)):
        lo = bins[i]
        hi = bins[i + 1] if i + 1 < len(bins) else float("inf")
        count = sum(1 for l in lengths if lo <= l < hi)
        pct = count / len(lengths) * 100
        bar = "█" * int(pct / 2)
        hi_label = str(hi) if hi != float("inf") else "∞"
        print(f"    {lo:>5}-{hi_label:>5}: {count:>5} ({pct:5.1f}%) {bar}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Валидация датасета AI PILOT LLM")
    parser.add_argument("--file", default=None, help="Конкретный файл (иначе train.jsonl + val.jsonl)")
    parser.add_argument("--verbose", action="store_true", help="Подробный вывод проблем")
    args = parser.parse_args()

    print("=" * 60)
    print("AI PILOT LLM — Валидация датасета")
    print("=" * 60)

    if args.file:
        files = [Path(args.file)]
    else:
        files = [DATASETS_DIR / "train.jsonl", DATASETS_DIR / "val.jsonl"]

    total_stats = {
        "valid": 0, "errors": 0, "truncated": 0,
        "agents": Counter(), "answer_lengths": [],
        "question_lengths": [], "russian": 0, "total": 0,
    }

    all_ok = True

    for filepath in files:
        print(f"\n--- {filepath} ---")
        stats = validate_file(filepath, verbose=args.verbose)

        errors = (stats["json_errors"] + stats["structure_errors"] +
                  stats["role_errors"] + stats["empty_fields"])

        print(f"  Строк: {stats['total_lines']}")
        print(f"  Валидных: {stats['valid_entries']}")
        print(f"  JSON ошибок: {stats['json_errors']}")
        print(f"  Ошибок структуры: {stats['structure_errors']}")
        print(f"  Ошибок ролей: {stats['role_errors']}")
        print(f"  Пустых полей: {stats['empty_fields']}")
        print(f"  Коротких ответов (<50): {stats['short_answers']}")
        print(f"  Длинных ответов (>5000): {stats['long_answers']}")
        print(f"  Обрезанных: {stats['truncated']}")
        print(f"  Русский язык: {stats['russian_count']}/{stats['valid_entries']} "
              f"({stats['russian_count']/max(stats['valid_entries'],1)*100:.1f}%)")

        if stats["agents"]:
            print(f"\n  Агенты ({len(stats['agents'])} типов):")
            for agent, count in stats["agents"].most_common():
                pct = count / max(stats["valid_entries"], 1) * 100
                print(f"    {agent:>15}: {count:>5} ({pct:.1f}%)")

        if stats["answer_lengths"]:
            avg_len = sum(stats["answer_lengths"]) / len(stats["answer_lengths"])
            max_len = max(stats["answer_lengths"])
            min_len = min(stats["answer_lengths"])
            print(f"\n  Длина ответов: min={min_len}, avg={avg_len:.0f}, max={max_len}")

        if args.verbose and stats["issues"]:
            print(f"\n  Проблемы ({len(stats['issues'])}):")
            for issue in stats["issues"][:30]:
                print(issue)
            if len(stats["issues"]) > 30:
                print(f"  ... и ещё {len(stats['issues']) - 30}")

        # Накопление общей статистики
        total_stats["valid"] += stats["valid_entries"]
        total_stats["errors"] += errors
        total_stats["truncated"] += stats["truncated"]
        total_stats["agents"].update(stats["agents"])
        total_stats["answer_lengths"].extend(stats["answer_lengths"])
        total_stats["question_lengths"].extend(stats["question_lengths"])
        total_stats["russian"] += stats["russian_count"]
        total_stats["total"] += stats["total_lines"]

        if errors > 0:
            all_ok = False

    # Итоговая статистика
    print("\n" + "=" * 60)
    print("ИТОГО")
    print("=" * 60)
    print(f"  Всего записей: {total_stats['valid']}")
    print(f"  Ошибки: {total_stats['errors']}")
    print(f"  Обрезанные: {total_stats['truncated']}")
    print(f"  Русский: {total_stats['russian']}/{total_stats['valid']} "
          f"({total_stats['russian']/max(total_stats['valid'],1)*100:.1f}%)")

    # Баланс агентов
    agent_count = len(total_stats["agents"])
    print(f"\n  Агентов: {agent_count} типов")
    if agent_count < 9:
        print(f"  ⚠️  ВНИМАНИЕ: менее 9 агентов! Проверьте баланс")
        all_ok = False

    # Гистограмма ответов
    print_histogram(total_stats["answer_lengths"], "Распределение длин ответов (символы)")

    # Рекомендация max_seq_len (в токенах, ~1 токен ≈ 3-4 символа для русского)
    if total_stats["answer_lengths"]:
        p95 = sorted(total_stats["answer_lengths"])[int(len(total_stats["answer_lengths"]) * 0.95)]
        p99 = sorted(total_stats["answer_lengths"])[int(len(total_stats["answer_lengths"]) * 0.99)]
        avg_total = sum(total_stats["answer_lengths"]) / len(total_stats["answer_lengths"])
        # Прибавляем среднюю длину system + question
        avg_input = (
            sum(total_stats["question_lengths"]) / max(len(total_stats["question_lengths"]), 1)
        )
        tokens_p95 = int((p95 + avg_input) / 3)  # ~3 символа/токен для русского
        tokens_p99 = int((p99 + avg_input) / 3)

        print(f"\n  Рекомендации для max_seq_len:")
        print(f"    P95 ответов: {p95} символов (~{tokens_p95} токенов)")
        print(f"    P99 ответов: {p99} символов (~{tokens_p99} токенов)")
        if tokens_p95 <= 2048:
            print(f"    → max_seq_len=2048 покроет 95%+ данных ✓")
        elif tokens_p95 <= 4096:
            print(f"    → max_seq_len=4096 рекомендуется (P95 > 2048 токенов)")
        else:
            print(f"    → max_seq_len=8192 рекомендуется (P95 > 4096 токенов)")

    # Финальный вердикт
    print("\n" + "=" * 60)
    if all_ok and total_stats["truncated"] == 0:
        print("✅ ДАТАСЕТ ГОТОВ К FINE-TUNE")
    elif all_ok:
        print(f"⚠️  ДАТАСЕТ ОК, но {total_stats['truncated']} обрезанных записей")
        print("   Запустите merge_datasets.py для автопочинки")
    else:
        print("❌ ДАТАСЕТ ТРЕБУЕТ ИСПРАВЛЕНИЙ")
        print(f"   Ошибок: {total_stats['errors']}, обрезанных: {total_stats['truncated']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
