#!/usr/bin/env python3
"""AI PILOT LLM — vLLM Serving Script.

Starts a vLLM OpenAI-compatible server with the fine-tuned model.

Usage:
  # Serve merged model:
  python scripts/serve.py --model checkpoints/ai-pilot-llm-v1-merged

  # Serve with LoRA adapter:
  python scripts/serve.py --model unsloth/Qwen3-8B --lora checkpoints/ai-pilot-llm-v1

  # Production (Hetzner GPU server):
  python scripts/serve.py --model checkpoints/ai-pilot-llm-v1-merged --host 0.0.0.0 --port 8000

Requirements:
  pip install vllm
"""
import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="AI PILOT LLM — vLLM Server")
    parser.add_argument("--model", required=True, help="Model path or HuggingFace ID")
    parser.add_argument("--lora", default="", help="LoRA adapter path (optional)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--max-model-len", type=int, default=4096)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    parser.add_argument("--dtype", default="auto", choices=["auto", "float16", "bfloat16"])
    parser.add_argument("--quantization", default="", choices=["", "awq", "gptq", "squeezellm"])
    parser.add_argument("--served-model-name", default="ai-pilot-llm-1.0")
    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", args.model,
        "--host", args.host,
        "--port", str(args.port),
        "--max-model-len", str(args.max_model_len),
        "--gpu-memory-utilization", str(args.gpu_memory_utilization),
        "--dtype", args.dtype,
        "--served-model-name", args.served_model_name,
        "--trust-remote-code",
    ]

    if args.lora:
        cmd.extend(["--enable-lora", "--lora-modules", f"ai-pilot-llm-1.0={args.lora}"])

    if args.quantization:
        cmd.extend(["--quantization", args.quantization])

    print(f"Starting vLLM server:")
    print(f"  Model: {args.model}")
    print(f"  LoRA:  {args.lora or 'none'}")
    print(f"  URL:   http://{args.host}:{args.port}")
    print(f"  Name:  {args.served_model_name}")
    print(f"\nTest with:")
    print(f'  curl http://localhost:{args.port}/v1/chat/completions \\')
    print(f'    -H "Content-Type: application/json" \\')
    print(f'    -d \'{{"model":"{args.served_model_name}","messages":[{{"role":"user","content":"Привет"}}]}}\'')
    print()

    subprocess.run(cmd)


if __name__ == "__main__":
    main()
