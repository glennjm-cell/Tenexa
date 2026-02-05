#!/usr/bin/env python3
"""
Tenexa RunPod Serverless Handler for Wan 2.2 Image-to-Video Generation
Supports: test, diagnose, and generate modes with full diagnostics
"""

import runpod
import os
import sys
import websocket
import base64
import json
import uuid
import logging
import urllib.request
import urllib.error
import time
import shutil
import re
from typing import Any, Dict, List, Optional
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Environment configuration
SERVER_ADDRESS = os.getenv("SERVER_ADDRESS", "127.0.0.1")
COMFY_ROOT = os.environ.get("COMFY_ROOT", "/ComfyUI")
COMFY_INPUT_DIR = os.path.join(COMFY_ROOT, "input")
COMFY_OUTPUT_DIR = os.path.join(COMFY_ROOT, "output")
COMFY_LOG_PATH = os.path.join(COMFY_ROOT, "comfy.log")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HANDLER_VERSION = os.getenv("HANDLER_VERSION", "2026-02-05-v1")

# Timeouts
COMFY_READY_TIMEOUT = int(os.getenv("COMFY_READY_TIMEOUT", "120"))
COMFY_EXEC_TIMEOUT = int(os.getenv("COMFY_EXEC_TIMEOUT", "600"))

# Volume paths
VOLUME_ROOT = "/runpod-volume"
VOLUME_MODELS = os.path.join(VOLUME_ROOT, "models")
VOLUME_LORAS = os.path.join(VOLUME_ROOT, "loras")


def _ensure_dirs():
    """Ensure ComfyUI directories exist"""
    os.makedirs(COMFY_INPUT_DIR, exist_ok=True)
    os.makedirs(COMFY_OUTPUT_DIR, exist_ok=True)


def get_comfy_logs_tail(lines: int = 80) -> str:
    """Get last N lines from ComfyUI log file"""
    try:
        if os.path.exists(COMFY_LOG_PATH):
            with open(COMFY_LOG_PATH, 'r') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        return "Log file not found"
    except Exception as e:
        return f"Error reading logs: {str(e)}"


def check_comfyui_ready(timeout: int = 5) -> bool:
    """Check if ComfyUI API is responding"""
    try:
        url = f"http://{SERVER_ADDRESS}:8188/system_stats"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return len(data) > 0
    except Exception:
        return False


def wait_for_comfyui(timeout: int = COMFY_READY_TIMEOUT) -> Dict[str, Any]:
    """
    Wait for ComfyUI to become ready.
    Returns dict with status and message.
    """
    start = time.time()
    logger.info(f"⏳ Waiting for ComfyUI (max {timeout}s)...")
    
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            logs = get_comfy_logs_tail(80)
            return {
                "ready": False,
                "error": f"ComfyUI failed to start within {timeout}s",
                "logs_tail": logs
            }
        
        if check_comfyui_ready():
            logger.info(f"✅ ComfyUI ready after {elapsed:.1f}s")
            return {"ready": True, "elapsed": elapsed}
        
        time.sleep(1)


def get_disk_usage() -> Dict[str, float]:
    """Get disk usage statistics in GB"""
    total, used, free = shutil.disk_usage(COMFY_ROOT)
    return {
        "total_gb": round(total / 1e9, 2),
        "used_gb": round(used / 1e9, 2),
        "free_gb": round(free / 1e9, 2)
    }


def check_volume_mounted() -> bool:
    """Check if RunPod volume is mounted"""
    return os.path.exists(VOLUME_ROOT) and os.path.isdir(VOLUME_ROOT)


def list_models() -> Dict[str, List[str]]:
    """List available models in ComfyUI directories"""
    models = {}
    
    # Check main ComfyUI model directories
    model_dirs = {
        "diffusion_models": os.path.join(COMFY_ROOT, "models", "diffusion_models"),
        "loras": os.path.join(COMFY_ROOT, "models", "loras"),
        "vae": os.path.join(COMFY_ROOT, "models", "vae"),
        "text_encoders": os.path.join(COMFY_ROOT, "models", "text_encoders"),
        "clip_vision": os.path.join(COMFY_ROOT, "models", "clip_vision"),
    }
    
    for name, path in model_dirs.items():
        try:
            if os.path.exists(path):
                models[name] = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
            else:
                models[name] = []
        except Exception as e:
            models[name] = [f"Error: {str(e)}"]
    
    # Check volume directories
    if check_volume_mounted():
        try:
            if os.path.exists(VOLUME_MODELS):
                models["volume_models"] = os.listdir(VOLUME_MODELS)
            if os.path.exists(VOLUME_LORAS):
                models["volume_loras"] = os.listdir(VOLUME_LORAS)
        except Exception as e:
            models["volume_error"] = str(e)
    
    return models


def check_workflow_requirements(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check if all models/loras referenced in workflow are available.
    Returns dict with missing items.
    """
    missing = {
        "diffusion_models": [],
        "loras": [],
        "other": []
    }
    
    available_models = list_models()
    
    # Check each node in workflow
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        
        inputs = node.get("inputs", {})
        class_type = node.get("class_type", "")
        
        # Check for model references
        if "ModelLoader" in class_type:
            model_name = inputs.get("model", "")
            if model_name and model_name not in available_models.get("diffusion_models", []):
                missing["diffusion_models"].append(model_name)
        
        # Check for LoRA references
        if "LoraSelect" in class_type or "LoRA" in class_type:
            for key, value in inputs.items():
                if "lora" in key.lower() and isinstance(value, str) and value:
                    all_loras = available_models.get("loras", []) + available_models.get("volume_loras", [])
                    if value not in all_loras and value != "None":
                        missing["loras"].append(value)
    
    return {
        "missing": missing,
        "has_missing": any(len(v) > 0 for v in missing.values())
    }


def check_object_info() -> Dict[str, Any]:
    """Check ComfyUI node availability via /object_info"""
    try:
        url = f"http://{SERVER_ADDRESS}:8188/object_info"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            
            # Check for key node types
            required_nodes = [
                "WanVideoModelLoader",
                "WanVideoSampler",
                "WanVideoImageToVideoEncode",
                "LoadImage",
                "VHS_VideoCombine"
            ]
            
            available = []
            missing = []
            
            for node_type in required_nodes:
                if node_type in data:
                    available.append(node_type)
                else:
                    missing.append(node_type)
            
            return {
                "success": True,
                "total_nodes": len(data),
                "required_available": available,
                "required_missing": missing
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def handle_test_mode() -> Dict[str, Any]:
    """Handle test/warmup mode - quick health check"""
    logger.info("🧪 Test mode")
    
    comfy_status = wait_for_comfyui(timeout=30)
    disk = get_disk_usage()
    
    return {
        "status": "completed",
        "ok": comfy_status.get("ready", False),
        "comfyui_up": comfy_status.get("ready", False),
        "paths": {
            "comfy_root": COMFY_ROOT,
            "input_dir": COMFY_INPUT_DIR,
            "output_dir": COMFY_OUTPUT_DIR
        },
        "disk_free_gb": disk["free_gb"],
        "volume_mounted": check_volume_mounted(),
        "handler_version": HANDLER_VERSION
    }


def handle_diagnose_mode() -> Dict[str, Any]:
    """Handle diagnose mode - comprehensive diagnostics"""
    logger.info("🔍 Diagnose mode")
    
    # Check ComfyUI
    comfy_status = wait_for_comfyui(timeout=30)
    
    result = {
        "status": "completed",
        "comfyui_reachable": comfy_status.get("ready", False),
        "disk_usage": get_disk_usage(),
        "volume_mounted": check_volume_mounted(),
        "paths": {
            "comfy_root": COMFY_ROOT,
            "input_dir": COMFY_INPUT_DIR,
            "output_dir": COMFY_OUTPUT_DIR,
            "volume_root": VOLUME_ROOT if check_volume_mounted() else None
        },
        "handler_version": HANDLER_VERSION
    }
    
    if not comfy_status.get("ready"):
        result["logs_tail"] = comfy_status.get("logs_tail", "")
        result["error"] = comfy_status.get("error", "")
        return result
    
    # List available models
    result["models"] = list_models()
    
    # Check node availability
    result["node_check"] = check_object_info()
    
    # Check workflows
    workflow_checks = {}
    for workflow_name in ["new_Wan22_api.json", "new_Wan22_flf2v_api.json"]:
        workflow_path = os.path.join(BASE_DIR, workflow_name)
        if os.path.exists(workflow_path):
            try:
                with open(workflow_path, 'r') as f:
                    workflow = json.load(f)
                requirements = check_workflow_requirements(workflow)
                workflow_checks[workflow_name] = {
                    "exists": True,
                    "nodes": len(workflow),
                    "missing_models": requirements["missing"]
                }
            except Exception as e:
                workflow_checks[workflow_name] = {
                    "exists": True,
                    "error": str(e)
                }
        else:
            workflow_checks[workflow_name] = {"exists": False}
    
    result["workflow_checks"] = workflow_checks
    
    return result


def save_image_from_base64(image_b64: str, filename: str) -> str:
    """
    Save base64 image to ComfyUI input directory.
    Returns the filename (not full path) for ComfyUI LoadImage nodes.
    """
    _ensure_dirs()
    
    # Strip data URI prefix if present
    if image_b64.startswith("data:image"):
        image_b64 = image_b64.split(",", 1)[1]
    
    # Decode and save
    image_data = base64.b64decode(image_b64)
    output_path = os.path.join(COMFY_INPUT_DIR, filename)
    
    with open(output_path, "wb") as f:
        f.write(image_data)
    
    logger.info(f"💾 Saved input image: {filename} ({len(image_data)} bytes)")
    return filename


def load_workflow(workflow_name: str) -> Dict[str, Any]:
    """Load workflow JSON from file"""
    workflow_path = os.path.join(BASE_DIR, workflow_name)
    
    if not os.path.exists(workflow_path):
        raise FileNotFoundError(f"Workflow not found: {workflow_path}")
    
    with open(workflow_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    
    if not content:
        raise ValueError(f"Workflow file is empty: {workflow_path}")
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        preview = content[:200]
        raise ValueError(f"Invalid JSON in {workflow_path}: {e}\nPreview: {preview}")


def patch_workflow_image(workflow: Dict[str, Any], image_filename: str, node_id: str = "244"):
    """Patch LoadImage node in workflow to use saved image"""
    if node_id in workflow and "inputs" in workflow[node_id]:
        workflow[node_id]["inputs"]["image"] = image_filename
        logger.info(f"✏️  Patched node {node_id} with image: {image_filename}")
    else:
        logger.warning(f"⚠️  Node {node_id} not found in workflow")


def queue_prompt(prompt: Dict[str, Any], client_id: str) -> Dict[str, Any]:
    """Submit workflow to ComfyUI queue"""
    url = f"http://{SERVER_ADDRESS}:8188/prompt"
    payload = {"prompt": prompt, "client_id": client_id}
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_history(prompt_id: str) -> Dict[str, Any]:
    """Get execution history for a prompt"""
    url = f"http://{SERVER_ADDRESS}:8188/history/{prompt_id}"
    req = urllib.request.Request(url, method="GET")
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def wait_for_completion(ws: websocket.WebSocket, prompt_id: str, timeout: int = COMFY_EXEC_TIMEOUT) -> Dict[str, Any]:
    """
    Wait for ComfyUI to complete execution via WebSocket.
    Returns history or raises TimeoutError.
    """
    start = time.time()
    logger.info(f"⏳ Waiting for execution (prompt_id: {prompt_id}, timeout: {timeout}s)")
    
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            raise TimeoutError(f"Execution timeout after {timeout}s")
        
        try:
            ws.settimeout(5)
            msg = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue
        
        # Parse WebSocket message
        if isinstance(msg, (bytes, bytearray)):
            continue
        
        try:
            data = json.loads(msg)
        except Exception:
            continue
        
        # Check for completion
        if data.get("type") == "executing":
            exec_data = data.get("data", {})
            node = exec_data.get("node")
            msg_prompt_id = exec_data.get("prompt_id")
            
            # When node is None and prompt_id matches, execution is complete
            if node is None and msg_prompt_id == prompt_id:
                logger.info(f"✅ Execution complete ({elapsed:.1f}s)")
                return get_history(prompt_id).get(prompt_id, {})
        
        # Check for errors
        if data.get("type") == "execution_error":
            error_data = data.get("data", {})
            raise RuntimeError(f"ComfyUI execution error: {json.dumps(error_data)}")


def find_output_video(history: Dict[str, Any]) -> Optional[str]:
    """
    Find generated MP4 file from ComfyUI history.
    Returns absolute path to video file.
    """
    outputs = history.get("outputs", {})
    
    for node_id, node_outputs in outputs.items():
        if not isinstance(node_outputs, dict):
            continue
        
        # Check for videos or gifs (VideoHelperSuite outputs as "gifs")
        for key in ["videos", "gifs"]:
            if key in node_outputs and isinstance(node_outputs[key], list):
                for item in node_outputs[key]:
                    if not isinstance(item, dict):
                        continue
                    
                    # Get file path
                    filename = item.get("filename")
                    subfolder = item.get("subfolder", "")
                    
                    if filename:
                        if subfolder:
                            full_path = os.path.join(COMFY_OUTPUT_DIR, subfolder, filename)
                        else:
                            full_path = os.path.join(COMFY_OUTPUT_DIR, filename)
                        
                        if os.path.exists(full_path) and full_path.endswith(('.mp4', '.gif')):
                            logger.info(f"📹 Found output: {full_path}")
                            return full_path
    
    # If not found in history, try to find newest MP4 in output dir
    try:
        mp4_files = []
        for root, dirs, files in os.walk(COMFY_OUTPUT_DIR):
            for file in files:
                if file.endswith('.mp4'):
                    full_path = os.path.join(root, file)
                    mp4_files.append((full_path, os.path.getmtime(full_path)))
        
        if mp4_files:
            mp4_files.sort(key=lambda x: x[1], reverse=True)
            newest = mp4_files[0][0]
            logger.info(f"📹 Found newest MP4: {newest}")
            return newest
    except Exception as e:
        logger.error(f"Error searching for MP4: {e}")
    
    return None


def encode_video_to_base64(video_path: str) -> str:
    """Encode video file to base64 string"""
    with open(video_path, "rb") as f:
        video_data = f.read()
    
    logger.info(f"📦 Encoded video: {len(video_data)} bytes")
    return base64.b64encode(video_data).decode("utf-8")


def get_video_metadata(video_path: str) -> Dict[str, Any]:
    """Get video metadata (basic info from file)"""
    try:
        stat = os.stat(video_path)
        return {
            "filename": os.path.basename(video_path),
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / 1024 / 1024, 2)
        }
    except Exception as e:
        return {"error": str(e)}


def handle_generate_mode(job_input: Dict[str, Any]) -> Dict[str, Any]:
    """Handle video generation mode"""
    logger.info("🎬 Generate mode")
    
    # Check ComfyUI is ready
    comfy_status = wait_for_comfyui(timeout=COMFY_READY_TIMEOUT)
    if not comfy_status.get("ready"):
        return {
            "status": "failed",
            "error_code": "COMFY_NOT_READY",
            "error_message": comfy_status.get("error", "ComfyUI not responding"),
            "logs_tail": comfy_status.get("logs_tail", "")
        }
    
    try:
        # Get input image
        image_b64 = job_input.get("image_base64")
        if not image_b64:
            return {
                "status": "failed",
                "error_code": "NO_IMAGE",
                "error_message": "Missing required parameter: image_base64"
            }
        
        # Save input image
        input_filename = "tenexa_input.png"
        save_image_from_base64(image_b64, input_filename)
        
        # Determine workflow
        workflow_type = job_input.get("workflow", "wan22_i2v")
        
        if workflow_type == "flf2v":
            workflow_file = "new_Wan22_flf2v_api.json"
            # Check for end image
            end_image_b64 = job_input.get("end_image_base64")
            if not end_image_b64:
                return {
                    "status": "failed",
                    "error_code": "NO_END_IMAGE",
                    "error_message": "FLF2V workflow requires end_image_base64"
                }
            end_filename = "tenexa_end.png"
            save_image_from_base64(end_image_b64, end_filename)
        else:
            workflow_file = "new_Wan22_api.json"
        
        logger.info(f"📄 Loading workflow: {workflow_file}")
        workflow = load_workflow(workflow_file)
        
        # Patch workflow with input image
        patch_workflow_image(workflow, input_filename, "244")
        
        if workflow_type == "flf2v":
            patch_workflow_image(workflow, end_filename, "617")
        
        # Apply parameters (with defaults)
        seed = int(job_input.get("seed", int(time.time())))
        cfg = float(job_input.get("cfg", 2.0))
        steps = int(job_input.get("steps", 10))
        num_frames = int(job_input.get("frames", 81))
        
        # Apply to workflow nodes (based on flf2v workflow structure)
        if "541" in workflow:  # WanVideoImageToVideoEncode
            workflow["541"]["inputs"]["num_frames"] = num_frames
        
        if "220" in workflow:  # First WanVideoSampler
            workflow["220"]["inputs"]["seed"] = seed
            workflow["220"]["inputs"]["cfg"] = cfg
            workflow["220"]["inputs"]["steps"] = steps
        
        if "540" in workflow:  # Second WanVideoSampler
            workflow["540"]["inputs"]["seed"] = seed
            workflow["540"]["inputs"]["cfg"] = cfg
        
        # Submit to ComfyUI
        client_id = str(uuid.uuid4())
        
        logger.info(f"📤 Submitting to ComfyUI (client_id: {client_id})")
        response = queue_prompt(workflow, client_id)
        prompt_id = response.get("prompt_id")
        
        if not prompt_id:
            return {
                "status": "failed",
                "error_code": "QUEUE_FAILED",
                "error_message": "ComfyUI did not return prompt_id",
                "response": response
            }
        
        # Connect WebSocket and wait for completion
        ws = websocket.WebSocket()
        ws.connect(f"ws://{SERVER_ADDRESS}:8188/ws?clientId={client_id}")
        
        history = wait_for_completion(ws, prompt_id, timeout=COMFY_EXEC_TIMEOUT)
        ws.close()
        
        # Find output video
        video_path = find_output_video(history)
        
        if not video_path:
            return {
                "status": "failed",
                "error_code": "NO_OUTPUT",
                "error_message": "No video file generated",
                "history": history
            }
        
        # Encode video
        video_b64 = encode_video_to_base64(video_path)
        metadata = get_video_metadata(video_path)
        
        # Get FPS from workflow or default
        fps = 24  # Default
        if "131" in workflow and "inputs" in workflow["131"]:
            fps = workflow["131"]["inputs"].get("frame_rate", 24)
        
        return {
            "status": "completed",
            "video_base64": video_b64,
            "seed": seed,
            "fps": fps,
            "frames": num_frames,
            "duration_sec": round(num_frames / fps, 2),
            "metadata": metadata,
            "handler_version": HANDLER_VERSION
        }
    
    except TimeoutError as e:
        return {
            "status": "failed",
            "error_code": "TIMEOUT",
            "error_message": str(e),
            "logs_tail": get_comfy_logs_tail(80)
        }
    except Exception as e:
        logger.exception("❌ Generation error")
        return {
            "status": "failed",
            "error_code": "GENERATION_ERROR",
            "error_message": str(e),
            "logs_tail": get_comfy_logs_tail(80)
        }


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main RunPod handler.
    Supports three modes:
    - test: {"input": {"test": true}}
    - diagnose: {"input": {"diagnose": true}}
    - generate: {"input": {"image_base64": "..."}}
    """
    logger.info(f"🚀 Handler called (version: {HANDLER_VERSION})")
    
    try:
        job_input = job.get("input", {})
        
        # Test mode
        if job_input.get("test") is True:
            return handle_test_mode()
        
        # Diagnose mode
        if job_input.get("diagnose") is True:
            return handle_diagnose_mode()
        
        # Generate mode (default)
        return handle_generate_mode(job_input)
    
    except Exception as e:
        logger.exception("❌ Handler error")
        return {
            "status": "failed",
            "error_code": "HANDLER_ERROR",
            "error_message": str(e),
            "handler_version": HANDLER_VERSION
        }


# Start RunPod serverless handler
runpod.serverless.start({"handler": handler})
