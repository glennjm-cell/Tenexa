# syntax=docker/dockerfile:1.4

########################################
# STAGE 1 — BUILD EVERYTHING
########################################
FROM wlsdml1114/multitalk-base:1.7 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Python deps
RUN pip install -U pip && \
    pip install runpod websocket-client "huggingface_hub[hf_transfer]"

WORKDIR /app

# ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /ComfyUI && \
    pip install -r /ComfyUI/requirements.txt

# Custom nodes
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Comfy-Org/ComfyUI-Manager.git && \
    pip install -r ComfyUI-Manager/requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/city96/ComfyUI-GGUF.git && \
    pip install -r ComfyUI-GGUF/requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-KJNodes.git && \
    pip install -r ComfyUI-KJNodes/requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    pip install -r ComfyUI-VideoHelperSuite/requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git && \
    pip install -r ComfyUI-WanVideoWrapper/requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/orssorbit/ComfyUI-wanBlockswap.git

# Download models and LoRA
RUN mkdir -p /ComfyUI/models/{diffusion_models,vae,text_encoders,loras,clip_vision} && \
    wget -q https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/I2V/Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors \
      -O /ComfyUI/models/diffusion_models/Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors && \
    wget -q https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/I2V/Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors \
      -O /ComfyUI/models/diffusion_models/Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors && \
    wget -q https://huggingface.co/Gjm1234/tenexa-wan22-lora/resolve/main/wan22-k3nk4llinon3-16epoc-full-high-k3nk.safetensors \
      -O /ComfyUI/models/loras/tenexa-wan22-lora.safetensors && \
    wget -q https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors \
      -O /ComfyUI/models/clip_vision/clip_vision_h.safetensors && \
    wget -q https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-bf16.safetensors \
      -O /ComfyUI/models/text_encoders/umt5-xxl-enc-bf16.safetensors && \
    wget -q https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors \
      -O /ComfyUI/models/vae/Wan2_1_VAE_bf16.safetensors

# Copy serverless code
COPY . /app
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml
RUN chmod +x /app/entrypoint.sh

########################################
# STAGE 2 — CLEAN RUNTIME
########################################
FROM wlsdml1114/multitalk-base:1.7

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY --from=builder /ComfyUI /ComfyUI
COPY --from=builder /app /app

CMD ["/app/entrypoint.sh"]
