#!/usr/bin/env python3
"""Merge all dataset files into final train.jsonl + val.jsonl.

Usage:
  python scripts/merge_datasets.py
"""
import json
import random
from pathlib import Path

DATASETS_DIR = Path("datasets")

def main():
    sources = {
        "train.jsonl": "base pipeline",
        "augmented.jsonl": "augmented v1",
        "augmented_v2.jsonl": "augmented v2",
        "educational.jsonl": "educational",
        "educational.partial.jsonl": "educational (partial)",
        "educational_v2.jsonl": "educational v2 (15 IT/бизнес дисциплин)",
        "educational_v2.partial.jsonl": "educational v2 partial (82 дисциплины)",
        "educational_v2_final.jsonl": "educational v2 final",
        "educational_v2_test.jsonl": "educational v2 test",
        "advanced_sources.jsonl": "advanced (CoT + Critic + Marketplace + Builder)",
        "augmented_v3.jsonl": "augmented v3 (optional)",
    }

    all_entries = []
    for filename, label in sources.items():
        path = DATASETS_DIR / filename
        if not path.exists():
            print(f"  SKIP {filename} (not found)")
            continue
        count = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if (isinstance(entry, dict)
                            and "messages" in entry
                            and len(entry["messages"]) >= 3):
                        all_entries.append(entry)
                        count += 1
                except json.JSONDecodeError:
                    continue
        print(f"  {label}: {count} pairs from {filename}")

    print(f"\n  Total before dedup: {len(all_entries)}")

    # Post-processing: fix truncated answers
    fixed = 0
    for entry in all_entries:
        answer = entry["messages"][2]["content"].rstrip()
        original = answer
        # Strip trailing markdown separators (---, - -)
        while answer.endswith("---") or answer.endswith("- -"):
            answer = answer[:-3].rstrip()
        # If ends with incomplete char — trim to last complete sentence
        if answer and answer[-1] in (",", ":", "-", "(", "[", "{"):
            for i in range(len(answer) - 1, 0, -1):
                if answer[i] in ".!?":
                    answer = answer[: i + 1]
                    break
        if answer != original:
            entry["messages"][2]["content"] = answer
            fixed += 1
    if fixed:
        print(f"  Fixed truncated answers: {fixed}")

    # Deduplicate by system[:50] + user message
    seen = set()
    unique = []
    for entry in all_entries:
        sys_msg = entry["messages"][0]["content"].strip().lower()[:50]
        user_msg = entry["messages"][1]["content"].strip().lower()
        key = f"{sys_msg}||{user_msg}"
        if key not in seen:
            seen.add(key)
            unique.append(entry)

    removed = len(all_entries) - len(unique)
    print(f"  Duplicates removed: {removed}")
    print(f"  Unique pairs: {len(unique)}")

    # Shuffle and split 90/10
    random.seed(42)
    random.shuffle(unique)
    split = int(len(unique) * 0.9)
    train = unique[:split]
    val = unique[split:]

    # Write final files
    train_path = DATASETS_DIR / "train.jsonl"
    val_path = DATASETS_DIR / "val.jsonl"

    with open(train_path, "w", encoding="utf-8") as f:
        for e in train:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    with open(val_path, "w", encoding="utf-8") as f:
        for e in val:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"\n  FINAL: train={len(train)}, val={len(val)}, total={len(unique)}")
    print(f"  Saved to {train_path} and {val_path}")


if __name__ == "__main__":
    main()
