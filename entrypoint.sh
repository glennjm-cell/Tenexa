#!/bin/bash
set -e

echo "====================================="
echo "🚀 Starting ComfyUI..."
echo "====================================="

cd /ComfyUI
python3 main.py --listen 0.0.0.0 --port 8188 &

COMFY_PID=$!

echo "⏳ Waiting for ComfyUI to be ready..."

for i in {1..180}; do
  if curl -s http://127.0.0.1:8188/ > /dev/null; then
    echo "✅ ComfyUI is ready."
    break
  fi
  echo "Waiting... $i"
  sleep 1
done

echo "====================================="
echo "🚀 Starting RunPod Handler..."
echo "====================================="

cd /app
python3 handler.py

wait $COMFY_PID
