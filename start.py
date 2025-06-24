#!/usr/bin/env python3
"""
Pipecat Voice Assistant Startup Script

This script helps users install dependencies and start the voice assistant.
"""

import subprocess
import sys
from pathlib import Path


def check_uv_installed():
    """Check if uv is installed"""
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
        print("✅ uv is installed")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ uv is not installed")
        print(
            "Please install uv: https://docs.astral.sh/uv/getting-started/installation/"
        )
        return False


def check_python_version():
    """Check if Python version is 3.9 or higher"""
    if sys.version_info < (3, 9):
        print("❌ Python 3.9 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version.split()[0]}")
    return True


def check_env_file():
    """Check if .env file exists and has required keys"""
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ .env file not found")
        print("Please create a .env file with your API keys:")
        print("  ASSEMBLYAI_API_KEY=your_key_here")
        print("  OPENROUTER_API_KEY=your_key_here")
        return False

    # Read and check for required keys
    env_content = env_path.read_text()
    required_keys = ["ASSEMBLYAI_API_KEY", "OPENROUTER_API_KEY"]
    missing_keys: list[str] = []

    for key in required_keys:
        if f"{key}=" not in env_content or f"{key}=your_" in env_content:
            missing_keys.append(key)

    if missing_keys:
        print(f"❌ Missing or invalid API keys in .env: {', '.join(missing_keys)}")
        print("Please update your .env file with valid API keys")
        return False

    print("✅ .env file configured")
    return True


def setup_virtual_environment():
    """Create virtual environment and install dependencies using uv"""
    venv_path = Path(".venv")

    if not venv_path.exists():
        print("📦 Creating virtual environment...")
        try:
            subprocess.run(["uv", "venv"], check=True, capture_output=True)
            print("✅ Virtual environment created")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to create virtual environment: {e}")
            return False
    else:
        print("✅ Virtual environment exists")

    print("📦 Installing dependencies...")
    try:
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--requirements",
                "requirements.txt",
                "--overrides",
                "constraints.txt",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        print("Error output:", e.stderr)
        return False


def start_server():
    """Start the Pipecat backend server using uv"""
    print("🚀 Starting Pipecat Voice Assistant...")
    print("Server will be available at: http://localhost:8000")
    print("Press Ctrl+C to stop the server")
    print("-" * 50)

    try:
        subprocess.run(["uv", "run", "python", "backend.py"], check=True)
    except KeyboardInterrupt:
        print("\n👋 Server stopped")
    except subprocess.CalledProcessError as e:
        print(f"❌ Server failed to start: {e}")
        return False

    return True


def main():
    """Main startup routine"""
    print("🎤 Pipecat Voice Assistant Setup")
    print("=" * 40)

    # Check prerequisites
    if not check_uv_installed():
        sys.exit(1)

    if not check_python_version():
        sys.exit(1)

    if not check_env_file():
        sys.exit(1)

    # Setup environment and install dependencies
    if not setup_virtual_environment():
        sys.exit(1)

    # Start server
    start_server()


if __name__ == "__main__":
    main()
