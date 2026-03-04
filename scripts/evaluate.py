#!/usr/bin/env python3
"""AI PILOT LLM — Evaluation script.

Tests the fine-tuned model against val.jsonl and compares with Claude baseline.

Usage:
  # Evaluate local model (requires LOCAL_LLM_URL):
  python scripts/evaluate.py

  # Evaluate against Claude (requires ANTHROPIC_API_KEY):
  python scripts/evaluate.py --compare-claude

  # Evaluate GGUF via Ollama:
  python scripts/evaluate.py --provider ollama --model ai-pilot-llm

  # Custom dataset:
  python scripts/evaluate.py --val-file datasets/val.jsonl --sample 50
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path


def load_val_samples(val_path: str, sample_size: int) -> list[dict]:
    """Load and optionally sample from validation set."""
    import random
    random.seed(42)
    samples = []
    with open(val_path, encoding="utf-8") as f:
        for line in f:
            samples.append(json.loads(line))
    if sample_size and sample_size < len(samples):
        samples = random.sample(samples, sample_size)
    return samples


async def eval_local(samples: list[dict], base_url: str, model: str) -> list[dict]:
    """Evaluate against local vLLM/Ollama endpoint."""
    import httpx

    results = []
    client = httpx.AsyncClient(timeout=30.0)

    for i, sample in enumerate(samples):
        msgs = sample["messages"]
        system = msgs[0]["content"]
        user = msgs[1]["content"]
        expected = msgs[2]["content"]

        start = time.time()
        try:
            resp = await client.post(
                f"{base_url}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "max_tokens": 1024,
                },
            )
            latency_ms = (time.time() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                generated = data["choices"][0]["message"]["content"]
                tokens = data.get("usage", {}).get("completion_tokens", 0)
            else:
                generated = f"ERROR: HTTP {resp.status_code}"
                tokens = 0
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            generated = f"ERROR: {e}"
            tokens = 0

        # Simple quality metrics
        result = {
            "index": i,
            "user": user[:100],
            "expected_len": len(expected),
            "generated_len": len(generated),
            "latency_ms": round(latency_ms),
            "tokens": tokens,
            "is_json": _is_valid_json(generated),
            "is_error": generated.startswith("ERROR:"),
            "overlap_score": _text_overlap(expected, generated),
        }
        results.append(result)

        if (i + 1) % 10 == 0 or i == len(samples) - 1:
            print(f"  [{i+1}/{len(samples)}] latency={latency_ms:.0f}ms overlap={result['overlap_score']:.2f}")

    await client.aclose()
    return results


async def eval_claude(samples: list[dict]) -> list[dict]:
    """Evaluate against Claude API for baseline comparison."""
    import httpx
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  WARNING: ANTHROPIC_API_KEY not set, skipping Claude eval")
        return []

    results = []
    client = httpx.AsyncClient(timeout=60.0)

    for i, sample in enumerate(samples):
        msgs = sample["messages"]
        system = msgs[0]["content"]
        user = msgs[1]["content"]
        expected = msgs[2]["content"]

        start = time.time()
        try:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1024,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            latency_ms = (time.time() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                generated = data["content"][0]["text"]
                tokens = data["usage"]["output_tokens"]
            else:
                generated = f"ERROR: HTTP {resp.status_code}"
                tokens = 0
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            generated = f"ERROR: {e}"
            tokens = 0

        result = {
            "index": i,
            "user": user[:100],
            "expected_len": len(expected),
            "generated_len": len(generated),
            "latency_ms": round(latency_ms),
            "tokens": tokens,
            "is_json": _is_valid_json(generated),
            "is_error": generated.startswith("ERROR:"),
            "overlap_score": _text_overlap(expected, generated),
        }
        results.append(result)

        if (i + 1) % 10 == 0 or i == len(samples) - 1:
            print(f"  [{i+1}/{len(samples)}] latency={latency_ms:.0f}ms overlap={result['overlap_score']:.2f}")

        # Rate limiting for Claude
        await asyncio.sleep(0.5)

    await client.aclose()
    return results


def _is_valid_json(text: str) -> bool:
    """Check if text is valid JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def _text_overlap(expected: str, generated: str) -> float:
    """Simple word overlap score (Jaccard similarity)."""
    if not expected or not generated:
        return 0.0
    words_exp = set(expected.lower().split())
    words_gen = set(generated.lower().split())
    if not words_exp:
        return 0.0
    intersection = words_exp & words_gen
    union = words_exp | words_gen
    return len(intersection) / len(union) if union else 0.0


def summarize(results: list[dict], label: str) -> dict:
    """Compute aggregate metrics."""
    if not results:
        return {"label": label, "count": 0}

    total = len(results)
    errors = sum(1 for r in results if r["is_error"])
    valid = [r for r in results if not r["is_error"]]

    summary = {
        "label": label,
        "count": total,
        "errors": errors,
        "success_rate": (total - errors) / total if total else 0,
        "avg_latency_ms": sum(r["latency_ms"] for r in valid) / len(valid) if valid else 0,
        "p95_latency_ms": sorted([r["latency_ms"] for r in valid])[int(len(valid) * 0.95)] if len(valid) > 1 else 0,
        "avg_overlap": sum(r["overlap_score"] for r in valid) / len(valid) if valid else 0,
        "json_valid_rate": sum(1 for r in valid if r["is_json"]) / len(valid) if valid else 0,
        "avg_tokens": sum(r["tokens"] for r in valid) / len(valid) if valid else 0,
    }
    return summary


def print_summary(summary: dict):
    """Pretty-print evaluation summary."""
    print(f"\n  {summary['label']}:")
    print(f"    Samples:      {summary['count']} ({summary['errors']} errors)")
    print(f"    Success rate: {summary['success_rate']:.1%}")
    print(f"    Avg latency:  {summary['avg_latency_ms']:.0f}ms (p95: {summary['p95_latency_ms']:.0f}ms)")
    print(f"    Avg overlap:  {summary['avg_overlap']:.3f}")
    print(f"    JSON valid:   {summary['json_valid_rate']:.1%}")
    print(f"    Avg tokens:   {summary['avg_tokens']:.0f}")


async def run(args):
    samples = load_val_samples(args.val_file, args.sample)

    print(f"\n{'='*60}")
    print(f"AI PILOT LLM — Evaluation")
    print(f"Samples: {len(samples)} from {args.val_file}")
    print(f"{'='*60}")

    all_summaries = {}

    # Eval local model
    if args.provider in ("local", "vllm", "ollama"):
        base_url = args.base_url
        if args.provider == "ollama":
            base_url = base_url or "http://localhost:11434"
        else:
            base_url = base_url or "http://localhost:8000"

        print(f"\n[LOCAL] Evaluating {args.model} at {base_url}...")
        local_results = await eval_local(samples, base_url, args.model)
        local_summary = summarize(local_results, f"AI PILOT LLM ({args.model})")
        print_summary(local_summary)
        all_summaries["local"] = local_summary

    # Compare with Claude
    if args.compare_claude:
        print(f"\n[CLAUDE] Evaluating claude-haiku baseline...")
        claude_results = await eval_claude(samples)
        claude_summary = summarize(claude_results, "Claude Haiku (baseline)")
        print_summary(claude_summary)
        all_summaries["claude"] = claude_summary

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"Results saved: {output_path}")

    # Comparison table
    if len(all_summaries) > 1:
        print(f"\n{'Provider':<30} {'Latency':>10} {'Overlap':>10} {'JSON':>10} {'Cost':>10}")
        print("-" * 70)
        for key, s in all_summaries.items():
            cost = "~$0" if key == "local" else "~$0.01/req"
            print(f"{s['label']:<30} {s['avg_latency_ms']:>8.0f}ms {s['avg_overlap']:>9.3f} {s['json_valid_rate']:>9.1%} {cost:>10}")

    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="AI PILOT LLM Evaluation")
    parser.add_argument("--val-file", default="datasets/val.jsonl")
    parser.add_argument("--sample", type=int, default=50, help="Number of samples to evaluate")
    parser.add_argument("--provider", default="local", choices=["local", "vllm", "ollama"])
    parser.add_argument("--base-url", default="", help="Override endpoint URL")
    parser.add_argument("--model", default="ai-pilot-llm-1.0", help="Model name for local endpoint")
    parser.add_argument("--compare-claude", action="store_true", help="Also evaluate Claude Haiku as baseline")
    parser.add_argument("--output", default="eval/results.json", help="Output file for results")
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
