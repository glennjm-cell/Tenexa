# Wan2.2 Image-to-Video RunPod Serverless Endpoint

A RunPod serverless endpoint for generating AI videos from images using the Wan2.2 model with ComfyUI.

## Features

- Image-to-video generation using Wan2.2-I2V-A14B model
- Support for base64, URL, or path input images
- Optional end image for first-last-frame-to-video (FLF2V) mode
- Dynamic LoRA loading from HuggingFace
- Configurable video parameters (resolution, length, steps, CFG, seed)

## Setup

### 1. Build the Docker Image

```bash
docker build -t wan22-serverless .
```

### 2. Push to Docker Hub

```bash
docker tag wan22-serverless your-username/wan22-serverless:latest
docker push your-username/wan22-serverless:latest
```

### 3. Create RunPod Endpoint

1. Go to [RunPod Serverless](https://www.runpod.io/console/serverless)
2. Create new endpoint
3. Use your Docker image: `your-username/wan22-serverless:latest`
4. Set GPU: 48GB+ VRAM recommended (A6000, A100, etc.)
5. Set max workers based on your needs

## API Usage

### Basic Request

```json
{
  "input": {
    "image_base64": "<base64-encoded-image>",
    "prompt": "A person walking through a forest",
    "width": 480,
    "height": 832,
    "length": 81,
    "steps": 10,
    "cfg": 2.0,
    "seed": 12345
  }
}
```

### Input Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_base64` | string | - | Base64 encoded input image |
| `image_url` | string | - | URL to input image |
| `image_path` | string | - | Path to input image |
| `prompt` | string | "" | Text prompt for video generation |
| `negative_prompt` | string | "bright tones, overexposed, static, blurred details" | Negative prompt |
| `width` | int | 480 | Video width (rounded to nearest 16) |
| `height` | int | 832 | Video height (rounded to nearest 16) |
| `length` | int | 81 | Number of frames |
| `steps` | int | 10 | Sampling steps |
| `cfg` | float | 2.0 | CFG scale |
| `seed` | int | random | Random seed |
| `context_overlap` | int | 48 | Context overlap frames |

### First-Last-Frame Mode (FLF2V)

Add an end image to generate video between two frames:

```json
{
  "input": {
    "image_base64": "<start-image>",
    "end_image_base64": "<end-image>",
    "prompt": "Smooth transition between poses"
  }
}
```

### Custom LoRA Loading

Load LoRAs dynamically from HuggingFace:

```json
{
  "input": {
    "image_base64": "<image>",
    "prompt": "...",
    "lora_pairs": [
      {
        "high_repo": "username/repo",
        "high_file": "lora-high.safetensors",
        "high_weight": 1.0,
        "low_repo": "username/repo",
        "low_file": "lora-low.safetensors",
        "low_weight": 1.0
      }
    ]
  }
}
```

### Response

```json
{
  "video": "<base64-encoded-mp4>"
}
```

## Files

- `handler.py` - RunPod serverless handler
- `Dockerfile` - Container build configuration
- `entrypoint.sh` - Startup script for ComfyUI + handler
- `extra_model_paths.yaml` - ComfyUI model paths configuration
- `new_Wan22_api.json` - Standard I2V workflow
- `new_Wan22_flf2v_api.json` - First-last-frame workflow
- `example_image.png` - Fallback test image

## Pre-installed Models

- Wan2.2-I2V-A14B-HIGH (fp8)
- Wan2.2-I2V-A14B-LOW (fp8)
- UMT5-XXL text encoder
- Wan2.1 VAE
- CLIP Vision H
- Tenexa LoRA

## License

MIT
