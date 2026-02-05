#!/usr/bin/env python3
"""
Diagnostic script for Tenexa RunPod endpoint
Tests diagnose mode and prints comprehensive system status
"""

import sys
import json
import argparse

try:
    import requests
except ImportError:
    print("❌ requests not installed. Run: pip install requests")
    sys.exit(1)


def print_section(title: str):
    """Print section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def send_diagnose_request(endpoint_url: str):
    """Send diagnose request to endpoint"""
    print(f"📤 Sending diagnose request to {endpoint_url}")
    
    payload = {
        "input": {
            "diagnose": True
        }
    }
    
    print("⏳ Waiting for response...")
    response = requests.post(endpoint_url, json=payload, timeout=60)
    response.raise_for_status()
    
    return response.json()


def print_diagnostics(result: dict):
    """Pretty print diagnostic results"""
    
    print_section("System Status")
    print(f"Status: {result.get('status', 'unknown')}")
    print(f"Handler Version: {result.get('handler_version', 'unknown')}")
    print(f"ComfyUI Reachable: {'✅ YES' if result.get('comfyui_reachable') else '❌ NO'}")
    print(f"Volume Mounted: {'✅ YES' if result.get('volume_mounted') else '❌ NO'}")
    
    # Disk usage
    disk = result.get('disk_usage', {})
    if disk:
        print_section("Disk Usage")
        print(f"Total: {disk.get('total_gb', 0)} GB")
        print(f"Used: {disk.get('used_gb', 0)} GB")
        print(f"Free: {disk.get('free_gb', 0)} GB")
    
    # Paths
    paths = result.get('paths', {})
    if paths:
        print_section("Paths")
        for key, value in paths.items():
            print(f"{key}: {value}")
    
    # Models
    models = result.get('models', {})
    if models:
        print_section("Available Models")
        for category, files in models.items():
            if isinstance(files, list):
                print(f"\n{category}: ({len(files)} files)")
                for file in files[:10]:  # Show first 10
                    print(f"  - {file}")
                if len(files) > 10:
                    print(f"  ... and {len(files) - 10} more")
            else:
                print(f"{category}: {files}")
    
    # Node check
    node_check = result.get('node_check', {})
    if node_check:
        print_section("ComfyUI Nodes")
        if node_check.get('success'):
            print(f"Total nodes available: {node_check.get('total_nodes', 0)}")
            
            available = node_check.get('required_available', [])
            missing = node_check.get('required_missing', [])
            
            if available:
                print(f"\n✅ Required nodes available:")
                for node in available:
                    print(f"  - {node}")
            
            if missing:
                print(f"\n❌ Required nodes missing:")
                for node in missing:
                    print(f"  - {node}")
        else:
            print(f"❌ Node check failed: {node_check.get('error')}")
    
    # Workflow checks
    workflow_checks = result.get('workflow_checks', {})
    if workflow_checks:
        print_section("Workflow Checks")
        for workflow_name, check in workflow_checks.items():
            print(f"\n{workflow_name}:")
            if check.get('exists'):
                print(f"  ✅ File exists")
                if 'nodes' in check:
                    print(f"  📊 Nodes: {check['nodes']}")
                
                missing = check.get('missing_models', {})
                if missing:
                    has_missing = False
                    for category, items in missing.items():
                        if items:
                            has_missing = True
                            print(f"  ❌ Missing {category}:")
                            for item in items:
                                print(f"     - {item}")
                    
                    if not has_missing:
                        print(f"  ✅ All requirements satisfied")
                
                if 'error' in check:
                    print(f"  ❌ Error: {check['error']}")
            else:
                print(f"  ❌ File not found")
    
    # Errors
    if 'error' in result:
        print_section("Errors")
        print(f"❌ {result['error']}")
        
        if 'logs_tail' in result:
            print("\n📋 ComfyUI logs (last 30 lines):")
            logs = result['logs_tail']
            log_lines = logs.split('\n')
            for line in log_lines[-30:]:
                if line.strip():
                    print(f"  {line}")


def send_test_request(endpoint_url: str):
    """Send test/health request"""
    print(f"📤 Sending test request to {endpoint_url}")
    
    payload = {
        "input": {
            "test": True
        }
    }
    
    response = requests.post(endpoint_url, json=payload, timeout=10)
    response.raise_for_status()
    
    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Diagnose Tenexa endpoint")
    parser.add_argument("endpoint_url", help="RunPod endpoint URL")
    parser.add_argument("--test", action="store_true", help="Run quick test instead of full diagnose")
    
    args = parser.parse_args()
    
    try:
        if args.test:
            print_section("Quick Test Mode")
            result = send_test_request(args.endpoint_url)
            print(json.dumps(result, indent=2))
            
            if result.get('ok') and result.get('comfyui_up'):
                print("\n✅ Test PASSED")
                sys.exit(0)
            else:
                print("\n❌ Test FAILED")
                sys.exit(1)
        else:
            print_section("Full Diagnostic Mode")
            result = send_diagnose_request(args.endpoint_url)
            print_diagnostics(result)
            
            # Check for critical issues
            issues = []
            if not result.get('comfyui_reachable'):
                issues.append("ComfyUI not reachable")
            
            workflow_checks = result.get('workflow_checks', {})
            for wf_name, check in workflow_checks.items():
                if check.get('missing_models'):
                    for category, items in check['missing_models'].items():
                        if items:
                            issues.append(f"Missing {category} in {wf_name}")
            
            if issues:
                print_section("Critical Issues Found")
                for issue in issues:
                    print(f"❌ {issue}")
                print("\n⚠️  Diagnose found issues")
                sys.exit(1)
            else:
                print_section("Summary")
                print("✅ All checks passed!")
                sys.exit(0)
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
