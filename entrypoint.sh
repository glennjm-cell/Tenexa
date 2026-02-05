#!/usr/bin/env bash
set -euo pipefail

echo "================================"
echo "Tenexa RunPod Serverless Startup"
echo "================================"

# Environment
export COMFY_ROOT="${COMFY_ROOT:-/ComfyUI}"
export COMFY_LOG="${COMFY_ROOT}/comfy.log"
export SERVER_ADDRESS="${SERVER_ADDRESS:-127.0.0.1}"
export COMFY_READY_TIMEOUT="${COMFY_READY_TIMEOUT:-120}"

# Create directories
mkdir -p "${COMFY_ROOT}/models"/{diffusion_models,vae,text_encoders,loras,clip_vision}
mkdir -p "${COMFY_ROOT}"/{input,output}

# Download helper function
dl () {
  url="$1"
  out="$2"
  if [ ! -f "$out" ]; then
    echo "📥 Downloading: $(basename "$out")"
    wget -q --show-progress "$url" -O "$out" || {
      echo "❌ Failed to download $url"
      return 1
    }
  else
    echo "✅ Exists: $(basename "$out")"
  fi
}

# Download required models
echo "🔧 Checking models..."

dl "https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/I2V/Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors" \
   "${COMFY_ROOT}/models/diffusion_models/Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors"

dl "https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/I2V/Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors" \
   "${COMFY_ROOT}/models/diffusion_models/Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"

dl "https://huggingface.co/Gjm1234/tenexa-wan22-lora/resolve/main/wan22-k3nk4llinon3-16epoc-full-high-k3nk.safetensors" \
   "${COMFY_ROOT}/models/loras/tenexa-wan22-lora.safetensors"

dl "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors" \
   "${COMFY_ROOT}/models/clip_vision/clip_vision_h.safetensors"

dl "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-bf16.safetensors" \
   "${COMFY_ROOT}/models/text_encoders/umt5-xxl-enc-bf16.safetensors"

dl "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors" \
   "${COMFY_ROOT}/models/vae/Wan2_1_VAE_bf16.safetensors"

echo "✅ Models ready"

# Start ComfyUI in background
echo "🚀 Starting ComfyUI..."
cd "${COMFY_ROOT}"

# Start ComfyUI and redirect logs
nohup python3 main.py --listen 0.0.0.0 --port 8188 > "${COMFY_LOG}" 2>&1 &
COMFY_PID=$!

echo "📝 ComfyUI PID: ${COMFY_PID}"
echo "📋 Logs: ${COMFY_LOG}"

# Wait for ComfyUI to be ready
echo "⏳ Waiting for ComfyUI (max ${COMFY_READY_TIMEOUT}s)..."

start_time=$(date +%s)
ready=false

while true; do
  current_time=$(date +%s)
  elapsed=$((current_time - start_time))
  
  if [ $elapsed -gt $COMFY_READY_TIMEOUT ]; then
    echo "❌ ComfyUI failed to start within ${COMFY_READY_TIMEOUT}s"
    echo "📋 Last 50 lines of ComfyUI log:"
    tail -n 50 "${COMFY_LOG}"
    exit 1
  fi
  
  # Check if ComfyUI is responding
  if curl -sf "http://${SERVER_ADDRESS}:8188/system_stats" > /dev/null 2>&1; then
    echo "✅ ComfyUI is ready (after ${elapsed}s)"
    ready=true
    break
  fi
  
  # Check if process is still running
  if ! kill -0 $COMFY_PID 2>/dev/null; then
    echo "❌ ComfyUI process died unexpectedly"
    echo "📋 Last 50 lines of ComfyUI log:"
    tail -n 50 "${COMFY_LOG}"
    exit 1
  fi
  
  sleep 1
done

# Show startup summary
echo ""
echo "================================"
echo "✅ ComfyUI Started Successfully"
echo "================================"
echo "🌐 Server: http://${SERVER_ADDRESS}:8188"
echo "📝 Logs: ${COMFY_LOG}"
echo "📁 Input: ${COMFY_ROOT}/input"
echo "📁 Output: ${COMFY_ROOT}/output"
echo ""

# Start RunPod handler
echo "🎬 Starting RunPod handler..."
cd /app
exec python3 handler.py
