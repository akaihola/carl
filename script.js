let ws = null;
let audioContext = null;
let mediaStream = null;
let audioProcessor = null;
let currentApiKey = null;
let currentResponseEl = null;
let currentResponseText = '';
let userHasScrolledUp = false;

// Audio output
let outputAudioContext = null;
let audioQueue = [];
let isPlayingAudio = false;

// Voice Activity Detection
let analyser = null;
let smoothedVolume = 0;
const VAD_THRESHOLD = 0.05;      // Minimum RMS volume to consider as speech
const VAD_SMOOTHING = 0.9;       // Smoothing factor (0-1), higher = slower release
const VAD_HOLD_TIME = 300;       // Keep sending for this many ms after speech stops
let lastSpeechTime = 0;
let silencePacketCount = 0;
let silenceStartTime = 0;
let lastSilenceLogTime = 0;
let lastAudioLogTime = 0;        // Track last time we logged audio above threshold

// Configuration
const MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025";
const HOST = "generativelanguage.googleapis.com";
const WS_URL = `wss://${HOST}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent`;
const API_KEY_STORAGE_KEY = "gemini_api_key";

// Menu functions
function toggleMenu() {
    const menu = document.getElementById('menu');
    const menuBtn = document.getElementById('menuBtn');
    menu.classList.toggle('open');
    menuBtn.classList.toggle('active');
}

function closeMenu() {
    const menu = document.getElementById('menu');
    const menuBtn = document.getElementById('menuBtn');
    menu.classList.remove('open');
    menuBtn.classList.remove('active');
}

function closeMenuOnBackdrop(event) {
    if (event.target.id === 'menu') {
        closeMenu();
    }
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
    const savedKey = localStorage.getItem(API_KEY_STORAGE_KEY);
    if (savedKey) {
        currentApiKey = savedKey;
        showConnectButton();
    } else {
        showApiKeyInput();
    }

    // Track user scroll behavior
    window.addEventListener('scroll', () => {
        const atBottom = (window.innerHeight + window.scrollY) >= (document.body.scrollHeight - 10);
        userHasScrolledUp = !atBottom;
    });

    // Catch Enter key globally to send text message (only when not focused on inputs/buttons)
    document.addEventListener('keydown', (e) => {
        console.log('keydown:', e.key, 'activeElement:', document.activeElement?.tagName, document.activeElement?.id);
        if (e.key === 'Enter' && ws && ws.readyState === WebSocket.OPEN) {
            const activeEl = document.activeElement;
            const isInputFocused = activeEl && (
                activeEl.tagName === 'INPUT' ||
                activeEl.tagName === 'TEXTAREA' ||
                activeEl.tagName === 'BUTTON'
            );
            console.log('Enter pressed, isInputFocused:', isInputFocused);
            if (!isInputFocused) {
                e.preventDefault();
                sendTextMessage('Tell me something funny again.');
            }
        }
    });
});

function showApiKeyInput() {
    document.getElementById('controls').classList.remove('hidden');
    document.getElementById('apiKeySection').style.display = 'flex';
    document.getElementById('connectBtn').style.display = 'none';
    document.getElementById('clearApiKeyBtn').style.display = 'none';
}

function showConnectButton() {
    document.getElementById('controls').classList.add('hidden');
    document.getElementById('apiKeySection').style.display = 'none';
    document.getElementById('connectBtn').style.display = 'inline-block';
    document.getElementById('clearApiKeyBtn').style.display = 'inline-block';
}

async function submitApiKey() {
    const key = document.getElementById('apiKey').value.trim();
    if (!key) {
        alert("Please enter an API Key");
        return;
    }

    localStorage.setItem(API_KEY_STORAGE_KEY, key);
    currentApiKey = key;
    document.getElementById('apiKey').value = '';
    showConnectButton();
}

function clearApiKey() {
    if (confirm("Are you sure you want to clear the saved API key?")) {
        localStorage.removeItem(API_KEY_STORAGE_KEY);
        currentApiKey = null;
        showApiKeyInput();
    }
}


// Bisect to find the optimal font size that fills the viewport height
// without breaking words mid-letter (only breaks at whitespace/punctuation)
function findOptimalFontSize(text) {
    const viewportHeight = window.innerHeight;
    const padding = parseFloat(getComputedStyle(document.body).paddingTop) * 2;
    const toolbarHeight = document.getElementById('toolbar').offsetHeight;
    const availableHeight = viewportHeight - padding - toolbarHeight - 20; // 20px margin

    // Create a measuring element
    const measureEl = document.createElement('div');
    measureEl.className = 'response measuring';
    measureEl.textContent = text;
    document.body.appendChild(measureEl);

    let minSize = 12;
    let maxSize = 200;
    let optimalSize = minSize;

    // Binary search for optimal font size
    // The measuring element uses word-break: keep-all to prevent mid-word breaks
    // If text overflows horizontally, the font is too large for longest word
    while (maxSize - minSize > 1) {
        const midSize = Math.floor((minSize + maxSize) / 2);
        measureEl.style.fontSize = midSize + 'px';

        const fitsHeight = measureEl.offsetHeight <= availableHeight;
        const fitsWidth = measureEl.scrollWidth <= measureEl.clientWidth;

        if (fitsHeight && fitsWidth) {
            optimalSize = midSize;
            minSize = midSize;
        } else {
            maxSize = midSize;
        }
    }

    document.body.removeChild(measureEl);
    return optimalSize;
}

function startNewResponse() {
    currentResponseText = '';
    currentResponseEl = document.createElement('div');
    currentResponseEl.className = 'response';
    currentResponseEl.style.visibility = 'visible';
    document.getElementById('log').appendChild(currentResponseEl);
}

function finalizeResponse() {
    if (currentResponseEl && currentResponseText) {
        // Final font size optimization for complete text
        const fontSize = findOptimalFontSize(currentResponseText);
        currentResponseEl.style.fontSize = fontSize + 'px';
        currentResponseEl = null;
        currentResponseText = '';

        // Auto-scroll to bottom unless user has scrolled up
        if (!userHasScrolledUp) {
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
        }
    }
}

async function toggleConnection() {
    console.log('toggleConnection called, ws:', ws);
    if (ws) {
        console.log('Already connected, disconnecting');
        disconnect();
    } else {
        console.log('Not connected, attempting to connect');
        await connect();
    }
    document.getElementById('connectBtn').blur();
}

async function connect() {
    console.log('connect() called');
    const key = currentApiKey;
    const prompt = document.getElementById('systemPrompt').value;

    if (!key) {
        console.error('No API key available');
        alert("Please enter an API Key");
        return;
    }
    console.log('API key available, initializing audio...');

    // 1. Initialize Audio (16kHz, Mono, PCM)
    try {
        console.log('Requesting microphone access...');
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: {
            channelCount: 1
        }});
        console.log('Microphone access granted');

        audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(mediaStream);
        const nativeSampleRate = audioContext.sampleRate;
        console.log('AudioContext created, native sample rate:', nativeSampleRate);

        // Set up AnalyserNode for voice activity detection
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;  // Small FFT for fast response
        source.connect(analyser);

        audioProcessor = audioContext.createScriptProcessor(4096, 1, 1);

        audioProcessor.onaudioprocess = (e) => {
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                return;
            }

            // Voice Activity Detection using RMS volume
            const isSpeaking = detectVoiceActivity();
            if (!isSpeaking) {
                return;
            }

            const inputData = e.inputBuffer.getChannelData(0);
            const resampled = resampleTo16kHz(inputData, nativeSampleRate);
            const pcmData = floatTo16BitPCM(resampled);
            const base64Audio = arrayBufferToBase64(pcmData);

            sendAudioMessage(base64Audio);
        };

        source.connect(audioProcessor);
        audioProcessor.connect(audioContext.destination);
        console.log('Audio processor connected');
    } catch (err) {
        console.error('Audio initialization error:', err);
        alert("Microphone error: " + err.message);
        return;
    }

    // 2. Initialize WebSocket
    const url = `${WS_URL}?key=${key}`;
    console.log('Creating WebSocket connection to:', url);
    ws = new WebSocket(url);

    ws.onopen = () => {
        console.log('WebSocket connected (readyState:', ws.readyState, ')');
        document.getElementById('connectBtn').textContent = "Disconnect";

        const setupMessage = {
            setup: {
                model: MODEL,
                generation_config: {
                    response_modalities: ["AUDIO"],
                    speech_config: {
                        voice_config: {
                            prebuilt_voice_config: {
                                voice_name: "Kore"
                            }
                        }
                    }
                },
                output_audio_transcription: {},
                system_instruction: {
                    parts: [{ text: prompt }]
                }
            }
        };
        console.log('Sending setup message with model:', MODEL);
        console.log('Setup message:', JSON.stringify(setupMessage, null, 2));
        ws.send(JSON.stringify(setupMessage));
    };

    ws.onmessage = async (event) => {
        try {
            let data = event.data;
            if (data instanceof Blob) {
                data = await data.text();
            }

            const response = JSON.parse(data);

            if (response.serverContent && response.serverContent.modelTurn) {
                const parts = response.serverContent.modelTurn.parts;
                for (const part of parts) {
                    // Log text parts with type indicator
                    if (part.text) {
                        const type = part.thought ? 'thought' : 'response';
                        const preview = part.text.substring(0, 100).replace(/\n/g, ' ');
                        console.log(`Received ${type}: ${preview}${part.text.length > 100 ? '...' : ''}`);
                    }
                    // Skip thought parts (internal reasoning)
                    if (part.thought) {
                        continue;
                    }
                    // Handle audio data
                    if (part.inlineData && part.inlineData.mimeType === 'audio/pcm') {
                        console.log('Received audio chunk');
                        queueAudioForPlayback(part.inlineData.data);
                    }
                    // Handle text (for non-audio models)
                    if (part.text) {
                        if (!currentResponseEl) {
                            startNewResponse();
                        }
                        currentResponseText += part.text;
                    }
                }
            }

            // Handle audio transcription
            if (response.serverContent && response.serverContent.outputTranscription) {
                const transcription = response.serverContent.outputTranscription.text;
                console.log('Received transcription:', transcription);
                if (transcription) {
                    if (!currentResponseEl) {
                        startNewResponse();
                    }
                    currentResponseText += transcription;
                    currentResponseEl.textContent = currentResponseText;

                    // Recalculate font size for current text (CSS transition smooths the change)
                    const fontSize = findOptimalFontSize(currentResponseText);
                    currentResponseEl.style.fontSize = fontSize + 'px';

                    // Auto-scroll during streaming
                    if (!userHasScrolledUp) {
                        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                    }
                }
            }

            // Check if turn is complete
            if (response.serverContent && response.serverContent.turnComplete) {
                console.log('Turn complete');
                finalizeResponse();
            }
        } catch (err) {
            console.error("Failed to parse message:", event.data);
            console.error("Parse error:", err);
        }
    };

    ws.onerror = (err) => {
        console.error("WebSocket Error:", err);

        const errorStr = err.toString().toLowerCase();
        if (errorStr.includes('401') || errorStr.includes('unauthorized') || errorStr.includes('invalid')) {
            console.error('API key appears invalid');
            localStorage.removeItem(API_KEY_STORAGE_KEY);
            currentApiKey = null;
            showApiKeyInput();
            alert("API key appears to be invalid. Please enter a new one.");
        }

        disconnect();
    };

    ws.onclose = (event) => {
        console.log('WebSocket closed - code:', event.code, 'reason:', event.reason, 'wasClean:', event.wasClean);
        if (ws) {
            disconnect();
        }
    };
}

function disconnect() {
    console.log('disconnect() called');
    document.getElementById('connectBtn').textContent = "Connect & Start";

    if (ws) {
        console.log('Closing WebSocket');
        ws.close();
        ws = null;
    }
    if (mediaStream) {
        console.log('Stopping media stream tracks');
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }
    if (audioContext) {
        console.log('Closing audio context');
        audioContext.close();
        audioContext = null;
    }
    if (outputAudioContext) {
        console.log('Closing output audio context');
        outputAudioContext.close();
        outputAudioContext = null;
    }
    audioQueue = [];
    isPlayingAudio = false;

    // Reset VAD state
    analyser = null;
    smoothedVolume = 0;
    lastSpeechTime = 0;
    silencePacketCount = 0;
    silenceStartTime = 0;
    lastSilenceLogTime = 0;

    // Finalize any pending response
    finalizeResponse();
}

// Audio playback functions
function queueAudioForPlayback(base64Audio) {
    const binaryString = atob(base64Audio);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    audioQueue.push(bytes.buffer);

    if (!isPlayingAudio) {
        playNextAudioChunk();
    }
}

async function playNextAudioChunk() {
    if (audioQueue.length === 0) {
        isPlayingAudio = false;
        return;
    }

    isPlayingAudio = true;

    if (!outputAudioContext) {
        outputAudioContext = new AudioContext({ sampleRate: 24000 });
    }

    const pcmData = audioQueue.shift();
    const int16Array = new Int16Array(pcmData);
    const float32Array = new Float32Array(int16Array.length);

    for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768;
    }

    const audioBuffer = outputAudioContext.createBuffer(1, float32Array.length, 24000);
    audioBuffer.getChannelData(0).set(float32Array);

    const source = outputAudioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(outputAudioContext.destination);
    source.onended = () => playNextAudioChunk();
    source.start();
}

function sendAudioMessage(base64Audio) {
    const audioMessage = {
        realtime_input: {
            media_chunks: [{
                mime_type: "audio/pcm",
                data: base64Audio
            }]
        }
    };
    try {
        ws.send(JSON.stringify(audioMessage));
        // Log audio status periodically (every 2 seconds) instead of on every packet
        const now = performance.now();
        if (now - lastAudioLogTime >= 2000) {
            console.log('Audio sent:', { size: base64Audio.length, volume: smoothedVolume.toFixed(4), wsReady: ws?.readyState === WebSocket.OPEN });
            lastAudioLogTime = now;
        }
    } catch (err) {
        console.error('Error sending audio message:', err);
    }
}

function sendTextMessage(text) {
    console.log('sendTextMessage called with:', text);
    console.log('ws:', ws, 'readyState:', ws?.readyState);
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        console.log('Not connected, aborting sendTextMessage');
        alert("Not connected to the server");
        return;
    }

    console.log('Sending text message to WebSocket');
    const textMessage = {
        client_content: {
            turns: [{
                role: "user",
                parts: [{ text: text }]
            }],
            turn_complete: true
        }
    };
    ws.send(JSON.stringify(textMessage));
}

// --- Helpers ---

// Voice Activity Detection using RMS volume from AnalyserNode
// Based on cwilso/volume-meter approach
function detectVoiceActivity() {
    if (!analyser) return true;  // If no analyser, allow all audio

    const bufferLength = analyser.fftSize;
    const dataArray = new Float32Array(bufferLength);
    analyser.getFloatTimeDomainData(dataArray);

    // Calculate RMS (root mean square) volume
    let sum = 0;
    for (let i = 0; i < bufferLength; i++) {
        sum += dataArray[i] * dataArray[i];
    }
    const rms = Math.sqrt(sum / bufferLength);

    // Apply smoothing: fast attack, slow release
    if (rms > smoothedVolume) {
        smoothedVolume = rms;  // Fast attack
    } else {
        smoothedVolume = smoothedVolume * VAD_SMOOTHING + rms * (1 - VAD_SMOOTHING);  // Slow release
    }

    const now = performance.now();
    const isBelowThreshold = smoothedVolume <= VAD_THRESHOLD;

    // Check if volume exceeds threshold
    if (smoothedVolume > VAD_THRESHOLD) {
        // Speech detected - log silence stats if we were silent
        if (silencePacketCount > 0) {
            const silenceDuration = now - silenceStartTime;
            console.log(`Speech resumed after ${silencePacketCount} silent packets (${silenceDuration.toFixed(0)}ms)`);
            silencePacketCount = 0;
            silenceStartTime = 0;
            lastSilenceLogTime = 0;
        }
        lastSpeechTime = now;
        return true;
    }

    // Below threshold - track silence
    if (isBelowThreshold) {
        if (silencePacketCount === 0) {
            silenceStartTime = now;
            lastSilenceLogTime = now;
        }
        silencePacketCount++;

        // Log every 5 seconds during extended silence
        if (now - lastSilenceLogTime >= 5000) {
            const silenceDuration = now - silenceStartTime;
            console.log(`Silence: ${silencePacketCount} packets (${silenceDuration.toFixed(0)}ms)`);
            lastSilenceLogTime = now;
        }
    }

    // Keep sending for a short time after speech stops (hold time)
    if (now - lastSpeechTime < VAD_HOLD_TIME) {
        return true;
    }

    return false;
}

function resampleTo16kHz(float32Array, fromSampleRate) {
    if (fromSampleRate === 16000) return float32Array;

    const ratio = fromSampleRate / 16000;
    const newLength = Math.floor(float32Array.length / ratio);
    const result = new Float32Array(newLength);

    for (let i = 0; i < newLength; i++) {
        const srcIndex = i * ratio;
        const srcIndexFloor = Math.floor(srcIndex);
        const srcIndexCeil = Math.min(srcIndexFloor + 1, float32Array.length - 1);
        const fraction = srcIndex - srcIndexFloor;

        result[i] = float32Array[srcIndexFloor] * (1 - fraction) + float32Array[srcIndexCeil] * fraction;
    }

    return result;
}

function floatTo16BitPCM(float32Array) {
    const buffer = new ArrayBuffer(float32Array.length * 2);
    const view = new DataView(buffer);
    for (let i = 0; i < float32Array.length; i++) {
        let s = Math.max(-1, Math.min(1, float32Array[i]));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return buffer;
}

function arrayBufferToBase64(buffer) {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
}
