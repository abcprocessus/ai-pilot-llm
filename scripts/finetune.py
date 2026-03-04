#!/usr/bin/env python3
"""AI PILOT LLM — Fine-tune script (QLoRA on Unsloth).

Trains a LoRA adapter on top of a base model using our dataset.

Usage:
  # Local GPU (RTX 3090/4090, 24GB VRAM):
  python scripts/finetune.py

  # RunPod / Vast.ai (A100 40GB):
  python scripts/finetune.py --base-model unsloth/Qwen3-8B-unsloth-bnb-4bit --epochs 3

  # Llama 4 Scout:
  python scripts/finetune.py --base-model unsloth/Llama-4-Scout-17B-16E-Instruct-unsloth-bnb-4bit --epochs 2

Requirements (install in training environment):
  pip install unsloth transformers datasets trl peft bitsandbytes

Outputs:
  checkpoints/ai-pilot-llm-v1/     — LoRA adapter weights
  checkpoints/ai-pilot-llm-v1-merged/  — Full merged model (for vLLM)
  checkpoints/ai-pilot-llm-v1-gguf/    — GGUF file (for Ollama)
"""
import argparse
import json
import os
import sys
from pathlib import Path


def check_dependencies():
    """Verify all required packages are installed."""
    missing = []
    for pkg in ["unsloth", "transformers", "datasets", "trl", "peft"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"ERROR: Missing packages: {', '.join(missing)}")
        print("Install with: pip install unsloth transformers datasets trl peft bitsandbytes")
        sys.exit(1)


def load_dataset(train_path: str, val_path: str):
    """Load JSONL dataset files."""
    from datasets import Dataset

    def read_jsonl(path):
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                rows.append(obj)
        return rows

    train_rows = read_jsonl(train_path)
    val_rows = read_jsonl(val_path)

    print(f"Dataset: {len(train_rows)} train, {len(val_rows)} val")

    return Dataset.from_list(train_rows), Dataset.from_list(val_rows)


def format_for_chat(example, tokenizer):
    """Format messages into chat template string."""
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}


def main():
    parser = argparse.ArgumentParser(description="AI PILOT LLM Fine-Tune (QLoRA)")
    parser.add_argument(
        "--base-model",
        default="unsloth/Qwen3-8B-unsloth-bnb-4bit",
        help="Base model (Unsloth 4-bit quantized)",
    )
    parser.add_argument("--train-file", default="datasets/train.jsonl")
    parser.add_argument("--val-file", default="datasets/val.jsonl")
    parser.add_argument("--output-dir", default="checkpoints/ai-pilot-llm-v1")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=4, help="Gradient accumulation steps")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--max-seq-len", type=int, default=2048)
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=16, help="LoRA alpha")
    parser.add_argument("--lora-dropout", type=float, default=0.0)
    parser.add_argument("--merge", action="store_true", help="Merge LoRA into base model after training")
    parser.add_argument("--gguf", action="store_true", help="Export GGUF for Ollama after training")
    parser.add_argument("--push-to-hub", default="", help="HuggingFace repo to push (e.g. abcprocessus/ai-pilot-llm-v1)")
    args = parser.parse_args()

    check_dependencies()

    from unsloth import FastLanguageModel
    from trl import SFTTrainer, SFTConfig

    # 1. Load base model with QLoRA
    print(f"\n{'='*60}")
    print(f"AI PILOT LLM — Fine-Tune")
    print(f"Base model: {args.base_model}")
    print(f"{'='*60}\n")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_len,
        load_in_4bit=True,
    )

    # 2. Add LoRA adapters
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Parameters: {trainable:,} trainable / {total:,} total ({trainable/total*100:.2f}%)")

    # 3. Load dataset
    train_ds, val_ds = load_dataset(args.train_file, args.val_file)
    train_ds = train_ds.map(lambda x: format_for_chat(x, tokenizer))
    val_ds = val_ds.map(lambda x: format_for_chat(x, tokenizer))

    # 4. Training config
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    effective_batch = args.batch_size * args.grad_accum
    steps_per_epoch = len(train_ds) // effective_batch
    total_steps = steps_per_epoch * args.epochs
    eval_steps = max(steps_per_epoch // 2, 1)
    save_steps = steps_per_epoch

    print(f"\nTraining config:")
    print(f"  Epochs: {args.epochs}")
    print(f"  Batch size: {args.batch_size} x {args.grad_accum} grad_accum = {effective_batch} effective")
    print(f"  Steps/epoch: {steps_per_epoch}, total: {total_steps}")
    print(f"  LR: {args.lr}, Max seq len: {args.max_seq_len}")
    print(f"  LoRA: r={args.lora_r}, alpha={args.lora_alpha}")
    print(f"  Output: {output_dir}\n")

    training_args = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        weight_decay=0.01,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=eval_steps,
        save_strategy="steps",
        save_steps=save_steps,
        save_total_limit=3,
        bf16=True,
        max_seq_length=args.max_seq_len,
        dataset_text_field="text",
        seed=42,
        report_to="none",
    )

    # 5. Train
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        args=training_args,
    )

    print("Starting training...")
    train_result = trainer.train()

    # 6. Save LoRA adapter
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    # Save training metrics
    metrics = {
        "train_loss": train_result.training_loss,
        "train_runtime_sec": train_result.metrics.get("train_runtime", 0),
        "train_samples": len(train_ds),
        "val_samples": len(val_ds),
        "base_model": args.base_model,
        "epochs": args.epochs,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "lr": args.lr,
        "max_seq_len": args.max_seq_len,
    }
    with open(output_dir / "training_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\nTraining complete!")
    print(f"  Loss: {train_result.training_loss:.4f}")
    print(f"  Runtime: {train_result.metrics.get('train_runtime', 0):.0f}s")
    print(f"  LoRA adapter saved: {output_dir}")

    # 7. Merge (optional)
    if args.merge:
        merge_dir = Path(str(output_dir) + "-merged")
        print(f"\nMerging LoRA into base model -> {merge_dir}")
        model.save_pretrained_merged(
            str(merge_dir),
            tokenizer,
            save_method="merged_16bit",
        )
        print(f"  Merged model saved: {merge_dir}")

    # 8. GGUF export (optional, for Ollama)
    if args.gguf:
        gguf_dir = Path(str(output_dir) + "-gguf")
        print(f"\nExporting GGUF (Q4_K_M) -> {gguf_dir}")
        model.save_pretrained_gguf(
            str(gguf_dir),
            tokenizer,
            quantization_method="q4_k_m",
        )
        print(f"  GGUF saved: {gguf_dir}")

    # 9. Push to HuggingFace (optional)
    if args.push_to_hub:
        print(f"\nPushing to HuggingFace: {args.push_to_hub}")
        model.push_to_hub_merged(
            args.push_to_hub,
            tokenizer,
            save_method="lora",
            token=os.environ.get("HF_TOKEN"),
        )
        print(f"  Pushed: https://huggingface.co/{args.push_to_hub}")

    print(f"\n{'='*60}")
    print("DONE. Next steps:")
    print("  1. Test: python scripts/evaluate.py")
    print("  2. Serve: python scripts/serve.py (vLLM) or scripts/ollama_import.sh (Ollama)")
    print("  3. Set LOCAL_LLM_URL=http://gpu-server:8000 in Railway env")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
