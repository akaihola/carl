// Application configuration constants
window.Carl = window.Carl || {};

Carl.config = {
    // API endpoints
    MODEL: 'models/gemini-2.5-flash-native-audio-preview-12-2025',
    VERIFICATION_MODEL: 'models/gemini-2.5-pro',
    HOST: 'generativelanguage.googleapis.com',

    get WS_URL() {
        return `wss://${this.HOST}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent`;
    },

    get REST_URL() {
        return `https://${this.HOST}/v1beta`;
    },

    // Storage
    API_KEY_STORAGE_KEY: 'gemini_api_key',

    // Protocol markers
    STRUCTURED_RESPONSE_MARKER: '§',

    // Voice Activity Detection thresholds
    VAD_THRESHOLD: 0.05,      // Minimum RMS volume to consider as speech
    VAD_SMOOTHING: 0.9,       // Smoothing factor (0-1), higher = slower release
    VAD_HOLD_TIME: 300,       // Keep sending for this many ms after speech stops

    // Audio settings
    INPUT_SAMPLE_RATE: 16000,
    OUTPUT_SAMPLE_RATE: 24000,
    AUDIO_PROCESSOR_BUFFER_SIZE: 4096,
    ANALYSER_FFT_SIZE: 256,

    // Logging intervals (ms)
    AUDIO_LOG_INTERVAL: 2000,
    SILENCE_LOG_INTERVAL: 5000,

    // Silence frame sending (keeps Gemini Live API engaged during pauses)
    SEND_SILENCE_INTERVAL: 1000,  // Send a silence frame every 1000ms (1 second)
    SILENCE_FRAME_DURATION_MS: 100  // Duration of each silence frame in ms
};
