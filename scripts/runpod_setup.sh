#!/bin/bash
# AI PILOT LLM — RunPod Training Setup (v2)
#
# Prerequisites:
#   1. RunPod account: https://www.runpod.io
#   2. Deploy GPU Pod: A100 40GB ($1.64/hr) — PyTorch 2.5 + CUDA 12.4 template
#   3. Upload dataset to pod (see step 3 below)
#
# Usage on RunPod (after uploading dataset):
#   cd /workspace/ai-pilot-llm && bash scripts/runpod_setup.sh
#
# Or one-liner after git clone:
#   git clone https://github.com/abcprocessus/ai-pilot-llm.git /workspace/ai-pilot-llm
#   cd /workspace/ai-pilot-llm && bash scripts/runpod_setup.sh
#
# Total cost estimate: ~$3-5 (1.5-2.5 hours on A100 40GB)

set -e

echo "============================================================"
echo "  AI PILOT LLM — Fine-Tune Pipeline v2"
echo "  Dataset: 14,390 pairs (12,951 train / 1,439 val)"
echo "  Model:   Qwen3-8B QLoRA → ai-pilot-llm-1.0"
echo "============================================================"
echo ""

# 1. Check GPU
echo "[1/7] Checking GPU..."
if ! nvidia-smi > /dev/null 2>&1; then
    echo "ERROR: No GPU found. Deploy a GPU-enabled pod (A100 recommended)."
    exit 1
fi
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1)
echo "  GPU: $GPU_NAME ($GPU_MEM)"
echo ""

# 2. Install dependencies
echo "[2/7] Installing training dependencies..."
pip install --no-cache-dir -q \
    "unsloth[cu124-torch251]" \
    "transformers>=4.46.0" \
    "datasets>=3.0" \
    "trl>=0.12.0" \
    "peft>=0.13.0" \
    "bitsandbytes>=0.44.0" \
    "accelerate>=1.0.0" \
    sentencepiece \
    protobuf \
    vllm
echo "  Done."
echo ""

# 3. Check dataset
echo "[3/7] Checking dataset..."
if [ ! -f "datasets/train.jsonl" ] || [ ! -f "datasets/val.jsonl" ]; then
    echo "ERROR: Dataset files not found!"
    echo ""
    echo "Upload from your local machine:"
    echo "  Option A — runpodctl (fastest):"
    echo "    # Local: runpodctl send datasets/train.jsonl"
    echo "    # Pod:   runpodctl receive <CODE>"
    echo ""
    echo "  Option B — scp:"
    echo "    scp datasets/train.jsonl datasets/val.jsonl root@<POD_IP>:/workspace/ai-pilot-llm/datasets/"
    echo ""
    echo "  Option C — curl from GitHub release (if uploaded):"
    echo "    mkdir -p datasets"
    echo "    curl -L -o datasets/train.jsonl <URL>"
    echo "    curl -L -o datasets/val.jsonl <URL>"
    exit 1
fi

TRAIN_COUNT=$(wc -l < datasets/train.jsonl)
VAL_COUNT=$(wc -l < datasets/val.jsonl)
echo "  train.jsonl: $TRAIN_COUNT pairs"
echo "  val.jsonl:   $VAL_COUNT pairs"
echo ""

# 4. Run fine-tuning
echo "[4/7] Starting QLoRA fine-tune..."
echo "  Base:   unsloth/Qwen3-8B-unsloth-bnb-4bit"
echo "  LoRA:   r=16, alpha=16"
echo "  LR:     2e-4 (cosine)"
echo "  Epochs: 3"
echo "  Batch:  2 x 4 = 8 effective"
echo "  Seq:    2048 tokens"
echo ""

mkdir -p checkpoints

python scripts/finetune.py \
    --base-model "unsloth/Qwen3-8B-unsloth-bnb-4bit" \
    --train-file "datasets/train.jsonl" \
    --val-file "datasets/val.jsonl" \
    --output-dir "checkpoints/ai-pilot-llm-v1" \
    --epochs 3 \
    --batch-size 2 \
    --grad-accum 4 \
    --lr 2e-4 \
    --max-seq-len 2048 \
    --merge \
    --gguf

echo ""
echo "  Training complete. Metrics:"
cat checkpoints/ai-pilot-llm-v1/training_metrics.json 2>/dev/null || echo "  (metrics file not found)"
echo ""

# 5. Quick smoke test with vLLM
echo "[5/7] Starting vLLM for smoke test..."
python -m vllm.entrypoints.openai.api_server \
    --model "checkpoints/ai-pilot-llm-v1-merged" \
    --served-model-name "ai-pilot-llm-1.0" \
    --host 0.0.0.0 \
    --port 8000 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 4096 &
VLLM_PID=$!

echo "  Waiting for vLLM (up to 2 min)..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "  vLLM ready!"
        break
    fi
    sleep 2
done

# 6. Evaluate
echo ""
echo "[6/7] Running evaluation..."
if [ -f "scripts/evaluate.py" ]; then
    python scripts/evaluate.py \
        --provider local \
        --base-url http://localhost:8000 \
        --sample 50 2>&1 || echo "  Evaluation script failed (non-critical)"
else
    # Quick manual test
    echo "  Quick test (3 prompts)..."
    for prompt in "Привет! Расскажи о себе." "Как подключить CRM к AI агенту?" "Объясни разницу между тарифами Lite и Business."; do
        echo ""
        echo "  Q: $prompt"
        RESPONSE=$(curl -sf http://localhost:8000/v1/chat/completions \
            -H "Content-Type: application/json" \
            -d "{\"model\":\"ai-pilot-llm-1.0\",\"messages\":[{\"role\":\"system\",\"content\":\"Ты AI PILOT — платформа AI сотрудников для бизнеса.\"},{\"role\":\"user\",\"content\":\"$prompt\"}],\"max_tokens\":512,\"temperature\":0.7}" 2>/dev/null \
            | python -c "import sys,json; print(json.load(sys.stdin)['choices'][0]['message']['content'][:200])" 2>/dev/null \
            || echo "  (request failed)")
        echo "  A: $RESPONSE"
    done
fi

kill $VLLM_PID 2>/dev/null || true
wait $VLLM_PID 2>/dev/null || true

# 7. Summary
echo ""
echo "============================================================"
echo "  TRAINING COMPLETE — AI PILOT LLM v1.0"
echo "============================================================"
echo ""
echo "  Outputs:"
echo "    LoRA adapter:  checkpoints/ai-pilot-llm-v1/"
echo "    Merged model:  checkpoints/ai-pilot-llm-v1-merged/"
echo "    GGUF (Ollama): checkpoints/ai-pilot-llm-v1-gguf/"
echo ""
echo "  Download to your server:"
echo "    # Option A: runpodctl (fastest)"
echo "    runpodctl send checkpoints/ai-pilot-llm-v1-merged/"
echo ""
echo "    # Option B: rsync"
echo "    rsync -avP checkpoints/ai-pilot-llm-v1-merged/ user@server:/models/ai-pilot-llm-v1/"
echo ""
echo "  Deploy with vLLM (on GPU server):"
echo "    docker run --gpus all -p 8000:8000 \\"
echo "      -v /models/ai-pilot-llm-v1:/model \\"
echo "      vllm/vllm-openai \\"
echo "      --model /model --served-model-name ai-pilot-llm-1.0 --port 8000"
echo ""
echo "  Connect to FastAPI:"
echo "    railway variables set LOCAL_LLM_URL=http://gpu-server:8000"
echo ""
echo "============================================================"
