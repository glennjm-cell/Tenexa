# Tenexa - Wan 2.2 Image-to-Video RunPod Serverless

Production-ready RunPod serverless endpoint for generating AI videos from images using the Wan 2.2 model with ComfyUI.

## Features

- ✅ **Robust startup** - ComfyUI readiness checks with timeout handling
- ✅ **Three operation modes** - test, diagnose, and generate
- ✅ **Full diagnostics** - Model validation, node checking, error reporting
- ✅ **Workflow support** - Standard I2V and First-Last-Frame (FLF2V) modes
- ✅ **Volume integration** - RunPod volume support for models and LoRAs
- ✅ **Error handling** - Comprehensive error codes and log tailing
- ✅ **Video output** - MP4 files returned as base64 with metadata

## Quick Start

### 1. Build and Push Docker Image

```bash
docker build -t your-username/tenexa-wan22:latest .
docker push your-username/tenexa-wan22:latest
```

### 2. Create RunPod Endpoint

1. Go to [RunPod Serverless](https://www.runpod.io/console/serverless)
2. Create new endpoint
3. Docker image: `your-username/tenexa-wan22:latest`
4. GPU: 48GB+ VRAM (A6000, A100, L40S recommended)
5. Worker configuration: Set idle timeout, max workers, etc.

### 3. Optional: Mount Volume for Custom Models

If you want to use custom models or LoRAs:

1. Create a network volume in RunPod
2. Mount it at `/runpod-volume`
3. Organize files as:
   ```
   /runpod-volume/
   ├── models/          # Diffusion models
   ├── loras/           # LoRA files
   └── clip/            # CLIP models
   ```

## API Usage

### Mode 1: Test / Health Check

Quick health check that verifies ComfyUI is running (< 1 second response).

**Request:**
```json
{
  "input": {
    "test": true
  }
}
```

**Response:**
```json
{
  "status": "completed",
  "ok": true,
  "comfyui_up": true,
  "paths": {
    "comfy_root": "/ComfyUI",
    "input_dir": "/ComfyUI/input",
    "output_dir": "/ComfyUI/output"
  },
  "disk_free_gb": 123.45,
  "volume_mounted": true,
  "handler_version": "2026-02-05-v1"
}
```

**cURL Example:**
```bash
curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"input": {"test": true}}'
```

### Mode 2: Diagnose

Comprehensive diagnostics including model availability, node checks, and workflow validation.

**Request:**
```json
{
  "input": {
    "diagnose": true
  }
}
```

**Response:**
```json
{
  "status": "completed",
  "comfyui_reachable": true,
  "disk_usage": {
    "total_gb": 500.0,
    "used_gb": 234.5,
    "free_gb": 265.5
  },
  "volume_mounted": true,
  "models": {
    "diffusion_models": [
      "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors",
      "Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"
    ],
    "loras": ["tenexa-wan22-lora.safetensors"],
    "vae": ["Wan2_1_VAE_bf16.safetensors"],
    "text_encoders": ["umt5-xxl-enc-bf16.safetensors"],
    "clip_vision": ["clip_vision_h.safetensors"]
  },
  "node_check": {
    "success": true,
    "total_nodes": 450,
    "required_available": [
      "WanVideoModelLoader",
      "WanVideoSampler",
      "WanVideoImageToVideoEncode",
      "LoadImage",
      "VHS_VideoCombine"
    ],
    "required_missing": []
  },
  "workflow_checks": {
    "new_Wan22_api.json": {
      "exists": true,
      "nodes": 28,
      "missing_models": {
        "diffusion_models": [],
        "loras": []
      }
    }
  }
}
```

**cURL Example:**
```bash
curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"input": {"diagnose": true}}'
```

### Mode 3: Generate Video (Default)

Generate video from input image(s).

**Request:**
```json
{
  "input": {
    "image_base64": "<base64-encoded-png>",
    "workflow": "wan22_i2v",
    "seed": 42,
    "steps": 10,
    "cfg": 2.0,
    "frames": 81
  }
}
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_base64` | string | **required** | Base64-encoded input image (PNG/JPG) |
| `workflow` | string | `wan22_i2v` | Workflow type: `wan22_i2v` or `flf2v` |
| `seed` | int | random | Random seed for reproducibility |
| `steps` | int | 10 | Sampling steps (higher = better quality, slower) |
| `cfg` | float | 2.0 | CFG scale (classifier-free guidance) |
| `frames` | int | 81 | Number of video frames to generate |
| `end_image_base64` | string | - | End frame for FLF2V mode (required if workflow=flf2v) |

**Success Response:**
```json
{
  "status": "completed",
  "video_base64": "<base64-encoded-mp4>",
  "seed": 42,
  "fps": 24,
  "frames": 81,
  "duration_sec": 3.38,
  "metadata": {
    "filename": "output_video.mp4",
    "size_bytes": 1234567,
    "size_mb": 1.23
  },
  "handler_version": "2026-02-05-v1"
}
```

**Error Response:**
```json
{
  "status": "failed",
  "error_code": "NO_OUTPUT",
  "error_message": "No video file generated",
  "logs_tail": "... last 80 lines of ComfyUI log ..."
}
```

**Error Codes:**

- `COMFY_NOT_READY` - ComfyUI failed to start or not responding
- `NO_IMAGE` - Missing required `image_base64` parameter
- `NO_END_IMAGE` - FLF2V mode requires `end_image_base64`
- `QUEUE_FAILED` - Failed to submit workflow to ComfyUI
- `TIMEOUT` - Execution timeout (default 600s)
- `NO_OUTPUT` - Video generation completed but no output file found
- `GENERATION_ERROR` - General error during generation

**cURL Example:**
```bash
# Encode image to base64
IMAGE_B64=$(base64 -w 0 example_image.png)

# Send request
curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d "{\"input\": {\"image_base64\": \"$IMAGE_B64\", \"steps\": 10}}"
```

### First-Last-Frame Mode (FLF2V)

Generate video transitioning between two images.

**Request:**
```json
{
  "input": {
    "image_base64": "<start-image-base64>",
    "end_image_base64": "<end-image-base64>",
    "workflow": "flf2v",
    "frames": 81
  }
}
```

## Test Scripts

### send_test.py

Send a test image and save the generated video.

```bash
# Install dependencies
pip install requests

# Run test
python scripts/send_test.py \
  https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync \
  --image example_image.png \
  --output result.mp4 \
  --steps 10 \
  --frames 81
```

### diagnose.py

Run full diagnostics on the endpoint.

```bash
# Quick health check
python scripts/diagnose.py \
  https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync \
  --test

# Full diagnostics
python scripts/diagnose.py \
  https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync
```

## Model Files

The Docker image includes these models by default:

- **Diffusion Models:**
  - `Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors` (18.8 GB)
  - `Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors` (18.8 GB)

- **Text Encoder:**
  - `umt5-xxl-enc-bf16.safetensors` (9.5 GB)

- **VAE:**
  - `Wan2_1_VAE_bf16.safetensors` (337 MB)

- **CLIP Vision:**
  - `clip_vision_h.safetensors` (3.7 GB)

- **LoRA:**
  - `tenexa-wan22-lora.safetensors` (226 MB)

**Total:** ~51 GB of models

## Volume Usage

To use custom models or LoRAs from a RunPod volume:

1. Create and mount a network volume at `/runpod-volume`
2. Upload files to the appropriate subdirectories
3. ComfyUI will automatically detect them via `extra_model_paths.yaml`

**Volume Structure:**
```
/runpod-volume/
├── models/              # Custom diffusion models
│   └── your-model.safetensors
├── loras/               # Custom LoRAs
│   └── your-lora.safetensors
└── clip/                # Custom CLIP models
    └── your-clip.safetensors
```

The `extra_model_paths.yaml` configuration automatically searches both local and volume paths.

## Architecture

```
┌─────────────────────────────────────────┐
│         RunPod Container                │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  entrypoint.sh                   │  │
│  │  1. Download models              │  │
│  │  2. Start ComfyUI (background)   │  │
│  │  3. Wait for readiness (120s)    │  │
│  │  4. Start handler.py             │  │
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────┐    ┌──────────────┐  │
│  │  ComfyUI     │◄──►│  handler.py  │  │
│  │  :8188       │    │  (RunPod)    │  │
│  └──────────────┘    └──────────────┘  │
│         ▲                               │
│         │                               │
│  ┌──────┴───────────────────────────┐  │
│  │  Models & Workflows              │  │
│  │  - /ComfyUI/models/              │  │
│  │  - /runpod-volume/ (optional)    │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## Troubleshooting

### Request Sits in Queue Forever

**Cause:** ComfyUI not starting or handler crash.

**Solution:**
1. Check RunPod logs for startup errors
2. Run diagnose mode to check system status
3. Verify sufficient GPU memory (48GB+ required)

### "COMFY_NOT_READY" Error

**Cause:** ComfyUI failed to start within timeout (120s).

**Solution:**
1. Check if models are downloading (first cold start takes time)
2. Increase `COMFY_READY_TIMEOUT` environment variable
3. Check logs_tail in error response for ComfyUI errors

### Missing Models Error

**Cause:** Workflow references models not present on disk.

**Solution:**
1. Run diagnose mode to see what's missing
2. Either add models to volume or modify workflow
3. Check `extra_model_paths.yaml` configuration

### "NO_OUTPUT" Error

**Cause:** ComfyUI executed but didn't produce video file.

**Solution:**
1. Check ComfyUI logs in error response
2. Verify workflow JSON is valid
3. Check disk space (diagnose mode shows this)

### Timeout During Generation

**Cause:** Generation takes longer than `COMFY_EXEC_TIMEOUT` (default 600s).

**Solution:**
1. Reduce `frames` parameter (fewer frames = faster)
2. Reduce `steps` parameter (fewer steps = faster but lower quality)
3. Increase `COMFY_EXEC_TIMEOUT` environment variable

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFY_ROOT` | `/ComfyUI` | ComfyUI installation directory |
| `SERVER_ADDRESS` | `127.0.0.1` | ComfyUI server address |
| `COMFY_READY_TIMEOUT` | `120` | Seconds to wait for ComfyUI startup |
| `COMFY_EXEC_TIMEOUT` | `600` | Seconds to wait for video generation |
| `HANDLER_VERSION` | auto | Handler version string |

## Files

- `handler.py` - RunPod serverless handler (test/diagnose/generate modes)
- `entrypoint.sh` - Startup script with robust ComfyUI initialization
- `Dockerfile` - Multi-stage build with ffmpeg and all dependencies
- `extra_model_paths.yaml` - ComfyUI model path configuration
- `new_Wan22_api.json` - Standard I2V workflow
- `new_Wan22_flf2v_api.json` - First-last-frame workflow
- `scripts/send_test.py` - Test script for endpoint
- `scripts/diagnose.py` - Diagnostic script
- `example_image.png` - Sample input image

## Requirements

- **GPU:** 48GB+ VRAM (A6000, A100, L40S, etc.)
- **Storage:** ~60GB for models + workspace
- **Memory:** 32GB+ RAM recommended

## License

MIT

## Credits

- Wan Video models by Kijai
- ComfyUI by comfyanonymous
- Custom nodes: ComfyUI-Manager, ComfyUI-WanVideoWrapper, ComfyUI-VideoHelperSuite, etc.
