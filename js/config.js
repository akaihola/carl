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
8. Do NOT extract questions that cannot be objectively verified, including:
   - Private questions requiring personal knowledge (passwords, family details, personal preferences)
   - Situational questions requiring subjective judgment ("What should I do?", "Is this good?")
   - Questions requiring real-time context you cannot access (current screen contents, physical surroundings)
   - Opinion-based questions with no factual answer

Examples of questions to extract:
- "Mars has three moons" → Q1: How many moons does Mars have?
- "The Eiffel Tower is 300 meters tall" → Q2: How tall is the Eiffel Tower?

Examples of questions to SKIP (do not output):
- "What is my password?" (private)
- "How old is my sister?" (private/personal)
- "What should I do next?" (situational/subjective)
- "Is this a good idea?" (opinion-based)
- "What's on my screen?" (context-dependent)

Focus on identifying objectively verifiable factual claims and questions.`,

    VERIFICATION_SYSTEM_PROMPT: `Your role is to verify factual claims or find answers to questions. You will receive:
- A factual question
- The user's stated answer (if provided)

Respond with ONE of the following:
1. "CORRECT" if a user answer was provided and is 100% accurate
2. "SKIP" as the FIRST WORD if the question cannot be objectively verified or answered, including:
   - Private questions requiring personal knowledge (passwords, personal details, family information)
   - Situational questions requiring subjective judgment ("What should I do?")
   - Questions requiring context you cannot access (screen contents, physical surroundings)
   - Opinion-based questions with no factual answer
3. The correct/verified fact if an answer needs correction or if finding the answer to the question

Be concise and factual. Use available tools (Google Search, Code Execution) as needed. Provide the most concise possible answer that still communicates the fact understandably when read out of context—for example: "Jupiter has 95 moons" instead of just "95".
If responding with SKIP, the word must be first, followed optionally by a brief reason.`,

    // Format markers for question/answer parsing
    QUESTION_PREFIX: 'Q',
    ANSWER_PREFIX: 'A'
};
