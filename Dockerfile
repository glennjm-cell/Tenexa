# syntax=docker/dockerfile:1.4
ARG BUILDKIT_INLINE_CACHE=0

########################################
# STAGE 1 — BUILD EVERYTHING (NO MODELS)
########################################
FROM wlsdml1114/multitalk-base:1.7 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV HF_HUB_DISABLE_TELEMETRY=1

# Install system dependencies including ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install -U pip && \
    pip install --no-cache-dir \
    runpod \
    websocket-client \
    "huggingface_hub[hf_transfer]" \
    requests \
    pyyaml \
    pillow

WORKDIR /app

# Clone and setup ComfyUI
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /ComfyUI && \
    pip install --no-cache-dir -r /ComfyUI/requirements.txt

# Install custom nodes
RUN set -eux; \
    cd /ComfyUI/custom_nodes; \
    git clone --depth 1 https://github.com/Comfy-Org/ComfyUI-Manager.git; \
    pip install --no-cache-dir -r ComfyUI-Manager/requirements.txt || true; \
    git clone --depth 1 https://github.com/city96/ComfyUI-GGUF.git; \
    pip install --no-cache-dir -r ComfyUI-GGUF/requirements.txt || true; \
    git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes.git; \
    pip install --no-cache-dir -r ComfyUI-KJNodes/requirements.txt || true; \
    git clone --depth 1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git; \
    pip install --no-cache-dir -r ComfyUI-VideoHelperSuite/requirements.txt || true; \
    git clone --depth 1 https://github.com/kijai/ComfyUI-WanVideoWrapper.git; \
    pip install --no-cache-dir -r ComfyUI-WanVideoWrapper/requirements.txt || true; \
    git clone --depth 1 https://github.com/orssorbit/ComfyUI-wanBlockswap.git

# Cleanup git + caches
RUN find /ComfyUI -name ".git" -type d -prune -exec rm -rf {} +; \
    rm -rf /root/.cache/pip /root/.cache/huggingface /tmp/*

# Copy application files
COPY handler.py /app/handler.py
COPY entrypoint.sh /app/entrypoint.sh
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml
COPY new_Wan22_api.json /app/new_Wan22_api.json
COPY new_Wan22_flf2v_api.json /app/new_Wan22_flf2v_api.json

RUN chmod +x /app/entrypoint.sh

########################################
# STAGE 2 — RUNTIME
########################################
FROM wlsdml1114/multitalk-base:1.7

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV COMFY_ROOT=/ComfyUI
ENV SERVER_ADDRESS=127.0.0.1
ENV HANDLER_VERSION=2026-02-05-v1

WORKDIR /app

# Copy from builder
COPY --from=builder /ComfyUI /ComfyUI
COPY --from=builder /app /app
COPY --from=builder /usr/local/lib/python3.*/dist-packages /usr/local/lib/python3.10/dist-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

CMD ["/app/entrypoint.sh"]
