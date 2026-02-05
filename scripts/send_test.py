#!/usr/bin/env python3
"""
Test script for Tenexa RunPod endpoint
Reads a local PNG, sends to handler, and saves output MP4
"""

import os
import sys
import json
import base64
import argparse
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ requests not installed. Run: pip install requests")
    sys.exit(1)


def encode_image(image_path: str) -> str:
    """Encode image file to base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def decode_video(video_b64: str, output_path: str):
    """Decode base64 video and save to file"""
    video_data = base64.b64decode(video_b64)
    with open(output_path, "wb") as f:
        f.write(video_data)
    print(f"💾 Saved video: {output_path} ({len(video_data)} bytes)")


def send_generate_request(endpoint_url: str, image_path: str, output_path: str, **params):
    """Send generation request to endpoint"""
    print(f"📤 Sending request to {endpoint_url}")
    print(f"🖼️  Input image: {image_path}")
    
    # Encode image
    image_b64 = encode_image(image_path)
    print(f"📦 Image encoded: {len(image_b64)} chars")
    
    # Build payload
    payload = {
        "input": {
            "image_base64": image_b64,
            **params
        }
    }
    
    # Send request
    print("⏳ Waiting for response...")
    response = requests.post(endpoint_url, json=payload, timeout=900)
    response.raise_for_status()
    
    result = response.json()
    
    # Check status
    status = result.get("status")
    if status == "completed":
        print("✅ Generation successful!")
        
        # Save video
        video_b64 = result.get("video_base64")
        if video_b64:
            decode_video(video_b64, output_path)
        else:
            print("⚠️  No video_base64 in response")
        
        # Show metadata
        print(f"🎬 Seed: {result.get('seed')}")
        print(f"🎬 FPS: {result.get('fps')}")
        print(f"🎬 Frames: {result.get('frames')}")
        print(f"🎬 Duration: {result.get('duration_sec')}s")
        
    elif status == "failed":
        print(f"❌ Generation failed: {result.get('error_message')}")
        print(f"   Error code: {result.get('error_code')}")
        
        # Show logs if available
        logs = result.get("logs_tail")
        if logs:
            print("\n📋 Logs tail:")
            print(logs)
    else:
        print("⚠️  Unknown status: {status}")
        print(json.dumps(result, indent=2))
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Test Tenexa video generation")
    parser.add_argument("endpoint_url", help="RunPod endpoint URL")
    parser.add_argument("--image", default="example_image.png", help="Input image path")
    parser.add_argument("--output", default="output.mp4", help="Output video path")
    parser.add_argument("--seed", type=int, help="Random seed")
    parser.add_argument("--steps", type=int, default=10, help="Sampling steps")
    parser.add_argument("--cfg", type=float, default=2.0, help="CFG scale")
    parser.add_argument("--frames", type=int, default=81, help="Number of frames")
    parser.add_argument("--workflow", choices=["wan22_i2v", "flf2v"], default="wan22_i2v", help="Workflow type")
    
    args = parser.parse_args()
    
    # Check image exists
    if not os.path.exists(args.image):
        print(f"❌ Image not found: {args.image}")
        sys.exit(1)
    
    # Build params
    params = {
        "steps": args.steps,
        "cfg": args.cfg,
        "frames": args.frames,
        "workflow": args.workflow
    }
    
    if args.seed:
        params["seed"] = args.seed
    
    # Send request
    try:
        result = send_generate_request(
            args.endpoint_url,
            args.image,
            args.output,
            **params
        )
        
        if result.get("status") == "completed":
            print("\n✅ Test PASSED")
            sys.exit(0)
        else:
            print("\n❌ Test FAILED")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
