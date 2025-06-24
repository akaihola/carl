"""  """#!/usr/bin/env python3
"""
Test script to verify Pipecat Voice Assistant setup
"""

import subprocess
import sys
from pathlib import Path


def test_uv_available():
    """Test if uv is available"""
    try:
        result = subprocess.run(
            ["uv", "--version"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        print(f"✅ uv version: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ uv not found")
        return False


def test_env_file():
    """Test if .env file exists and has required keys"""
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ .env file missing")
        return False
    
    content = env_path.read_text()
    required_keys = ["ASSEMBLYAI_API_KEY", "OPENROUTER_API_KEY"]
    
    for key in required_keys:
        if f"{key}=" not in content:
            print(f"❌ Missing {key} in .env")
            return False
        if f"{key}=your_" in content:
            print(f"❌ {key} has placeholder value")
            return False
    
    print("✅ .env file configured correctly")
    return True


def test_dependencies():
    """Test if dependencies can be imported"""
    try:
        subprocess.run([
            "uv", "pip", "install", "-r", "requirements.txt", "-c", "constraints.txt"
        ], check=True, capture_output=True)
        print("✅ Dependencies installed")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install dependencies")
        return False


def test_import_pipecat():
    """Test if pipecat can be imported"""
    try:
        subprocess.run([
            "uv", "run", "python", "-c", "import pipecat; print('Pipecat imported successfully')"
        ], capture_output=True, text=True, check=True)
        print("✅ Pipecat imports successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Pipecat import failed: {e.stderr}")
        return False


def test_backend_syntax():
    """Test if backend.py has valid syntax"""
    try:
        subprocess.run([
            "uv", "run", "python", "-m", "py_compile", "backend.py"
        ], capture_output=True, text=True, check=True)
        print("✅ Backend syntax is valid")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Backend syntax error: {e.stderr}")
        return False


def main():
    """Run all tests"""
    print("🧪 Testing Pipecat Voice Assistant Setup")
    print("=" * 45)
    
    tests = [
        test_uv_available,
        test_env_file,
        test_dependencies,
        test_import_pipecat,
        test_backend_syntax,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Ready to start the voice assistant.")
        print("Run: python start.py")
    else:
        print("❌ Some tests failed. Please fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()