#!/usr/bin/env bash
set -euo pipefail

mkdir -p /ComfyUI/models/{diffusion_models,vae,text_encoders,loras,clip_vision}

dl () {
  url="$1"
  out="$2"
  if [ ! -f "$out" ]; then
    echo "Downloading: $out"
    wget -q --show-progress "$url" -O "$out"
  else
    echo "Exists: $out"
  fi
}

dl "https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/I2V/Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors" \
   "/ComfyUI/models/diffusion_models/Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors"

dl "https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/I2V/Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors" \
   "/ComfyUI/models/diffusion_models/Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"

dl "https://huggingface.co/Gjm1234/tenexa-wan22-lora/resolve/main/wan22-k3nk4llinon3-16epoc-full-high-k3nk.safetensors" \
   "/ComfyUI/models/loras/tenexa-wan22-lora.safetensors"

dl "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors" \
   "/ComfyUI/models/clip_vision/clip_vision_h.safetensors"

dl "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-bf16.safetensors" \
   "/ComfyUI/models/text_encoders/umt5-xxl-enc-bf16.safetensors"

dl "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors" \
   "/ComfyUI/models/vae/Wan2_1_VAE_bf16.safetensors"

# then start ComfyUI + RunPod worker like you already do
