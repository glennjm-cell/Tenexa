import runpod
from runpod.serverless.utils import rp_upload
import os
import websocket
import base64
import json
import uuid
import logging
import urllib.request
import urllib.parse
import subprocess
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server_address = os.getenv("SERVER_ADDRESS", "127.0.0.1")
client_id = str(uuid.uuid4())

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def to_nearest_multiple_of_16(value):
    try:
        numeric_value = float(value)
    except Exception:
        raise Exception(f"width/height is not numeric: {value}")
    adjusted = int(round(numeric_value / 16.0) * 16)
    return max(adjusted, 16)


def ensure_lora_downloaded(repo_id, filename, target_dir="/ComfyUI/models/loras"):
    os.makedirs(target_dir, exist_ok=True)
    local_path = os.path.join(target_dir, filename)

    if not os.path.exists(local_path):
        url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
        logger.info(f"Downloading LoRA: {url}")
        subprocess.run(["wget", "-O", local_path, url], check=True)

    return local_path


def download_file_from_url(url, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result = subprocess.run(
        ["wget", "-O", output_path, "--no-verbose", url],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise Exception(f"Download failed: {result.stderr}")
    return output_path


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
        return download_file_from_url(input_data, os.path.join(temp_dir, filename))
    if input_type == "base64":
        return save_base64_to_file(input_data, temp_dir, filename)
    raise Exception("Unsupported input type")


def queue_prompt(prompt):
    url = f"http://{server_address}:8188/prompt"
    payload = {"prompt": prompt, "client_id": client_id}
    req = urllib.request.Request(url, json.dumps(payload).encode("utf-8"))
    return json.loads(urllib.request.urlopen(req).read())


def get_history(prompt_id):
    url = f"http://{server_address}:8188/history/{prompt_id}"
    return json.loads(urllib.request.urlopen(url).read())


def get_videos(ws, prompt):
    prompt_id = queue_prompt(prompt)["prompt_id"]

    while True:
        msg = ws.recv()
        if isinstance(msg, str):
            msg = json.loads(msg)
            if msg["type"] == "executing":
                if msg["data"]["node"] is None and msg["data"]["prompt_id"] == prompt_id:
                    break

    history = get_history(prompt_id)[prompt_id]
    videos = []

    for node in history["outputs"].values():
        if "gifs" in node:
            for video in node["gifs"]:
                with open(video["fullpath"], "rb") as f:
                    videos.append(base64.b64encode(f.read()).decode())

    return videos


def load_workflow(filename):
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Workflow file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def handler(job):
    job_input = job.get("input", {})
    task_id = f"/tmp/task_{uuid.uuid4()}"

    # Image input (required)
    if "image_path" in job_input:
        image_path = process_input(job_input["image_path"], task_id, "image.png", "path")
    elif "image_url" in job_input:
        image_path = process_input(job_input["image_url"], task_id, "image.png", "url")
    elif "image_base64" in job_input:
        image_path = process_input(job_input["image_base64"], task_id, "image.png", "base64")
    else:
        image_path = "/example_image.png"

    # End image (optional for FLF2V mode)
    end_image_path = None
    if "end_image_path" in job_input:
        end_image_path = process_input(job_input["end_image_path"], task_id, "end.png", "path")
    elif "end_image_url" in job_input:
        end_image_path = process_input(job_input["end_image_url"], task_id, "end.png", "url")
    elif "end_image_base64" in job_input:
        end_image_path = process_input(job_input["end_image_base64"], task_id, "end.png", "base64")

    # Load workflow
    workflow_file = "new_Wan22_flf2v_api.json" if end_image_path else "new_Wan22_api.json"
    prompt = load_workflow(workflow_file)

    # Parameters with defaults
    seed = job_input.get("seed", int(time.time()))
    cfg = job_input.get("cfg", 2.0)
    length = job_input.get("length", 81)
    steps = job_input.get("steps", 10)

    # Set workflow parameters
    prompt["244"]["inputs"]["image"] = image_path
    prompt["541"]["inputs"]["num_frames"] = length
    prompt["135"]["inputs"]["positive_prompt"] = job_input.get("prompt", "")
    prompt["135"]["inputs"]["negative_prompt"] = job_input.get("negative_prompt", "bright tones, overexposed, static, blurred details")

    prompt["220"]["inputs"]["seed"] = seed
    prompt["540"]["inputs"]["seed"] = seed
    prompt["540"]["inputs"]["cfg"] = cfg

    prompt["235"]["inputs"]["value"] = to_nearest_multiple_of_16(job_input.get("width", 480))
    prompt["236"]["inputs"]["value"] = to_nearest_multiple_of_16(job_input.get("height", 832))

    prompt["498"]["inputs"]["context_frames"] = length
    prompt["498"]["inputs"]["context_overlap"] = job_input.get("context_overlap", 48)

    if "834" in prompt:
        prompt["834"]["inputs"]["steps"] = steps
        prompt["829"]["inputs"]["step"] = int(steps * 0.6)

    if end_image_path:
        prompt["617"]["inputs"]["image"] = end_image_path

    # LoRA support (up to 4 pairs)
    lora_pairs = job_input.get("lora_pairs", [])[:4]

    for i, pair in enumerate(lora_pairs):
        hi = pair.get("high_repo")
        hi_file = pair.get("high_file")
        lo = pair.get("low_repo")
        lo_file = pair.get("low_file")

        if hi and hi_file:
            prompt["279"]["inputs"][f"lora_{i+1}"] = ensure_lora_downloaded(hi, hi_file)
            prompt["279"]["inputs"][f"strength_{i+1}"] = pair.get("high_weight", 1.0)

        if lo and lo_file:
            prompt["553"]["inputs"][f"lora_{i+1}"] = ensure_lora_downloaded(lo, lo_file)
            prompt["553"]["inputs"][f"strength_{i+1}"] = pair.get("low_weight", 1.0)

    # Wait for ComfyUI to be ready
    for _ in range(180):
        try:
            urllib.request.urlopen(f"http://{server_address}:8188/", timeout=5)
            break
        except:
            time.sleep(1)

    ws = websocket.WebSocket()
    ws.connect(f"ws://{server_address}:8188/ws?clientId={client_id}")

    videos = get_videos(ws, prompt)
    ws.close()

    if videos:
        return {"video": videos[0]}

    return {"error": "No video generated"}


runpod.serverless.start({"handler": handler})
