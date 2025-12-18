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

    // Facts mapping and verification queue
    facts: {
        mapping: {},      // {number: {q: question, a: answer, f: fact}}
        queue: [],        // [1, 2, 3, ...] numbers awaiting verification (FIFO)
        currentVerification: null,  // number currently being verified, null if none
        completed: new Set()  // Set of fact numbers that have been verified and completed
    },

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
    },

    // Add or update a fact in the mapping
    addFact(number, q, a) {
        if (!this.facts.mapping[number]) {
            this.facts.mapping[number] = { q, a, f: null };
            this.facts.queue.push(number);
            console.log(`[FACTS] Added fact ${number}: "${q}"`);
        } else {
            // Skip if fact already completed (verified and displayed)
            if (this.facts.completed.has(number)) {
                console.log(`[FACTS] Fact ${number} already completed, ignoring update`);
                return;
            }

            // Update answer if it's a new one
            this.facts.mapping[number].a = a;
            this.facts.mapping[number].f = null;  // Reset fact for re-verification
            // Move to head of queue if not already verifying
            if (this.facts.currentVerification !== number) {
                this.facts.queue = this.facts.queue.filter(n => n !== number);
                this.facts.queue.unshift(number);
                console.log(`[FACTS] Updated fact ${number} answer, moved to head of queue`);
            }
        }
    },

    // Remove a fact from the queue after verification
    removeFact(number) {
        this.facts.queue = this.facts.queue.filter(n => n !== number);
        console.log(`[FACTS] Removed fact ${number} from queue`);
    },

    // Get the next fact to verify (FIFO)
    getNextVerification() {
        if (this.facts.queue.length === 0) return null;
        const number = this.facts.queue[0];
        this.facts.currentVerification = number;
        return number;
    },

    // Mark verification as complete
    completeVerification() {
        if (this.facts.currentVerification !== null) {
            this.facts.currentVerification = null;
        }
    },

    // Check if a verification is in progress
    isVerificationInProgress() {
        return this.facts.currentVerification !== null;
    }
};
