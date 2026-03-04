#!/bin/bash
# AI PILOT LLM — Import GGUF model into Ollama
#
# Usage:
#   bash scripts/ollama_import.sh
#
# Prerequisites:
#   - Ollama installed (https://ollama.com)
#   - GGUF file at checkpoints/ai-pilot-llm-v1-gguf/
#
# After import:
#   ollama run ai-pilot-llm
#   Set LOCAL_LLM_URL=http://localhost:11434 in Railway env

set -e

GGUF_DIR="checkpoints/ai-pilot-llm-v1-gguf"
MODEL_NAME="ai-pilot-llm"

# Find GGUF file
GGUF_FILE=$(find "$GGUF_DIR" -name "*.gguf" -type f | head -1)

if [ -z "$GGUF_FILE" ]; then
    echo "ERROR: No .gguf file found in $GGUF_DIR"
    echo "Run: python scripts/finetune.py --gguf"
    exit 1
fi

echo "Found GGUF: $GGUF_FILE"

# Create Modelfile
MODELFILE="$GGUF_DIR/Modelfile"
cat > "$MODELFILE" << 'MODELFILE_EOF'
FROM {{GGUF_FILE}}

PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|endoftext|>"

SYSTEM """Ты AI PILOT — универсальный AI-ассистент для бизнеса.
Специализации: бухгалтерия BY/RU, юриспруденция, продажи, HR, маркетинг, реклама, код.
Отвечай точно, структурированно. Для бухгалтерских и юридических вопросов — JSON с проводками/рисками."""
MODELFILE_EOF

# Replace placeholder with actual path
sed -i "s|{{GGUF_FILE}}|$GGUF_FILE|g" "$MODELFILE"

echo "Creating Ollama model: $MODEL_NAME"
ollama create "$MODEL_NAME" -f "$MODELFILE"

echo ""
echo "Done! Test with:"
echo "  ollama run $MODEL_NAME"
echo ""
echo "For API access:"
echo "  curl http://localhost:11434/v1/chat/completions \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"model\":\"$MODEL_NAME\",\"messages\":[{\"role\":\"user\",\"content\":\"Как отразить поступление товаров?\"}]}'"
echo ""
echo "Set in Railway: LOCAL_LLM_URL=http://your-server:11434"
