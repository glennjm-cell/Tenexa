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

RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install -U pip && \
    pip install --no-cache-dir runpod websocket-client "huggingface_hub[hf_transfer]"

WORKDIR /app

RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /ComfyUI && \
    pip install --no-cache-dir -r /ComfyUI/requirements.txt

RUN set -eux; \
    cd /ComfyUI/custom_nodes; \
    git clone --depth 1 https://github.com/Comfy-Org/ComfyUI-Manager.git; \
    pip install --no-cache-dir -r ComfyUI-Manager/requirements.txt; \
    git clone --depth 1 https://github.com/city96/ComfyUI-GGUF.git; \
    pip install --no-cache-dir -r ComfyUI-GGUF/requirements.txt; \
    git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes.git; \
    pip install --no-cache-dir -r ComfyUI-KJNodes/requirements.txt; \
    git clone --depth 1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git; \
    pip install --no-cache-dir -r ComfyUI-VideoHelperSuite/requirements.txt; \
    git clone --depth 1 https://github.com/kijai/ComfyUI-WanVideoWrapper.git; \
    pip install --no-cache-dir -r ComfyUI-WanVideoWrapper/requirements.txt; \
    git clone --depth 1 https://github.com/orssorbit/ComfyUI-wanBlockswap.git

# cleanup git + caches (still good)
RUN find /ComfyUI -name ".git" -type d -prune -exec rm -rf {} +; \
    rm -rf /root/.cache/pip /root/.cache/huggingface /tmp/*

COPY . /app
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml
RUN chmod +x /app/entrypoint.sh

########################################
# STAGE 2 — RUNTIME
########################################
FROM wlsdml1114/multitalk-base:1.7

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY --from=builder /ComfyUI /ComfyUI
COPY --from=builder /app /app

CMD ["/app/entrypoint.sh"]
