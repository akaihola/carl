// Centralized application state
window.Carl = window.Carl || {};

Carl.state = {
    // WebSocket connection
    ws: null,

    // Audio contexts
    audioContext: null,
    outputAudioContext: null,
    mediaStream: null,
    audioProcessor: null,
    analyser: null,

    // API key
    currentApiKey: null,

    // Response rendering
    currentResponseEl: null,
    currentResponseText: '',

    // Scroll tracking
    userHasScrolledUp: false,
    isProgrammaticScrolling: false,
    scrollEndTimeout: null,

    // Structured response parsing (confidence protocol)
    pendingStructuredResponse: '',
    isParsingStructured: false,
    structuredBraceDepth: 0,

    // Audio playback queue
    audioQueue: [],
    isPlayingAudio: false,

    // Voice Activity Detection
    smoothedVolume: 0,
    lastSpeechTime: 0,
    silencePacketCount: 0,
    silenceStartTime: 0,
    lastSilenceLogTime: 0,
    lastAudioLogTime: 0,
    lastSilenceSendTime: 0,

    // Location context cache
    cachedLocationContext: null,

    // Reset structured response state
    resetStructuredState() {
        this.pendingStructuredResponse = '';
        this.isParsingStructured = false;
        this.structuredBraceDepth = 0;
    },

    // Reset VAD state
    resetVadState() {
        this.analyser = null;
        this.smoothedVolume = 0;
        this.lastSpeechTime = 0;
        this.silencePacketCount = 0;
        this.silenceStartTime = 0;
        this.lastSilenceLogTime = 0;
        this.lastSilenceSendTime = 0;
    },

    // Reset silence tracking (when speech resumes)
    resetSilenceTracking() {
        this.silencePacketCount = 0;
        this.silenceStartTime = 0;
        this.lastSilenceLogTime = 0;
    },

    // Clear audio queue and stop playback
    clearAudioQueue() {
        this.audioQueue = [];
        this.isPlayingAudio = false;
    },

    // Check if WebSocket is connected and open
    isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }
};
