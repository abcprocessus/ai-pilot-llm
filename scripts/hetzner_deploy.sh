#!/bin/bash
# AI PILOT LLM — Hetzner GPU Server Deployment
#
# Production serving on Hetzner dedicated GPU server.
#
# Recommended server: Hetzner EX44 + GPU (RTX 4000 Ada)
#   or: Hetzner Cloud with GPU (GEX44, A100)
#   Cost: ~€150-200/month
#
# Prerequisites:
#   - Ubuntu 22.04+ with NVIDIA drivers
#   - Docker installed
#   - Model files uploaded to /models/ai-pilot-llm/
#
# Usage (on the Hetzner server):
#   bash hetzner_deploy.sh [vllm|ollama]

set -e

MODE=${1:-vllm}
MODEL_DIR="/models/ai-pilot-llm"
PORT=8000

echo "============================================"
echo "AI PILOT LLM — Production Deploy ($MODE)"
echo "============================================"

# Check NVIDIA
if ! nvidia-smi > /dev/null 2>&1; then
    echo "ERROR: NVIDIA drivers not found"
    echo "Install: apt install nvidia-driver-550"
    exit 1
fi

echo "GPU detected:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

if [ "$MODE" = "vllm" ]; then
    # ── vLLM Docker ──────────────────────────────────────────
    echo ""
    echo "Deploying vLLM (OpenAI-compatible API)..."

    docker pull vllm/vllm-openai:latest

    # Stop existing container
    docker stop ai-pilot-llm 2>/dev/null || true
    docker rm ai-pilot-llm 2>/dev/null || true

    docker run -d \
        --name ai-pilot-llm \
        --runtime nvidia \
        --gpus all \
        -p ${PORT}:8000 \
        -v ${MODEL_DIR}:/model \
        --restart unless-stopped \
        vllm/vllm-openai:latest \
        --model /model \
        --served-model-name ai-pilot-llm-1.0 \
        --max-model-len 4096 \
        --gpu-memory-utilization 0.90 \
        --dtype auto \
        --trust-remote-code

    echo "vLLM container started on port $PORT"

elif [ "$MODE" = "ollama" ]; then
    # ── Ollama ───────────────────────────────────────────────
    echo ""
    echo "Deploying via Ollama..."

    # Install Ollama if not present
    if ! command -v ollama &> /dev/null; then
        curl -fsSL https://ollama.com/install.sh | sh
    fi

    # Find GGUF file
    GGUF_FILE=$(find ${MODEL_DIR} -name "*.gguf" -type f | head -1)
    if [ -z "$GGUF_FILE" ]; then
        echo "ERROR: No .gguf file in $MODEL_DIR"
        exit 1
    fi

    # Create Modelfile
    cat > /tmp/Modelfile << EOF
FROM $GGUF_FILE

PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|endoftext|>"

SYSTEM """Ты AI PILOT — универсальный AI-ассистент для бизнеса.
Специализации: бухгалтерия BY/RU, юриспруденция, продажи, HR, маркетинг, реклама, код.
Отвечай точно, структурированно."""
EOF

    ollama create ai-pilot-llm -f /tmp/Modelfile

    # Start Ollama with GPU
    OLLAMA_HOST=0.0.0.0:${PORT} ollama serve &

    echo "Ollama started on port $PORT"
fi

# Wait for startup
echo ""
echo "Waiting for model to load..."
for i in $(seq 1 120); do
    if [ "$MODE" = "vllm" ]; then
        if curl -s http://localhost:${PORT}/health > /dev/null 2>&1; then
            break
        fi
    else
        if curl -s http://localhost:${PORT}/api/tags > /dev/null 2>&1; then
            break
        fi
    fi
    sleep 2
    echo -n "."
done
echo ""

# Test
echo ""
echo "Testing inference..."
RESPONSE=$(curl -s http://localhost:${PORT}/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "ai-pilot-llm-1.0",
        "messages": [
            {"role": "system", "content": "Ты AI PILOT бухгалтер."},
            {"role": "user", "content": "Как отразить поступление товаров?"}
        ],
        "max_tokens": 200
    }' 2>/dev/null)

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"

echo ""
echo "============================================"
echo "DEPLOYED!"
echo ""
echo "Endpoint: http://$(hostname -I | awk '{print $1}'):${PORT}"
echo ""
echo "Set in Railway FastAPI env vars:"
echo "  LOCAL_LLM_URL=http://$(hostname -I | awk '{print $1}'):${PORT}"
echo ""
echo "Systemd service (optional):"
echo "  sudo cp ai-pilot-llm.service /etc/systemd/system/"
echo "  sudo systemctl enable ai-pilot-llm"
echo "  sudo systemctl start ai-pilot-llm"
echo "============================================"
