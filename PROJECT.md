# Carl Project Documentation

Carl is a real-time conversation AI assistant that listens through a device microphone, transcribes speech to text, and provides intelligent contextual responses using Gemini AI models.

## Overview

Carl is a web-based application designed for personal use that:
- Listens to conversation via microphone input
- Provides real-time speech transcription in "subtitle" style
- Generates contextual AI responses when appropriate
- Displays responses as large, readable text banners
- Implements confidence-based fact verification with real-time grounding

## Architecture

### Frontend Stack
- **HTML/CSS/JavaScript**: Modern browser APIs (Firefox 145+, Chromium 143+)
- **WebSocket**: Real-time bidirectional communication with Gemini Live API
- **Web Audio API**: Audio capture and processing
- **Server-Sent Events (SSE)**: Streaming response handling for REST API calls

### AI Models
- **Primary Model**: `models/gemini-2.5-flash-native-audio-preview-12-2025`
  - Real-time audio transcription and response generation
  - Communicates via WebSocket

- **Verification Model**: `models/gemini-2.5-pro`
  - Fact verification and grounding
  - Communicates via REST API with streaming
  - Tools: Google Search, Code Execution

### Key Infrastructure
- **Gemini API**: Google AI for Developers (generativelanguage.googleapis.com)
- **Authentication**: API key-based (stored in localStorage)
- **Voice Activity Detection**: Silero VAD model for speech detection

## Core Features

### 1. Real-Time Audio Transcription
- WebSocket connection to Gemini Live API
- 16kHz mono PCM audio streaming
- Binary frame transmission
- Progressive text rendering as transcription arrives

### 2. Confidence-Based Verification Protocol
- Primary model assesses confidence in factual claims (99%+ threshold)
- Low-confidence responses trigger structured format: `§{q, a, c}`
  - `q`: Factual question needing verification
  - `a`: Model's brief answer
  - `c`: Confidence level (0-100)
- Automatic routing to verification model when triggered

### 3. Verification with Grounding
- Verification model uses tools to ground answers:
  - **Google Search**: Real-time information retrieval
  - **Code Execution**: Mathematical calculations and data processing
- Grounding metadata logged to console
- Visual indicator: Teal border for grounded responses vs. green for regular verified

### 4. Voice Activity Detection (VAD)
- Algorithm: RMS volume analysis from AnalyserNode
- Configuration:
  - Threshold: 0.05 (minimum RMS to consider as speech)
  - Smoothing: 0.9 (slower release, prevents chatter)
  - Hold time: 300ms (continue sending after speech stops)
  - Silence interval: 1000ms (send periodic silence frames)
  - Silence frame duration: 100ms (duration of each silence frame)
- Reduces unnecessary audio transmission
- **Periodic silence frames**: During detected silence, sends PCM frames with zeros every 1 second to keep Gemini Live API engaged and responsive

### 5. Responsive Font Sizing
- Binary search algorithm to find optimal font size
- Fits response text within viewport constraints
- Updates during streaming with smooth CSS transitions
- Prevents text overflow on any screen size

### 6. Location Context Injection
- Automatically prepends current context to system prompt on connection
- Uses browser Geolocation API for coordinates
- Reverse geocodes via OpenStreetMap Nominatim API
- Context includes:
  - Local timestamp (weekday, date, time)
  - Timezone
  - Latitude/Longitude
  - Country, State/Province, City
  - Full address
- Cached after first retrieval (5-minute validity)
- Graceful fallback if location unavailable

## Project Structure

```
carl/
├── index.html              # HTML structure + system prompts
├── styles.css              # CSS styling and layout (150+ lines)
├── AGENTS.md               # Project development guidelines
├── README.md               # Brief project description
├── PROJECT.md              # This file
├── .env                    # API keys (not committed)
├── silero_vad.onnx         # Silero voice activity detection model
├── script.js               # Deprecated: original monolithic script
├── js/                     # Modular application (1173 lines total)
│   ├── helpers.js          # Shared utilities (audio conversion, formatting)
│   ├── config.js           # Application constants and configuration
│   ├── state.js            # Centralized state management
│   ├── ui.js               # DOM manipulation and UI helpers
│   ├── location.js         # Geolocation and context acquisition
│   ├── audio.js            # Audio I/O and Voice Activity Detection
│   ├── response.js         # Response rendering and verification
│   ├── connection.js       # WebSocket connection management
│   └── main.js             # Entry point and initialization
└── .claude/                # Claude Code configuration
    └── settings.local.json
```

## File Descriptions

### index.html
- Minimal HTML structure with single title and toolbar
- Menu system for settings
- System prompt configuration area (editable textarea)
- System instructions for both primary and verification models
- API key input and management controls
- Loads modular JavaScript files in dependency order

### Modular JavaScript Architecture (`js/` directory)

The application has been refactored from a monolithic `script.js` into a modular architecture using a global `Carl` namespace. This design works with `file:///` URLs (avoiding ES modules' CORS limitations).

#### `config.js` (42 lines)
- **Purpose**: Centralized configuration constants
- **Exports**: `Carl.config`
- **Key Constants**:
  - API endpoints (MODEL, VERIFICATION_MODEL, WS_URL, REST_URL)
  - Feature markers (STRUCTURED_RESPONSE_MARKER = '§')
  - VAD thresholds (VAD_THRESHOLD, VAD_SMOOTHING, VAD_HOLD_TIME)
  - Silence frame sending (SEND_SILENCE_INTERVAL, SILENCE_FRAME_DURATION_MS)
  - Audio settings (sample rates, buffer sizes)
  - Logging intervals

#### `state.js` (85 lines)
- **Purpose**: Centralized state management
- **Exports**: `Carl.state`
- **State Categories**:
  - WebSocket and audio contexts
  - API authentication
  - Response rendering
  - Structured response parsing
  - Audio playback queue
  - Voice Activity Detection tracking (including silence send timing)
  - Location context cache
- **Helper Methods**:
  - `resetStructuredState()`, `resetVadState()`, `resetSilenceTracking()`
  - `clearAudioQueue()`, `isConnected()`

#### `helpers.js` (70 lines)
- **Purpose**: Shared utility functions (de-duplicated)
- **Exports**: `Carl.helpers`
- **Functions**:
  - `formatTimestamp()` - Consolidated from two locations
  - `resampleTo16kHz()` - Audio resampling
  - `floatTo16BitPCM()`, `arrayBufferToBase64()`, `base64ToArrayBuffer()` - Audio encoding

#### `ui.js` (97 lines)
- **Purpose**: DOM manipulation and UI state
- **Exports**: `Carl.ui`
- **Responsibilities**:
  - Element caching (menu, controls, buttons, inputs)
  - Menu toggling and backdrop handling
  - API key UI state management
  - Scroll management with programmatic scroll tracking
  - Connection button state

#### `location.js` (70 lines)
- **Purpose**: Geolocation context acquisition
- **Exports**: `Carl.location`
- **Async Function**: `getContext()` - Retrieves location with reverse geocoding
- **Features**:
  - Geolocation API integration
  - OpenStreetMap Nominatim reverse geocoding
  - Timezone detection
  - Fallback handling for permission denial

#### `audio.js` (247 lines)
- **Purpose**: Audio input/output and Voice Activity Detection
- **Exports**: `Carl.audio`
- **Functions**:
  - `initInput()` - Microphone setup and audio processing pipeline
  - `detectVoiceActivity()` - RMS-based VAD with smoothing and periodic silence sending
  - `generateSilenceFrame()` - Creates zero-filled PCM audio frames
  - `sendSilenceFrame()` - Sends silence frames to keep API engaged during pauses
  - `sendAudioMessage()` - WebSocket audio transmission
  - `queueForPlayback()`, `playNextChunk()` - Audio output queue
  - `cleanup()` - Resource cleanup on disconnect

#### `response.js` (312 lines)
- **Purpose**: Response rendering and structured response handling
- **Exports**: `Carl.response`
- **Functions**:
  - `findOptimalFontSize()` - Binary search for responsive sizing (consolidated)
  - `startNew()`, `updateText()`, `finalize()` - Response lifecycle
  - `parseStructured()` - JSON parsing from § marker format
  - `processTranscription()` - Handles structured response detection
  - `handleCompleteStructured()` - Verification trigger logic
  - `verifyWithGeminiPro()` - REST API call to verification model

#### `connection.js` (211 lines)
- **Purpose**: WebSocket connection lifecycle
- **Exports**: `Carl.connection`
- **Functions**:
  - `toggle()` - Connection state toggling
  - `connect()` - WebSocket setup with handlers (onopen, onmessage, onerror, onclose)
  - `disconnect()` - Cleanup and resource release
  - `sendTextMessage()` - Text message transmission

#### `main.js` (90 lines)
- **Purpose**: Entry point and initialization
- **Exports**: `Carl.init()`, `Carl.apiKey`
- **Responsibilities**:
  - Global event handler registration (DOMContentLoaded, scroll, keydown)
  - UI initialization
  - API key management (submit, clear, localStorage)
  - Global function bindings for HTML onclick handlers

#### `script.js` (991 lines - Deprecated)
- Original monolithic implementation kept for reference
- No longer loaded by index.html
- Can be removed once modular version is stable

### styles.css
**Key Classes:**
- `.toolbar`: Sticky header with connection and menu buttons
- `.menu-content`: Settings panel (sidebar)
- `.response`: Base response styling
- `.response.verified`: Verified response (green left border)
- `.response.verified.grounded`: Grounded response with tools (teal left border)
- `.response.measuring`: Hidden element for font size calculation
- `.controls`: API key input area

**Design Approach:**
- CSS Grid/Flexbox for layout
- CSS custom properties for responsive sizing (clamp)
- CSS transitions for smooth font size changes
- Modern CSS features without legacy support

## Data Flow

### Audio Processing Pipeline
```
Microphone
    ↓
Web Audio API (AnalyserNode)
    ↓
VAD Check (RMS volume analysis)
    ↓
Binary frame encoding
    ↓
WebSocket → Gemini Live API
    ↓
Streaming response (text)
    ↓
Display in UI + Font size calculation
```

### Verification Pipeline
```
Primary Model Response
    ↓
Confidence assessment (§ marker detected)
    ↓
Parse structured JSON {q, a, c}
    ↓
Extract factual question
    ↓
REST API → Verification Model (gemini-2.5-pro)
    ↓
Tool execution (Google Search, Code Execution)
    ↓
Grounding metadata extraction
    ↓
Display with visual indicator (teal border)
```

## API Integration

### Gemini Live API (WebSocket)
- **URL**: `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent`
- **Authentication**: API key (query parameter)
- **Protocol**: Binary frames for audio, text/JSON for responses
- **Purpose**: Real-time audio transcription and response generation

### Gemini REST API (Server-Sent Events)
- **URL**: `https://generativelanguage.googleapis.com/v1beta/{model}:streamGenerateContent`
- **Authentication**: API key (query parameter)
- **Request Body**:
  - `contents`: User message
  - `generationConfig`: Output constraints (maxOutputTokens)
  - `systemInstruction`: Model behavior guidance
  - `tools`: Available tools (googleSearch, codeExecution)
- **Response**: Server-Sent Events stream with JSON chunks
- **Purpose**: Verification and grounding with tool support

## Configuration

### System Prompts
Both system prompts are editable in the UI settings panel:

**Primary Model Instructions:**
- Contribute concisely only when facts are needed
- Wait for at least 2 turns before responding to factual gaps
- Use confidence protocol: output structured JSON for low-confidence claims

**Verification Model Instructions:**
- Use Google Search for current/real-world information
- Use Code Execution for calculations
- Ground answers in tool results
- Cite sources when applicable

### API Key Management
- Stored in localStorage (key: `gemini_api_key`)
- Submitted through UI input field
- Used for both WebSocket and REST API authentication
- Can be cleared through UI controls

## Performance Considerations

### Audio Streaming
- 16kHz mono PCM reduces bandwidth (~256 KB/s vs. 1.4 MB/s for 48kHz stereo)
- VAD reduces unnecessary transmission (only send during speech)
- WebSocket binary frames for efficient encoding

### Response Rendering
- Progressive text rendering (appends as received)
- Font size calculation during streaming (not blocking)
- Smooth CSS transitions prevent layout jank
- Auto-scrolling respects user scroll position

### Tool Execution
- Google Search and Code Execution happen within single API call
- Model automatically determines which tools are needed
- No additional latency for tool availability (always configured)

## Development Notes

### Browser Support
- Target: Firefox 145+, Chromium 143+ (November 2025 and later)
- No legacy support or polyfills needed
- Leverages cutting-edge CSS and browser APIs
- Works with `file:///` URLs (no CORS issues with script loading)

### Code Philosophy
- Minimal dependencies (no frameworks)
- Pure JavaScript with modern ES2024+ features
- CSS-first for styling and interactions
- Self-documenting code without excessive comments
- Semantic HTML and native browser APIs
- Single responsibility per module
- De-duplicated shared logic in helpers

### Modular Architecture Benefits
- **Single Responsibility**: Each module handles one domain (audio, UI, response, connection, etc.)
- **De-duplication**: Shared logic consolidated (timestamp formatting, font size calculation, brace counting)
- **Maintainability**: Easier to locate and modify functionality
- **Testability**: Individual modules can be tested independently
- **Scalability**: New features can be added as new modules or extensions
- **file:/// Compatibility**: No ES modules CORS issues when opening locally

### Error Handling
- Graceful fallbacks for API failures
- Console logging for debugging
- User-friendly error messages in UI
- Verification failures display inline error text

## Recent Enhancements

### Periodic Silence Frame Sending (Latest)
- Sends zero-filled PCM audio frames every 1 second during detected silence
- Keeps Gemini Live API engaged and responsive during user pauses
- Configurable via `SEND_SILENCE_INTERVAL` and `SILENCE_FRAME_DURATION_MS`
- Uses same audio format as regular speech frames (16-bit PCM at 16kHz)
- Seamlessly integrates with existing VAD system

### Confidence-Based Verification
- Structured response format allows low-confidence detection
- Automatic routing to verification model
- No user action required

### Grounding with Tools
- Google Search integration for real-time information
- Code Execution for calculations and transformations
- Automatic tool selection by model
- Grounding metadata logging and visual indicators

### Font Sizing Improvements
- Smooth CSS transitions during size changes
- Responsive sizing with clamp()
- Prevents text overflow on all screens

## Troubleshooting

### Audio Not Working
1. Check microphone permissions
2. Verify API key is valid
3. Check browser console for WebSocket errors
4. Ensure browser supports Web Audio API

### Verification Not Triggering
1. Check that response contains confidence assessment
2. Verify structured response format is correct (§{...})
3. Check API key for verification model
4. Review confidence threshold (99%+)

### Font Size Issues
1. Clear localStorage and reload
2. Check styles.css for transition settings
3. Verify viewport meta tag in index.html

## Future Considerations

- Audio output (text-to-speech)
- User conversation history
- Custom model selection
- Advanced filtering and response preferences
- Multi-language support
- Conversation export/sharing
