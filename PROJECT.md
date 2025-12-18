# Carl Project Documentation

Carl is a real-time conversation fact-checker that listens through a device microphone, identifies factual questions and claims, and provides verified answers using Gemini AI models.

## Overview

Carl is a web-based application designed for personal use that:
- Listens to conversation via microphone input
- Identifies questions, missing facts, and misinformation
- Silently tracks factual claims from the conversation
- Verifies facts using Google Search and Code Execution tools
- Displays only verified factual answers as large, readable text banners

## Architecture

### Frontend Stack
- **HTML/CSS/JavaScript**: Modern browser APIs (Firefox 145+, Chromium 143+)
- **WebSocket**: Real-time bidirectional communication with Gemini Live API
- **Web Audio API**: Audio capture and processing
- **Server-Sent Events (SSE)**: Streaming response handling for REST API calls

### AI Models
- **Primary Model**: `models/gemini-2.0-flash-exp`
  - Real-time audio processing with text-only output
  - Role: Fact identifier (NOT answerer)
  - Outputs structured `Qn:` / `An:` format for questions and conversation answers
  - Communicates via WebSocket

- **Verification Model**: `models/gemini-2.5-pro`
  - Fact verification and correction
  - Communicates via REST API with streaming (SSE)
  - Tools: Google Search, Code Execution
  - Responds with "CORRECT", "SKIP" (for unanswerable questions), or streams the actual fact

### Key Infrastructure
- **Gemini API**: Google AI for Developers (generativelanguage.googleapis.com)
- **Authentication**: API key-based (stored in localStorage)
- **Voice Activity Detection**: Silero VAD model for speech detection

## Core Features

### 1. Real-Time Audio Processing
- WebSocket connection to Gemini Live API
- 16kHz mono PCM audio streaming
- Binary frame transmission
- Primary model outputs text-only (no audio response)

### 2. Fact Identification Protocol
- Primary model identifies factual gaps and questions in conversation:
  - Questions (direct or indirect) - queued immediately
  - Missing information - queued for finding answers
  - Misinformation or claimed facts - queued for verification
- Output format: `Qn: [question]` for questions, `An: [answer from conversation]` for user statements
  - Example: `Q1: How many moons does Mars have?` (queued alone, model will find answer)
  - Example: `A1: Mars has two moons` (paired with Q1 if both present, or standalone)
- Questions and answers are numbered with matching prefixes (Q1/A1, Q2/A2, etc.)
- Questions are queued for verification immediately upon parsing (no answer required)
- Amended or new answers (same Q number, new A) move to head of queue for re-verification

### 3. Silent Fact Tracking
- `Qn:` and `An:` format is parsed but NOT displayed to user
- Facts stored in internal mapping: `{number: {q, a, f}}`
- FIFO verification queue maintains order of discovery
- User only sees verified facts from verification model

### 4. Verification Queue Processing (Dual-Mode)
- One verification request in flight at a time (no parallel requests)
- Queue processes in FIFO order
- Two verification modes:
  - **With Answer** (Q+A): Verification model receives question + user's answer, verifies correctness
  - **Without Answer** (Q-only): Verification model receives question alone, finds and verifies the correct answer
- Request prompt adapts based on mode:
  - With answer: `"Question: X\nUser's Answer: Y\n\nPlease verify if this answer is correct."`
  - Without answer: `"Question: X\n\nPlease find and verify the correct answer to this question."`
- Response handling:
  - First word "CORRECT": answer confirmed (only in with-answer mode), fact removed from queue
  - Otherwise: streams finding or correction to display
- Amended answers (same Q number, new A) move to head of queue for re-verification
- When answer arrives for verified Q-only fact: moves to head of queue for re-verification against user answer

### 5. Verification with Grounding
- Verification model uses tools to validate/correct facts:
  - **Google Search**: Real-time information retrieval
  - **Code Execution**: Mathematical calculations and data processing
- Grounding metadata logged to console
- Facts streamed to display as they arrive

### 6. Voice Activity Detection (VAD)
- Algorithm: RMS volume analysis from AnalyserNode
- Configuration:
  - Threshold: 0.05 (minimum RMS to consider as speech)
  - Smoothing: 0.9 (slower release, prevents chatter)
  - Hold time: 300ms (continue sending after speech stops)
  - Silence interval: 1000ms (send periodic silence frames)
  - Silence frame duration: 100ms (duration of each silence frame)
- Reduces unnecessary audio transmission
- **Periodic silence frames**: During detected silence, sends PCM frames with zeros every 1 second to keep Gemini Live API engaged and responsive

### 7. Responsive Font Sizing
- Binary search algorithm to find optimal font size
- Fits response text within viewport constraints
- Updates during streaming with smooth CSS transitions
- Prevents text overflow on any screen size

### 8. Location Context Injection
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
├── js/                     # Modular application
│   ├── helpers.js          # Shared utilities (audio conversion, formatting)
│   ├── config.js           # Application constants and configuration
│   ├── state.js            # Centralized state management
│   ├── ui.js               # DOM manipulation and UI helpers
│   ├── location.js         # Geolocation and context acquisition
│   ├── audio.js            # Audio I/O and Voice Activity Detection
│   ├── response.js         # Response rendering and verification queue
│   ├── facts.js            # Fact parsing (Qn:/An:) and queue management
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

#### `config.js`
- **Purpose**: Centralized configuration constants
- **Exports**: `Carl.config`
- **Key Constants**:
  - API endpoints (MODEL, VERIFICATION_MODEL, WS_URL, REST_URL)
  - System prompts (PRIMARY_SYSTEM_PROMPT, VERIFICATION_SYSTEM_PROMPT)
  - Format markers (QUESTION_PREFIX = 'Q', ANSWER_PREFIX = 'A')
  - VAD thresholds (VAD_THRESHOLD, VAD_SMOOTHING, VAD_HOLD_TIME)
  - Silence frame sending (SEND_SILENCE_INTERVAL, SILENCE_FRAME_DURATION_MS)
  - Audio settings (sample rates, buffer sizes)
  - Logging intervals

#### `state.js`
- **Purpose**: Centralized state management
- **Exports**: `Carl.state`
- **State Categories**:
  - WebSocket and audio contexts
  - API authentication
  - Response rendering
  - Facts mapping and verification queue
  - Voice Activity Detection tracking (including silence send timing)
  - Location context cache
- **Facts State**:
  - `facts.mapping`: `{number: {q, a, f}}` - question, answer, fact
  - `facts.queue`: `[1, 2, 3...]` - FIFO verification queue
  - `facts.currentVerification`: number being verified (or null)
- **Helper Methods**:
  - `addFact()`, `removeFact()`, `getNextVerification()`, `completeVerification()`
  - `isVerificationInProgress()`, `resetVadState()`, `resetSilenceTracking()`
  - `clearAudioQueue()`, `isConnected()`

#### `helpers.js` (70 lines)
- **Purpose**: Shared utility functions (de-duplicated)
- **Exports**: `Carl.helpers`
- **Functions**:
  - `formatTimestamp()` - Consolidated from two locations
  - `resampleTo16kHz()` - Audio resampling
  - `floatTo16BitPCM()`, `arrayBufferToBase64()`, `base64ToArrayBuffer()` - Audio encoding

#### `ui.js` (116 lines)
- **Purpose**: DOM manipulation and UI state
- **Exports**: `Carl.ui`
- **Responsibilities**:
  - Element caching (menu, controls, buttons, inputs)
  - Menu toggling and backdrop handling
  - API key UI state management
  - Scroll management: positions response wrapper top just below fixed toolbar
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

#### `audio.js` (255 lines)
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

#### `response.js` (264 lines)
- **Purpose**: Response rendering and verification queue processing
- **Exports**: `Carl.response`
- **Functions**:
  - `findOptimalFontSize()` - Binary search for responsive sizing
  - `startNew()`, `updateText()`, `finalize()` - Response lifecycle
  - `processTranscription()` - Routes text to facts parser or display
  - `verifyNextFact()` - Initiates verification from queue (one at a time)
  - `verifyWithGeminiPro()` - REST API call to verification model with streaming

#### `facts.js` (87 lines)
- **Purpose**: Fact parsing and queue management
- **Exports**: `Carl.facts`
- **Functions**:
  - `parseAndStore()` - Parses `Qn:` and `An:` format from model output
  - `hasFactFormat()` - Detects if text contains fact format
  - `filterFactLines()` - Removes fact format lines from text
- **Behavior**:
  - Silently stores facts in `state.facts.mapping`
  - Adds new questions to verification queue immediately upon parsing
  - Handles amended answers (moves to head of queue)

#### `connection.js` (208 lines)
- **Purpose**: WebSocket connection lifecycle
- **Exports**: `Carl.connection`
- **Functions**:
  - `toggle()` - Connection state toggling
  - `connect()` - WebSocket setup with handlers (onopen, onmessage, onerror, onclose)
  - `disconnect()` - Cleanup and resource release
  - `sendTextMessage()` - Text message transmission

#### `main.js` (78 lines)
- **Purpose**: Entry point and initialization
- **Exports**: `Carl.apiKey` (with submit and clear methods)
- **Responsibilities**:
  - Global function bindings for HTML onclick handlers
  - API key management (submit, clear, localStorage)
  - Global event handler registration

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
Binary frame encoding (16kHz PCM)
    ↓
WebSocket → Flash 2.0 (text-only output)
    ↓
Qn:/An: format (parsed silently)
    ↓
Facts stored in mapping, queued for verification
```

### Verification Pipeline (Dual-Mode)
```
Turn Complete
    ↓
verifyNextFact() called
    ↓
Get first fact from queue (FIFO)
    ↓
Check if answer exists (fact.a):
    ├── With answer → Prompt: "Please verify this answer"
    └── Without answer → Prompt: "Please find the answer"
    ↓
REST API → Gemini Pro (streaming)
    ↓
Tool execution (Google Search, Code Execution)
    ↓
Response check:
    ├── "CORRECT" → Remove from queue, try next (verification mode only)
    └── Fact text → Stream to display, store in mapping
    ↓
Later if answer arrives for Q-only fact:
    ├── Update fact.a with user's answer
    ├── Move to head of queue
    └── Re-verify with "verify answer" mode
    ↓
Repeat until queue empty
```

### Display Flow
```
User sees ONLY:
- Verified facts streamed from Pro model
- Error messages on verification failure

User does NOT see:
- Qn:/An: format from primary model
- CORRECT confirmations
- SKIP responses (silently dropped)
```

## API Integration

### Gemini Live API (WebSocket)
- **URL**: `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent`
- **Authentication**: API key (query parameter)
- **Protocol**: Binary frames for audio input, text/JSON for responses
- **Setup Configuration**:
  - `response_modalities: ['TEXT']` (text-only output, no audio)
  - System instruction for fact identification
- **Purpose**: Real-time audio processing with fact identification output

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
System prompts are defined in `config.js` and editable in UI settings:

**Primary Model (Fact Identifier):**
- Identify questions, gaps, and misinformation in conversation
- Do NOT provide direct answers
- Output format: `Qn: [question]` and `An: [answer from conversation]`
- Use matching numbers (Q1/A1, Q2/A2, etc.)
- Repeat same number for amended answers
- Skip private, situational, and unanswerable questions

**Verification Model (Fact Validator/Answerer):**
- Verify factual claims OR find answers to questions
- Respond with "CORRECT" if a user answer was provided and is accurate (not displayed to user)
- Respond with "SKIP" (first word) for private/situational/unanswerable questions
- Otherwise, provide the correct fact or found answer with full context
- Use Google Search for real-time information
- Use Code Execution for calculations
- Adapts behavior based on whether user answer was provided
- Always provide complete, understandable answers that work without the original question
  - Example: "The capital of Finland is Helsinki" (not just "Helsinki")
  - Example: "Mars has two moons" (not just "two")

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

### Question Filtering (Latest)
- Defense-in-depth filtering for private, situational, and unanswerable questions
- **Primary Model Prevention**: System prompt instructs model to avoid extracting:
  - Private questions requiring personal knowledge (passwords, family details)
  - Situational questions requiring subjective judgment ("What should I do?")
  - Questions requiring real-time context (screen contents, physical surroundings)
  - Opinion-based questions with no factual answer
- **Verification Model Fallback**: If such questions slip through, verification model responds with "SKIP" as first word
- **Silent Handling**: SKIP responses are detected and silently dropped without display to user
- Console logging for debugging: `[VERIFICATION] Q{n} SKIPPED (unanswerable question)`

### Open-Question Answering
- Extended verification to handle questions without answers
- Questions alone (Q-only) now queued for answer-finding instead of skipped
- Dual-mode verification system:
  - **With-answer mode**: Verifies user-stated answers ("Is this correct?")
  - **Without-answer mode**: Finds answers to questions ("What is the answer?")
- Verification prompt adapts based on whether answer is present
- System prompt updated to guide model for both verification and finding modes
- When user provides answer to previously-verified Q-only fact: moves to queue head for re-verification
- Enables Carl to act as both a fact-checker AND an open-question answerer

### Answer Updates During Verification
- When an answer arrives while verification is already in progress for that question:
  - Answer is stored in state (existing behavior)
  - Fact is immediately re-queued to head of verification queue (new behavior)
  - Current verification completes without displaying its result
  - Fact is re-verified with the updated answer
  - User sees only the final, corrected verification result
- Prevents stale or incorrect intermediate answers from being displayed
- Ensures all answer updates are properly verified, regardless of timing

### Fact-Checking Architecture
- Switched from Flash 2.5 (voice+text) to Flash 2.0 (text-only)
- Primary model now identifies facts instead of answering
- New `Qn:/An:` format for structured fact tracking
- Silent fact parsing (user never sees raw model output)
- FIFO verification queue with one-at-a-time processing
- "CORRECT" detection for confirmed facts
- Amended answers move to head of queue for re-verification

### Facts Module
- New `facts.js` module for parsing and queue management
- Stores facts in `state.facts.mapping`
- Maintains verification queue in `state.facts.queue`
- Handles question/answer matching by number

### Periodic Silence Frame Sending
- Sends zero-filled PCM audio frames every 1 second during detected silence
- Keeps Gemini Live API engaged and responsive during user pauses
- Configurable via `SEND_SILENCE_INTERVAL` and `SILENCE_FRAME_DURATION_MS`
- Uses same audio format as regular speech frames (16-bit PCM at 16kHz)

### Grounding with Tools
- Google Search integration for real-time information
- Code Execution for calculations and transformations
- Automatic tool selection by verification model
- Grounding metadata logged to console

### Response Quality Improvements (Latest)
- **"CORRECT" metadata handling**: "CORRECT" responses are now stored as metadata only and never displayed to the user
- **Increased token limits**: `maxOutputTokens` increased from 1024 to 2048 to prevent truncated responses
- **Full context answers**: Enhanced verification system prompt to ensure answers include full context
  - Prevents single-word or out-of-context answers
  - Examples added to guide model: "The capital of Finland is Helsinki" (not just "Helsinki")
  - Ensures answers are meaningful when displayed without the original question

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
1. Check that primary model outputs `Qn:/An:` format
2. Verify facts are being added to queue (check console logs)
3. Ensure turn completes (triggers `verifyNextFact()`)
4. Check API key for verification model
5. Look for `[FACTS]` and `[VERIFICATION]` log messages

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
