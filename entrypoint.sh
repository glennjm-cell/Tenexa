#!/bin/bash
set -e

echo "====================================="
echo " Starting ComfyUI..."
echo "====================================="

python3 /ComfyUI/main.py --listen 0.0.0.0 --port 8188 &

COMFY_PID=$!

echo "Waiting for ComfyUI to be ready..."

for i in {1..60}; do
  if curl -s http://127.0.0.1:8188/ > /dev/null; then
    echo "ComfyUI is ready."
    break
  fi
  sleep 1
done

echo "====================================="
echo " Starting RunPod Handler..."
echo "====================================="

python3 /app/handler.py

wait $COMFY_PID
