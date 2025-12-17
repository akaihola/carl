let ws = null;
let audioContext = null;
let mediaStream = null;
let audioProcessor = null;
let currentApiKey = null;
let currentResponseEl = null;
let currentResponseText = '';
let userHasScrolledUp = false;

// Configuration
const MODEL = "models/gemini-2.0-flash-exp";
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
    while (maxSize - minSize > 1) {
        const midSize = Math.floor((minSize + maxSize) / 2);
        measureEl.style.fontSize = midSize + 'px';

        if (measureEl.offsetHeight <= availableHeight) {
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
    currentResponseEl.style.visibility = 'hidden';
    document.getElementById('log').appendChild(currentResponseEl);
}

function finalizeResponse() {
    if (currentResponseEl && currentResponseText) {
        const fontSize = findOptimalFontSize(currentResponseText);
        currentResponseEl.style.fontSize = fontSize + 'px';
        currentResponseEl.textContent = currentResponseText;
        currentResponseEl.style.visibility = 'visible';
        currentResponseEl = null;
        currentResponseText = '';

        // Auto-scroll to bottom unless user has scrolled up
        if (!userHasScrolledUp) {
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
        }
    }
}

async function toggleConnection() {
    if (ws) {
        disconnect();
    } else {
        await connect();
    }
    document.getElementById('connectBtn').blur();
}

async function connect() {
    const key = currentApiKey;
    const prompt = document.getElementById('systemPrompt').value;

    if (!key) { alert("Please enter an API Key"); return; }

    // 1. Initialize Audio (16kHz, Mono, PCM)
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: {
            channelCount: 1
        }});

        audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(mediaStream);
        const nativeSampleRate = audioContext.sampleRate;

        audioProcessor = audioContext.createScriptProcessor(4096, 1, 1);

        audioProcessor.onaudioprocess = (e) => {
            if (!ws || ws.readyState !== WebSocket.OPEN) return;

            const inputData = e.inputBuffer.getChannelData(0);
            const resampled = resampleTo16kHz(inputData, nativeSampleRate);
            const pcmData = floatTo16BitPCM(resampled);
            const base64Audio = arrayBufferToBase64(pcmData);

            sendAudioMessage(base64Audio);
        };

        source.connect(audioProcessor);
        audioProcessor.connect(audioContext.destination);
    } catch (err) {
        console.error(err);
        alert("Microphone error: " + err.message);
        return;
    }

    // 2. Initialize WebSocket
    const url = `${WS_URL}?key=${key}`;
    ws = new WebSocket(url);

    ws.onopen = () => {
        document.getElementById('connectBtn').textContent = "Disconnect";

        const setupMessage = {
            setup: {
                model: MODEL,
                generation_config: {
                    response_modalities: ["TEXT"]
                },
                system_instruction: {
                    parts: [{ text: prompt }]
                }
            }
        };
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
                    if (part.text) {
                        if (!currentResponseEl) {
                            startNewResponse();
                        }
                        currentResponseText += part.text;
                    }
                }
            }

            // Check if turn is complete
            if (response.serverContent && response.serverContent.turnComplete) {
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
            localStorage.removeItem(API_KEY_STORAGE_KEY);
            currentApiKey = null;
            showApiKeyInput();
            alert("API key appears to be invalid. Please enter a new one.");
        }

        disconnect();
    };

    ws.onclose = () => {
        if (ws) {
            disconnect();
        }
    };
}

function disconnect() {
    document.getElementById('connectBtn').textContent = "Connect & Start";

    if (ws) {
        ws.close();
        ws = null;
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }

    // Finalize any pending response
    finalizeResponse();
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
    ws.send(JSON.stringify(audioMessage));
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
