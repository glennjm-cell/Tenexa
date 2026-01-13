#!/bin/bash
set -e

echo "Starting ComfyUI..."
python /ComfyUI/main.py --listen --use-sage-attention &

echo "Waiting for ComfyUI to accept connections..."
for i in {1..120}; do
  if curl -s http://127.0.0.1:8188/ >/dev/null 2>&1; then
    echo "ComfyUI is responding."
    break
  fi
  sleep 2
done

echo "Launching RunPod handler..."
exec python /app/handler.py
