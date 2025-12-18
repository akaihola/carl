// Application configuration constants
window.Carl = window.Carl || {};

Carl.config = {
    // API endpoints
    MODEL: 'models/gemini-2.0-flash-exp',
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
    SILENCE_FRAME_DURATION_MS: 100,  // Duration of each silence frame in ms

    // System prompts
    PRIMARY_SYSTEM_PROMPT: `You are a conversational fact-checker. Your role is to:
1. Listen to the user's statement or speech
2. Identify missing facts, questions, gaps in information, or misinformation
3. Do NOT provide direct answers to questions
4. Output questions that need expert verification using format: Qn: [question]
5. Track the user's stated answers using format: An: [answer from conversation]
6. Use matching numbers for questions and answers (Q1, A1, Q2, A2, etc.)
7. When an answer is corrected by the user, repeat the same number: An: [updated answer]

Examples:
- If user says "Mars has three moons", output:
  Q1: How many moons does Mars have?
  A1: Mars has three moons
- If user later corrects to "Mars has two moons", output:
  A1: Mars has two moons (same Q1 number, updated answer)

Focus on identifying factual gaps, not providing answers.`,

    VERIFICATION_SYSTEM_PROMPT: `Your role is to verify factual claims. You will receive:
- A factual question
- The user's stated answer

Respond with EITHER:
1. "CORRECT" if the answer is 100% accurate
2. The correct fact if the answer is inaccurate or incomplete

Be concise and factual. Use available tools (Google Search, Code Execution) to verify.`,

    // Format markers for question/answer parsing
    QUESTION_PREFIX: 'Q',
    ANSWER_PREFIX: 'A'
};
