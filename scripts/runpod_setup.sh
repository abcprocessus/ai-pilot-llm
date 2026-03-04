#!/bin/bash
# AI PILOT LLM — RunPod Training Setup
#
# 1. Create RunPod account: https://www.runpod.io
# 2. Deploy GPU Pod: A100 40GB ($1.64/hr) or A100 80GB ($2.49/hr)
#    Template: RunPod Pytorch 2.4.1 (CUDA 12.4)
# 3. SSH into pod and run this script
#
# Total cost estimate: ~$5-10 (2-4 hours training + setup)
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/abcprocessus/ai-pilot-llm/main/scripts/runpod_setup.sh | bash

set -e

echo "============================================"
echo "AI PILOT LLM — RunPod Training Setup"
echo "============================================"

# 1. Clone repo
echo "[1/6] Cloning repository..."
cd /workspace
if [ -d "ai-pilot-llm" ]; then
    cd ai-pilot-llm && git pull
else
    git clone https://github.com/abcprocessus/ai-pilot-llm.git
    cd ai-pilot-llm
fi

# 2. Install dependencies
echo "[2/6] Installing training dependencies..."
pip install -q "unsloth[cu124-torch250] @ git+https://github.com/unslothai/unsloth.git"
pip install -q transformers datasets trl peft bitsandbytes
pip install -q httpx  # for dataset pipeline

# 3. Generate dataset (if not present)
echo "[3/6] Generating dataset..."
if [ ! -f "datasets/train.jsonl" ]; then
    # Without Supabase — constitutions + synthetic only
    # To include Supabase data, set SUPABASE_URL and SUPABASE_SERVICE_KEY
    python scripts/prepare_dataset.py \
        --constitutions-dir docs/ \
        2>&1 || echo "Dataset generation failed, checking if files exist..."
fi

if [ ! -f "datasets/train.jsonl" ]; then
    echo "ERROR: datasets/train.jsonl not found. Upload manually or set SUPABASE_SERVICE_KEY"
    exit 1
fi

TRAIN_LINES=$(wc -l < datasets/train.jsonl)
VAL_LINES=$(wc -l < datasets/val.jsonl)
echo "  Dataset: $TRAIN_LINES train, $VAL_LINES val"

# 4. Run fine-tuning
echo "[4/6] Starting fine-tuning..."
echo "  Base model: Qwen3-8B (4-bit)"
echo "  Method: QLoRA (r=16, alpha=16)"
echo "  Epochs: 3"

python scripts/finetune.py \
    --base-model unsloth/Qwen3-8B-unsloth-bnb-4bit \
    --epochs 3 \
    --batch-size 2 \
    --grad-accum 4 \
    --lr 2e-4 \
    --max-seq-len 2048 \
    --merge \
    --gguf

# 5. Evaluate
echo "[5/6] Evaluating model..."
# Start vLLM in background for eval
python -m vllm.entrypoints.openai.api_server \
    --model checkpoints/ai-pilot-llm-v1-merged \
    --port 8000 \
    --max-model-len 4096 \
    --served-model-name ai-pilot-llm-1.0 &
VLLM_PID=$!

# Wait for server to start
echo "  Waiting for vLLM to start..."
for i in $(seq 1 60); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

python scripts/evaluate.py \
    --provider local \
    --base-url http://localhost:8000 \
    --sample 50

kill $VLLM_PID 2>/dev/null || true

# 6. Summary
echo "[6/6] Done!"
echo ""
echo "============================================"
echo "RESULTS:"
echo "============================================"
echo ""
echo "Files:"
echo "  LoRA adapter:  checkpoints/ai-pilot-llm-v1/"
echo "  Merged model:  checkpoints/ai-pilot-llm-v1-merged/"
echo "  GGUF (Ollama): checkpoints/ai-pilot-llm-v1-gguf/"
echo "  Eval results:  eval/results.json"
echo "  Train metrics: checkpoints/ai-pilot-llm-v1/training_metrics.json"
echo ""
cat checkpoints/ai-pilot-llm-v1/training_metrics.json 2>/dev/null
echo ""
echo "Next steps:"
echo "  1. Download merged model to Hetzner GPU server"
echo "  2. Or: download GGUF and use with Ollama"
echo "  3. Set LOCAL_LLM_URL in Railway env"
echo ""
echo "Download merged model:"
echo "  rsync -avP /workspace/ai-pilot-llm/checkpoints/ai-pilot-llm-v1-merged/ user@hetzner:/models/ai-pilot-llm/"
echo ""
echo "Download GGUF:"
echo "  scp /workspace/ai-pilot-llm/checkpoints/ai-pilot-llm-v1-gguf/*.gguf user@hetzner:/models/"
echo "============================================"
