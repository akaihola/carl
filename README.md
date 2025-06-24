# Pipecat Voice Assistant

A real-time voice assistant built with Pipecat that provides live transcription and AI-powered insights using AssemblyAI for speech-to-text and Perplexity for intelligent analysis.

## Features

- 🎤 **Real-time Speech Recognition**: Live transcription using AssemblyAI's streaming STT
- 🧠 **AI-Powered Insights**: Intelligent conversation analysis with Perplexity's web-enabled LLM
- 🌐 **WebRTC Audio Streaming**: Low-latency audio transmission from browser to backend
- 📱 **Responsive Web Interface**: Clean, modern UI that works on desktop and mobile
- 🔒 **Secure API Management**: API keys managed securely on the backend
- ⚡ **No CORS Issues**: Backend proxy eliminates browser API restrictions

## Architecture

This implementation migrates from a CORS-blocked frontend approach to a robust Pipecat-based backend architecture:

- **Frontend**: WebRTC client for audio capture and real-time display
- **Backend**: Pipecat pipeline with FastAPI WebSocket server
- **Audio Pipeline**: Browser → WebRTC → Pipecat → AssemblyAI → Perplexity → Response

See [`pipecat-voice-assistant-architecture.md`](pipecat-voice-assistant-architecture.md) for detailed technical specifications.

## Prerequisites

- Python 3.9 or higher
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for Python package management
- AssemblyAI API key
- Perplexity API key

## Quick Start

### 1. Get API Keys

**AssemblyAI**: Sign up at [AssemblyAI](https://www.assemblyai.com/) and get your API key from the dashboard.

**Perplexity**: Sign up at [Perplexity](https://www.perplexity.ai/) and get your API key.

### 2. Configure Environment

Create a `.env` file with your API keys:

```bash
# API Keys
ASSEMBLYAI_API_KEY=your_assemblyai_api_key_here
PERPLEXITY_API_KEY=your_perplexity_api_key_here

# Server Configuration (optional)
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

### 3. Start the Application

Run the startup script:

```bash
python start.py
```

This will:
- Check prerequisites
- Create a virtual environment using `uv`
- Install dependencies
- Start the Pipecat backend server

### 4. Use the Voice Assistant

1. Open your browser to `http://localhost:8000`
2. Click "Start Voice Assistant"
3. Allow microphone access when prompted
4. Start speaking - you'll see:
   - Live transcription in the bottom ticker
   - AI insights in the main panel

## Manual Setup

If you prefer manual setup:

```bash
# Create virtual environment
uv venv

# Install dependencies
uv pip install -r requirements.txt

# Start the server
uv run python backend.py
```

## Project Structure

```
├── backend.py              # Pipecat FastAPI server
├── webrtc-script.js        # WebRTC frontend client
├── index.html              # Web interface
├── style.css               # UI styling
├── start.py                # Setup and startup script
├── requirements.txt        # Python dependencies
├── .env                    # Environment configuration
├── README.md               # This file
└── pipecat-voice-assistant-architecture.md  # Technical architecture
```

## How It Works

### Audio Pipeline

1. **Browser Audio Capture**: WebRTC captures microphone audio with optimal settings
2. **WebSocket Connection**: Establishes connection to Pipecat backend
3. **Audio Streaming**: Real-time audio transmission via WebRTC
4. **Speech Processing**: Pipecat pipeline processes audio through:
   - Voice Activity Detection (Silero VAD)
   - Speech-to-Text (AssemblyAI)
   - Transcription Aggregation
   - LLM Analysis (Perplexity)
5. **Real-time Display**: Results streamed back to frontend via WebSocket

### Key Components

- **ConversationManager**: Tracks conversation state and context
- **TranscriptionAggregator**: Processes STT results and triggers LLM insights
- **SmallWebRTCTransport**: Handles P2P audio streaming
- **WebSocket Handler**: Manages client connections and message routing

## Configuration

### Environment Variables

- `ASSEMBLYAI_API_KEY`: Your AssemblyAI API key (required)
- `PERPLEXITY_API_KEY`: Your Perplexity API key (required)
- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 8000)
- `DEBUG`: Enable debug mode (default: true)

### Audio Settings

The frontend is configured for optimal speech recognition:
- Sample Rate: 16kHz
- Channels: Mono
- Echo Cancellation: Enabled
- Noise Suppression: Enabled
- Auto Gain Control: Enabled

## Troubleshooting

### Common Issues

**"uv not found"**: Install uv following the [official guide](https://docs.astral.sh/uv/getting-started/installation/)

**"Missing API keys"**: Ensure your `.env` file has valid API keys without placeholder text

**"WebRTC connection failed"**: Check that the server is running and accessible at the configured port

**"No audio detected"**: Verify microphone permissions and that your browser supports WebRTC

### Debug Mode

Enable debug logging by setting `DEBUG=true` in your `.env` file. This provides detailed information about:
- WebSocket connections
- Audio pipeline processing
- API interactions
- Error details

## Development

### Adding New Features

The modular Pipecat architecture makes it easy to extend:

1. **New STT Service**: Replace `AssemblyAISTTService` in the pipeline
2. **Different LLM**: Swap `PerplexityLLMService` for another provider
3. **Additional Processing**: Add new frame processors to the pipeline
4. **Enhanced UI**: Modify the frontend components

### Testing

Start the development server with auto-reload:

```bash
uv run uvicorn backend:app --reload --host 0.0.0.0 --port 8000
```

## License

This project is open source. See the individual service providers (AssemblyAI, Perplexity) for their respective terms of service.

## Contributing

Contributions are welcome! Please ensure:
- Code follows the established patterns
- New features include appropriate error handling
- Documentation is updated for significant changes