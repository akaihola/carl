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
- Reduces unnecessary audio transmission

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
├── script.js               # Main application logic (894 lines)
├── styles.css              # CSS styling and layout (150+ lines)
├── AGENTS.md               # Project development guidelines
├── README.md               # Brief project description
├── PROJECT.md              # This file
├── .env                    # API keys (not committed)
├── silero_vad.onnx         # Silero voice activity detection model
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

### script.js
**Key Functions:**
- `toggleConnection()`: WebSocket connection management
- `connect()`: Establishes WebSocket connection with location context
- `getLocationContext()`: Retrieves and caches geolocation + reverse geocoding
- `sendAudioFrame()`: Binary frame transmission to WebSocket
- `processTranscription()`: Handles structured response detection and parsing
- `verifyWithGeminiPro()`: REST API call to verification model with tool support
- `findOptimalFontSize()`: Binary search for responsive font sizing
- `handleCompleteStructuredResponse()`: Processes confidence-based verification trigger

**Global State:**
- `ws`: WebSocket connection
- `audioContext`, `mediaStream`, `audioProcessor`: Web Audio API objects
- `currentResponseEl`, `currentResponseText`: Current response display state
- `userHasScrolledUp`: Scroll position tracking
- `pendingStructuredResponse`, `isParsingStructured`: Structured response handling
- `analyser`, `smoothedVolume`: Voice activity detection state
- `outputAudioContext`, `audioQueue`: Audio playback management
- `cachedLocationContext`: Cached location context string

**Configuration Constants:**
```javascript
const MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
const VERIFICATION_MODEL = "models/gemini-2.5-pro"
const HOST = "generativelanguage.googleapis.com"
const WS_URL = `wss://${HOST}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent`
const GEMINI_REST_URL = `https://${HOST}/v1beta`
const STRUCTURED_RESPONSE_MARKER = '§'
const VAD_THRESHOLD = 0.05
const VAD_SMOOTHING = 0.9
const VAD_HOLD_TIME = 300
```

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

### Code Philosophy
- Minimal dependencies (no frameworks)
- Pure JavaScript with modern ES2024+ features
- CSS-first for styling and interactions
- Self-documenting code without excessive comments
- Semantic HTML and native browser APIs

### Error Handling
- Graceful fallbacks for API failures
- Console logging for debugging
- User-friendly error messages in UI
- Verification failures display inline error text

## Recent Enhancements

### Confidence-Based Verification (Latest)
- Structured response format allows low-confidence detection
- Automatic routing to verification model
- No user action required

### Grounding with Tools (Latest)
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
