# Pipecat Voice Assistant

A real-time voice assistant built with Pipecat that provides live transcription and AI-powered insights using AssemblyAI for speech-to-text and Perplexity for intelligent analysis.

## Features

- 🎤 **Real-time Speech Recognition**: Live transcription using AssemblyAI.
- 🧠 **AI-Powered Insights**: Intelligent conversation analysis using an LLM (via OpenRouter).
- 🌐 **WebRTC Audio Streaming**: Low-latency audio from browser to backend.
- 📱 **Responsive Web Interface**: Clean UI for desktop and mobile.
- 🔒 **Secure API Management**: API keys are managed on the backend.
- ⚡ **No CORS Issues**: Backend-centric design avoids browser API restrictions.

## Architecture

This project uses a modern, refactored backend architecture:

- **Frontend**: A static web page using WebRTC for audio capture and a WebSocket for communication.
- **Backend**: A `server.py` using FastAPI to handle WebRTC signaling and manage `bot.py` subprocesses. Each voice session runs in an isolated `bot.py` process, which contains the Pipecat pipeline.
- **Pipecat Pipeline**: `bot.py` defines the pipeline: WebRTC → VAD → AssemblyAI (STT) → OpenRouter (LLM) → WebRTC.

See [`pipecat-voice-assistant-architecture.md`](pipecat-voice-assistant-architecture.md) for more details.

## Prerequisites

- Python 3.9+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- AssemblyAI API key
- OpenRouter API key

## Quick Start

### 1. Get API Keys

- **AssemblyAI**: Get your key from the [AssemblyAI dashboard](https://www.assemblyai.com/).
- **OpenRouter**: Get your key from the [OpenRouter dashboard](https://openrouter.ai/).

### 2. Configure Environment

Create a `.env` file with your API keys. A `start.py` script can help create this.

```bash
# .env
ASSEMBLYAI_API_KEY="your_assemblyai_api_key"
OPENROUTER_API_KEY="your_openrouter_api_key"
```

### 3. Start the Application

The `start.py` script automates setup and execution:

```bash
python start.py
```

This script checks prerequisites, creates a virtual environment, installs dependencies, and starts the server.

### 4. Use the Voice Assistant

1. Open your browser to `http://localhost:8000`.
2. Click "Start Voice Assistant".
3. Grant microphone access.
4. Start speaking. You will see live transcription and AI insights.

## Manual Setup

```bash
# Create virtual environment
uv venv

# Install dependencies
uv pip install -r requirements.txt

# Start the server
uv run python server.py
```

## Project Structure

```
├── server.py           # FastAPI server for signaling and process management
├── bot.py              # Pipecat pipeline logic for each voice session
├── config.py           # Configuration management
├── start.py            # Setup and startup script
├── static/
│   ├── index.html      # Main web interface
│   ├── webrtc-script.js# Frontend WebRTC and WebSocket logic
│   └── style.css       # UI styling
├── requirements.txt    # Python dependencies
├── .env                # Environment configuration (gitignored)
└── README.md           # This file
```

## How It Works

1.  **Audio Capture**: The browser captures microphone audio using WebRTC.
2.  **Signaling**: The browser sends a WebRTC offer to the FastAPI `server.py`.
3.  **Bot Spawning**: `server.py` spawns a new `bot.py` process to handle the voice session.
4.  **Pipeline Processing**: The `bot.py` instance runs the Pipecat pipeline:
    -   **WebRTCTransport**: Manages the WebRTC connection.
    -   **SileroVADAnalyzer**: Detects voice activity.
    -   **AssemblyAISTTService**: Transcribes audio to text.
    -   **OpenAIContextAggregator**: Manages conversation history.
    -   **OpenAILLMService**: Sends text to an LLM via OpenRouter for analysis.
5.  **Real-time Display**: Responses are sent back to the browser via the WebRTC data channel.

## Development

Start the development server with auto-reload:

```bash
uv run uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

## Troubleshooting

- **"uv not found"**: Install `uv` from the [official guide](https://docs.astral.sh/uv/getting-started/installation/).
- **"Missing API keys"**: Ensure your `.env` file contains valid API keys.
- **"WebRTC connection failed"**: Check that the server is running and accessible.
- **"No audio detected"**: Verify microphone permissions in your browser.

## Contributing

Contributions are welcome! Please ensure:
- Code follows the established patterns
- New features include appropriate error handling
- Documentation is updated for significant changes