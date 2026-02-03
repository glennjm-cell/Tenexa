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
from typing import Any, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server_address = os.getenv("SERVER_ADDRESS", "127.0.0.1")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def to_nearest_multiple_of_16(value):
    numeric_value = float(value)
    adjusted = int(round(numeric_value / 16.0) * 16)
    return max(adjusted, 16)


def download_with_timeout(url, path, timeout=30):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        with open(path, "wb") as f:
            f.write(r.read())
    return path


def save_base64_to_file(base64_data, temp_dir, filename):
    os.makedirs(temp_dir, exist_ok=True)
    path = os.path.join(temp_dir, filename)
    with open(path, "wb") as f:
        f.write(base64.b64decode(base64_data))
    return path


def process_input(input_data, temp_dir, filename, input_type):
    if input_type == "path":
        return input_data
    if input_type == "url":
        return download_with_timeout(input_data, os.path.join(temp_dir, filename))
    if input_type == "base64":
        return save_base64_to_file(input_data, temp_dir, filename)
    raise Exception("Unsupported input type")


def queue_prompt(prompt, client_id):
    url = f"http://{server_address}:8188/prompt"
    payload = {"prompt": prompt, "client_id": client_id}
    req = urllib.request.Request(url, json.dumps(payload).encode("utf-8"))
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def get_history(prompt_id):
    url = f"http://{server_address}:8188/history/{prompt_id}"
    return json.loads(urllib.request.urlopen(url, timeout=10).read())


def get_videos(ws, prompt, client_id):
    prompt_id = queue_prompt(prompt, client_id)["prompt_id"]
    logger.info(f"🟢 Prompt queued: {prompt_id}")

    start_time = time.time()
    MAX_WAIT = 300

    while True:
        if time.time() - start_time > MAX_WAIT:
            raise TimeoutError("ComfyUI execution timed out")

        try:
            ws.settimeout(5)
            msg = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue

        if isinstance(msg, str):
            msg = json.loads(msg)
            if msg.get("type") == "executing":
                data = msg.get("data", {})
                if data.get("node") is None and data.get("prompt_id") == prompt_id:
                    logger.info("🟢 ComfyUI execution finished")
                    break

    history = get_history(prompt_id).get(prompt_id, {})
    outputs = history.get("outputs", {})

    videos = []
    for node in outputs.values():
        if "gifs" in node:
            for video in node["gifs"]:
                with open(video["fullpath"], "rb") as f:
                    videos.append(base64.b64encode(f.read()).decode())

    if not videos:
        logger.error(f"❌ No video generated. History: {json.dumps(history, indent=2)}")

    return videos


def load_workflow(filename: str) -> Dict[str, Any]:
    """
    Robust workflow loader:
    - Clear error if missing
    - Clear error if empty
    - Clear error if invalid JSON (with preview)
    """
    path = os.path.join(BASE_DIR, filename)

    if not os.path.exists(path):
        raise FileNotFoundError(f"Workflow file not found: {path}")

    # Read raw first so we can detect empty or invalid content clearly
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    if not raw.strip():
        raise ValueError(f"Workflow file is empty (0 bytes / blank): {path}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        preview = raw[:200].replace("\n", "\\n")
        raise ValueError(f"Workflow JSON invalid: {path} | {e} | preview='{preview}'")


def wait_for_comfyui():
    start = time.time()
    READY_TIMEOUT = 180

    logger.info("⏳ Waiting for ComfyUI to become ready...")

    while True:
        if time.time() - start > READY_TIMEOUT:
            raise RuntimeError("❌ ComfyUI failed to start within 180 seconds")

        try:
            urllib.request.urlopen(f"http://{server_address}:8188/", timeout=2)
            logger.info("✅ ComfyUI is ready.")
            return
        except:
            time.sleep(1)


def handler(job):
    client_id = str(uuid.uuid4())
    task_dir = f"/tmp/task_{uuid.uuid4()}"

    try:
        job_input = job.get("input", {}) or {}
        logger.info(f"🟡 New job received keys: {list(job_input.keys())}")

        # =========================
        # WARMUP / TEST SHORT-CIRCUIT
        # =========================
        # Your earlier test payload was {"input":{"test":true}}
        # This prevents it from crashing by trying to load workflows.
        if job_input.get("warmup") is True or job_input.get("test") is True:
            # Still waits for ComfyUI so you can use this as a warmup trigger
            wait_for_comfyui()
            return {
                "ok": True,
                "message": "Warmup/test acknowledged. ComfyUI ready.",
                "server_address": server_address
            }

        # =========================
        # IMAGE INPUT (FIXED ORDER)
        # =========================
        if "image_base64" in job_input:
            image_path = process_input(job_input["image_base64"], task_dir, "image.png", "base64")
        elif "image_url" in job_input:
            image_path = process_input(job_input["image_url"], task_dir, "image.png", "url")
        elif "image_path" in job_input:
            image_path = process_input(job_input["image_path"], task_dir, "image.png", "path")
        else:
            image_path = os.path.join(BASE_DIR, "example_image.png")

        # Optional end image
        end_image_path = None
        if "end_image_path" in job_input:
            end_image_path = process_input(job_input["end_image_path"], task_dir, "end.png", "path")
        elif "end_image_url" in job_input:
            end_image_path = process_input(job_input["end_image_url"], task_dir, "end.png", "url")
        elif "end_image_base64" in job_input:
            end_image_path = process_input(job_input["end_image_base64"], task_dir, "end.png", "base64")

        workflow_file = "new_Wan22_flf2v_api.json" if end_image_path else "new_Wan22_api.json"
        workflow_path = os.path.join(BASE_DIR, workflow_file)
        logger.info(f"📄 Using workflow: {workflow_path}")

        prompt = load_workflow(workflow_file)

        seed = int(job_input.get("seed", int(time.time())))
        cfg = float(job_input.get("cfg", 2.0))
        length = int(job_input.get("length", 81))
        steps = int(job_input.get("steps", 10))

        # ---- Apply inputs to workflow (your existing node IDs) ----
        prompt["244"]["inputs"]["image"] = image_path
        prompt["541"]["inputs"]["num_frames"] = length
        prompt["135"]["inputs"]["positive_prompt"] = job_input.get("prompt", "")
        prompt["135"]["inputs"]["negative_prompt"] = job_input.get(
            "negative_prompt",
            "bright tones, overexposed, static, blurred details"
        )

        prompt["220"]["inputs"]["seed"] = seed
        prompt["540"]["inputs"]["seed"] = seed
        prompt["540"]["inputs"]["cfg"] = cfg

        prompt["235"]["inputs"]["value"] = to_nearest_multiple_of_16(job_input.get("width", 480))
        prompt["236"]["inputs"]["value"] = to_nearest_multiple_of_16(job_input.get("height", 832))

        prompt["498"]["inputs"]["context_frames"] = length
        prompt["498"]["inputs"]["context_overlap"] = int(job_input.get("context_overlap", 48))

        if "834" in prompt:
            prompt["834"]["inputs"]["steps"] = steps
            prompt["829"]["inputs"]["step"] = int(steps * 0.6)

        if end_image_path:
            prompt["617"]["inputs"]["image"] = end_image_path

        wait_for_comfyui()

        ws = websocket.WebSocket()
        ws.connect(f"ws://{server_address}:8188/ws?clientId={client_id}")

        videos = get_videos(ws, prompt, client_id)
        ws.close()

        if videos:
            logger.info("🎉 Video generated successfully")

            # Return a stable key name for your web app
            # (your PHP/JS can look for output.video_base64)
            return {
                "video_base64": videos[0],
                "video": videos[0]  # optional backwards-compat
            }

        return {"error": "No video generated"}

    except Exception as e:
        # Surface errors clearly in RunPod /status output
        logger.exception("❌ Handler error")
        return {"error": str(e)}

    finally:
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True)


runpod.serverless.start({"handler": handler})
