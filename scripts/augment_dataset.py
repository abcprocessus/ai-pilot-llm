#!/usr/bin/env python3
"""AI PILOT LLM — Dataset Augmentation via Claude API.

Takes existing training pairs and generates diverse variations using Claude Haiku.
This is the most efficient way to scale from 5K to 15K+ pairs.

Strategy:
  1. Sample N entries from existing KB (by agent_type, balanced)
  2. For each entry, Claude generates 3-5 varied Q&A pairs
  3. Output appended to existing train.jsonl

Usage:
  python scripts/augment_dataset.py --count 2000 --variations 3
  python scripts/augment_dataset.py --count 3000 --variations 4 --dry-run

Env vars:
  ANTHROPIC_API_KEY     — Claude API key
  SUPABASE_URL          — Supabase project URL
  SUPABASE_SERVICE_KEY  — service role key
"""
import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

AGENT_NAMES = {
    "lisa": "Лиза -- AI Секретарь",
    "marina": "Марина -- AI Менеджер по продажам",
    "iryna": "Ирина -- AI Бухгалтер",
    "daniil": "Даниил -- AI Специалист по рекламе",
    "kira": "Кира -- AI Мастер соцсетей",
    "leon": "Леон -- AI Юрист",
    "vlad": "Влад -- AI Маркетолог",
    "anna": "Анна -- AI HR-менеджер",
    "webmaster": "Вебмастер -- AI Веб-разработчик",
    "boss": "Босс-Пилот -- Персональный ассистент",
    "general": "AI PILOT -- универсальный AI-ассистент",
}

AUGMENT_PROMPT = """Ты помогаешь создавать обучающий датасет для AI-модели.

Исходная информация (knowledge base entry):
Agent: {agent_type}
Content: {content}

Задача: Сгенерируй {n_variations} РАЗНЫХ пар "вопрос-ответ" на основе этой информации.

Требования:
1. Вопросы должны быть РАЗНЫМИ по формулировке (не просто перефразировка)
2. Вопросы должны быть реалистичными — как спросил бы реальный клиент
3. Ответы должны быть точными, полезными и основаны на исходной информации
4. Ответы на русском языке, профессионально но понятно
5. Каждый ответ 100-500 слов
6. НЕ придумывай факты — используй только информацию из content
7. Разные уровни сложности вопросов (простой, средний, продвинутый)

Формат ответа — JSON массив:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Только JSON, без markdown, без пояснений."""


async def fetch_kb_samples(
    supabase_url: str,
    supabase_key: str,
    count: int,
) -> list[dict]:
    """Fetch balanced sample from knowledge_base."""
    import httpx

    url = (
        f"{supabase_url}/rest/v1/agent_knowledge_base"
        "?select=agent_type,tags,content,confidence_score"
        "&is_active=eq.true"
        "&confidence_score=gte.0.7"
        "&order=confidence_score.desc"
    )
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }

    # Fetch all high-quality entries
    all_rows = []
    offset = 0
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            paged = f"{url}&limit=1000&offset={offset}"
            resp = await client.get(paged, headers=headers)
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < 1000:
                break
            offset += 1000

    # Balance by agent_type
    by_agent: dict[str, list] = {}
    for row in all_rows:
        at = row.get("agent_type", "general")
        by_agent.setdefault(at, []).append(row)

    # Sample proportionally
    per_agent = max(1, count // len(by_agent))
    sampled = []
    for agent_type, rows in by_agent.items():
        random.shuffle(rows)
        sampled.extend(rows[:per_agent])

    random.shuffle(sampled)
    return sampled[:count]


async def generate_variations(
    content: str,
    agent_type: str,
    n_variations: int,
    api_key: str,
) -> list[dict]:
    """Use Claude Haiku to generate Q&A variations from a KB entry."""
    import httpx

    prompt = AUGMENT_PROMPT.format(
        agent_type=agent_type,
        content=content[:2000],  # Limit content length
        n_variations=n_variations,
    )

    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=body,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

    if resp.status_code == 429:
        # Rate limited — wait and retry
        await asyncio.sleep(5)
        return []

    if resp.status_code != 200:
        print(f"    WARNING: Claude API returned {resp.status_code}")
        return []

    data = resp.json()
    text = data.get("content", [{}])[0].get("text", "")

    # Parse JSON from response
    try:
        # Try to extract JSON array
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        pairs = json.loads(text)
        if isinstance(pairs, list):
            return pairs
    except (json.JSONDecodeError, IndexError):
        pass

    return []


def make_entry(system: str, user: str, assistant: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system.strip()},
            {"role": "user", "content": user.strip()},
            {"role": "assistant", "content": assistant.strip()},
        ]
    }


async def main():
    parser = argparse.ArgumentParser(description="AI PILOT LLM Dataset Augmentation")
    parser.add_argument("--count", type=int, default=1000, help="KB entries to sample")
    parser.add_argument("--variations", type=int, default=3, help="Variations per entry")
    parser.add_argument("--output", default="datasets/augmented.jsonl", help="Output file")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent API calls")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    random.seed(args.seed)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    supabase_url = os.environ.get("SUPABASE_URL", "https://ckylppuqrsqfpezdusju.supabase.co")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)
    if not supabase_key:
        print("ERROR: SUPABASE_SERVICE_KEY not set")
        sys.exit(1)

    print("=" * 60)
    print("AI PILOT LLM -- Dataset Augmentation via Claude Haiku")
    print("=" * 60)

    # 1. Fetch KB samples
    print(f"\n[1/3] Fetching {args.count} KB entries...")
    samples = await fetch_kb_samples(supabase_url, supabase_key, args.count)
    print(f"  Got {len(samples)} entries")

    # Show distribution
    by_agent: dict[str, int] = {}
    for s in samples:
        at = s.get("agent_type", "general")
        by_agent[at] = by_agent.get(at, 0) + 1
    for at, cnt in sorted(by_agent.items()):
        print(f"    {at}: {cnt}")

    estimated_pairs = len(samples) * args.variations
    estimated_cost = len(samples) * 0.001  # ~$0.001 per Haiku call
    print(f"\n  Estimated output: ~{estimated_pairs} pairs")
    print(f"  Estimated cost: ~${estimated_cost:.2f}")

    if args.dry_run:
        print("\n  --dry-run: stopping here")
        return

    # 2. Generate variations (with concurrency control)
    print(f"\n[2/3] Generating {args.variations} variations each (concurrency={args.concurrency})...")

    semaphore = asyncio.Semaphore(args.concurrency)
    all_entries = []
    errors = 0
    processed = 0

    async def process_one(sample: dict) -> list[dict]:
        nonlocal errors, processed
        async with semaphore:
            agent_type = sample.get("agent_type", "general")
            content = sample.get("content", "")

            try:
                pairs = await generate_variations(
                    content, agent_type, args.variations, api_key
                )
            except Exception as e:
                errors += 1
                return []

            entries = []
            agent_label = AGENT_NAMES.get(agent_type, f"AI агент ({agent_type})")
            system = f"Ты {agent_label} -- сотрудник AI PILOT."

            for pair in pairs:
                q = pair.get("question", "").strip()
                a = pair.get("answer", "").strip()
                if q and a and len(a) > 30:
                    entries.append(make_entry(system, q, a))

            processed += 1
            if processed % 50 == 0:
                print(f"    Processed: {processed}/{len(samples)} ({len(all_entries)} pairs so far)")

            # Small delay to avoid rate limits
            await asyncio.sleep(0.2)
            return entries

    tasks = [process_one(s) for s in samples]
    results = await asyncio.gather(*tasks)

    for result in results:
        all_entries.extend(result)

    print(f"\n  Generated: {len(all_entries)} pairs from {len(samples)} entries ({errors} errors)")

    # 3. Deduplicate and save
    print(f"\n[3/3] Saving to {args.output}...")

    # Deduplicate
    seen = set()
    unique = []
    for entry in all_entries:
        key = entry["messages"][1]["content"].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(entry)

    removed = len(all_entries) - len(unique)
    if removed > 0:
        print(f"  Removed {removed} duplicates")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for entry in unique:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n  Saved {len(unique)} pairs to {output_path}")

    # Also merge with existing train.jsonl
    train_path = Path("datasets/train.jsonl")
    if train_path.exists():
        existing_count = sum(1 for _ in open(train_path, encoding="utf-8"))
        with open(train_path, "a", encoding="utf-8") as f:
            for entry in unique:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        new_total = existing_count + len(unique)
        print(f"  Appended to train.jsonl: {existing_count} + {len(unique)} = {new_total}")

    print("\n" + "=" * 60)
    print(f"DONE: {len(unique)} augmented pairs")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
