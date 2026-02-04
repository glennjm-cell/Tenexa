import runpod
import os
import websocket
import base64
import json
import uuid
import logging
import urllib.request
import time
import shutil
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ComfyUI server inside the container
server_address = os.getenv("SERVER_ADDRESS", "127.0.0.1")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Version stamp to prove the new handler is actually deployed
HANDLER_VERSION = os.getenv("HANDLER_VERSION", "2026-02-04-01")


def to_nearest_multiple_of_16(value) -> int:
    """Comfy/WAN likes multiples of 16. Accepts numeric-ish input."""
    try:
        numeric_value = float(value)
    except Exception:
        numeric_value = 16.0
    adjusted = int(round(numeric_value / 16.0) * 16)
    return max(adjusted, 16)


def download_with_timeout(url: str, path: str, timeout: int = 60) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        with open(path, "wb") as f:
            f.write(r.read())
    return path


def save_base64_to_file(base64_data: str, temp_dir: str, filename: str) -> str:
    os.makedirs(temp_dir, exist_ok=True)
    path = os.path.join(temp_dir, filename)
    with open(path, "wb") as f:
        f.write(base64.b64decode(base64_data))
    return path


def process_input(input_data: str, temp_dir: str, filename: str, input_type: str) -> str:
    if input_type == "path":
        return input_data
    if input_type == "url":
        return download_with_timeout(input_data, os.path.join(temp_dir, filename))
    if input_type == "base64":
        return save_base64_to_file(input_data, temp_dir, filename)
    raise ValueError(f"Unsupported input type: {input_type}")


def http_json(url: str, method: str = "GET", payload: Optional[dict] = None, timeout: int = 15) -> dict:
    if payload is None:
        req = urllib.request.Request(url, method=method)
    else:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method=method,
        )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if not data:
        return {}
    return json.loads(data)


def queue_prompt(prompt: Dict[str, Any], client_id: str) -> Dict[str, Any]:
    url = f"http://{server_address}:8188/prompt"
    payload = {"prompt": prompt, "client_id": client_id}
    return http_json(url, method="POST", payload=payload, timeout=30)


def get_history(prompt_id: str) -> Dict[str, Any]:
    url = f"http://{server_address}:8188/history/{prompt_id}"
    return http_json(url, method="GET", timeout=30)


def wait_for_comfyui(ready_timeout: int = 180) -> None:
    """Wait until ComfyUI responds on the root endpoint."""
    start = time.time()
    logger.info("⏳ Waiting for ComfyUI to become ready...")
    while True:
        if time.time() - start > ready_timeout:
            raise RuntimeError(f"❌ ComfyUI failed to start within {ready_timeout} seconds")

        try:
            urllib.request.urlopen(f"http://{server_address}:8188/", timeout=2)
            logger.info("✅ ComfyUI is ready.")
            return
        except Exception:
            time.sleep(1)


def load_workflow(filename: str) -> Dict[str, Any]:
    """
    Robust workflow loader (fixes your JSONDecodeError mystery):
    - clear error if missing
    - clear error if empty
    - clear error if invalid JSON (with preview)
    """
    path = os.path.join(BASE_DIR, filename)

    if not os.path.exists(path):
        raise FileNotFoundError(f"Workflow file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    if not raw.strip():
        raise ValueError(f"Workflow file is empty (0 bytes / blank): {path}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        preview = raw[:250].replace("\n", "\\n")
        raise ValueError(f"Workflow JSON invalid: {path} | {e} | preview='{preview}'")


def get_videos(ws: websocket.WebSocket, prompt: Dict[str, Any], client_id: str) -> List[str]:
    queued = queue_prompt(prompt, client_id)
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return prompt_id. Response: {queued}")

    logger.info(f"🟢 Prompt queued: {prompt_id}")

    start_time = time.time()
    MAX_WAIT = int(os.getenv("COMFY_MAX_WAIT", "600"))  # seconds

    # Wait for ComfyUI to finish executing this prompt_id
    while True:
        if time.time() - start_time > MAX_WAIT:
            raise TimeoutError(f"ComfyUI execution timed out after {MAX_WAIT}s (prompt_id={prompt_id})")

        try:
            ws.settimeout(5)
            msg = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue

        # Websocket messages can be JSON strings or bytes; we only need the JSON status frames.
        if isinstance(msg, (bytes, bytearray)):
            continue

        try:
            data = json.loads(msg)
        except Exception:
            continue

        if data.get("type") == "executing":
            exec_data = data.get("data", {})
            # When node is None, ComfyUI reports it finished for that prompt_id
            if exec_data.get("node") is None and exec_data.get("prompt_id") == prompt_id:
                logger.info("🟢 ComfyUI execution finished")
                break

    history = get_history(prompt_id).get(prompt_id, {})
    outputs = history.get("outputs", {})

    videos_b64: List[str] = []

    # Your workflow returns "gifs" from VideoHelperSuite/outputs
    for node in outputs.values():
        if isinstance(node, dict) and "gifs" in node:
            for vid in node.get("gifs", []):
                fullpath = vid.get("fullpath")
                if fullpath and os.path.exists(fullpath):
                    with open(fullpath, "rb") as f:
                        videos_b64.append(base64.b64encode(f.read()).decode("utf-8"))

        # Some workflows output "videos" instead of "gifs"
        if isinstance(node, dict) and "videos" in node:
            for vid in node.get("videos", []):
                fullpath = vid.get("fullpath")
                if fullpath and os.path.exists(fullpath):
                    with open(fullpath, "rb") as f:
                        videos_b64.append(base64.b64encode(f.read()).decode("utf-8"))

    if not videos_b64:
        logger.error(f"❌ No video generated. History:\n{json.dumps(history, indent=2)}")

    return videos_b64


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(f"✅ HANDLER VERSION: {HANDLER_VERSION}")

    client_id = str(uuid.uuid4())
    task_dir = f"/tmp/task_{uuid.uuid4()}"

    try:
        job_input = job.get("input", {}) or {}
        logger.info(f"🟡 New job received keys: {list(job_input.keys())}")

        # =========================
        # WARMUP / TEST SHORT-CIRCUIT
        # =========================
        # This prevents test jobs from crashing by trying to load workflows.
        if job_input.get("warmup") is True or job_input.get("test") is True:
            wait_for_comfyui()
            return {
                "ok": True,
                "message": "Warmup/test acknowledged. ComfyUI ready.",
                "server_address": server_address,
                "handler_version": HANDLER_VERSION,
            }

        # =========================
        # IMAGE INPUT (priority order)
        # =========================
        if "image_base64" in job_input:
            image_path = process_input(job_input["image_base64"], task_dir, "image.png", "base64")
        elif "image_url" in job_input:
            image_path = process_input(job_input["image_url"], task_dir, "image.png", "url")
        elif "image_path" in job_input:
            image_path = process_input(job_input["image_path"], task_dir, "image.png", "path")
        else:
            # Fallback sample; must exist in your repo or you'll get a clear error later.
            image_path = os.path.join(BASE_DIR, "example_image.png")

        # Optional end image
        end_image_path: Optional[str] = None
        if "end_image_base64" in job_input:
            end_image_path = process_input(job_input["end_image_base64"], task_dir, "end.png", "base64")
        elif "end_image_url" in job_input:
            end_image_path = process_input(job_input["end_image_url"], task_dir, "end.png", "url")
        elif "end_image_path" in job_input:
            end_image_path = process_input(job_input["end_image_path"], task_dir, "end.png", "path")

        # =========================
        # WORKFLOW PICK
        # =========================
        workflow_file = "new_Wan22_flf2v_api.json" if end_image_path else "new_Wan22_api.json"
        workflow_path = os.path.join(BASE_DIR, workflow_file)
        logger.info(f"📄 Using workflow: {workflow_path}")

        # This is where your old handler was dying with JSONDecodeError.
        # Now it will give a clear error if missing/empty/invalid.
        prompt = load_workflow(workflow_file)

        # =========================
        # PARAMS
        # =========================
        seed = int(job_input.get("seed", int(time.time())))
        cfg = float(job_input.get("cfg", 2.0))
        length = int(job_input.get("length", 81))
        steps = int(job_input.get("steps", 10))

        width = to_nearest_multiple_of_16(job_input.get("width", 480))
        height = to_nearest_multiple_of_16(job_input.get("height", 832))

        positive = job_input.get("prompt", "")
        negative = job_input.get(
            "negative_prompt",
            "bright tones, overexposed, static, blurred details"
        )

        context_overlap = int(job_input.get("context_overlap", 48))

        # =========================
        # APPLY TO YOUR NODE IDS
        # =========================
        # IMPORTANT: These IDs must match your exported ComfyUI workflow JSON.
        # If any are wrong, you'll see it in ComfyUI history output.
        prompt["244"]["inputs"]["image"] = image_path
        prompt["541"]["inputs"]["num_frames"] = length

        prompt["135"]["inputs"]["positive_prompt"] = positive
        prompt["135"]["inputs"]["negative_prompt"] = negative

        prompt["220"]["inputs"]["seed"] = seed
        prompt["540"]["inputs"]["seed"] = seed
        prompt["540"]["inputs"]["cfg"] = cfg

        prompt["235"]["inputs"]["value"] = width
        prompt["236"]["inputs"]["value"] = height

        prompt["498"]["inputs"]["context_frames"] = length
        prompt["498"]["inputs"]["context_overlap"] = context_overlap

        # Optional step nodes (only if they exist in this workflow)
        if "834" in prompt and isinstance(prompt["834"], dict) and "inputs" in prompt["834"]:
            prompt["834"]["inputs"]["steps"] = steps
        if "829" in prompt and isinstance(prompt["829"], dict) and "inputs" in prompt["829"]:
            prompt["829"]["inputs"]["step"] = int(steps * 0.6)

        # End image node for FLF2V workflow
        if end_image_path:
            if "617" not in prompt:
                raise KeyError("End-image workflow selected but node '617' not found in workflow JSON")
            prompt["617"]["inputs"]["image"] = end_image_path

        # =========================
        # RUN COMFY
        # =========================
        wait_for_comfyui()

        ws = websocket.WebSocket()
        ws.connect(f"ws://{server_address}:8188/ws?clientId={client_id}")

        videos = get_videos(ws, prompt, client_id)
        ws.close()

        if videos:
            logger.info("🎉 Video generated successfully")
            # Stable return key for your webapp
            return {
                "video_base64": videos[0],
                "video": videos[0],  # optional compat
                "handler_version": HANDLER_VERSION,
            }

        return {
            "error": "No video generated",
            "handler_version": HANDLER_VERSION,
        }

    except Exception as e:
        logger.exception("❌ Handler error")
        return {
            "error": str(e),
            "handler_version": HANDLER_VERSION,
        }

    finally:
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True)


runpod.serverless.start({"handler": handler})
