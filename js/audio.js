// Audio input/output and Voice Activity Detection
window.Carl = window.Carl || {};

Carl.audio = {
    // Initialize microphone input and audio processing
    async initInput() {
        const { state, config, helpers } = Carl;

        console.log('Requesting microphone access...');
        state.mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1 }
        });
        console.log('Microphone access granted');

        state.audioContext = new AudioContext();
        const source = state.audioContext.createMediaStreamSource(state.mediaStream);
        const nativeSampleRate = state.audioContext.sampleRate;
        console.log('AudioContext created, native sample rate:', nativeSampleRate);

        // Set up AnalyserNode for voice activity detection
        state.analyser = state.audioContext.createAnalyser();
        state.analyser.fftSize = config.ANALYSER_FFT_SIZE;
        source.connect(state.analyser);

        state.audioProcessor = state.audioContext.createScriptProcessor(
            config.AUDIO_PROCESSOR_BUFFER_SIZE, 1, 1
        );

        state.audioProcessor.onaudioprocess = (e) => {
            if (!state.isConnected()) return;

            if (!this.detectVoiceActivity()) return;

            const inputData = e.inputBuffer.getChannelData(0);
            const resampled = helpers.resampleTo16kHz(inputData, nativeSampleRate);
            const pcmData = helpers.floatTo16BitPCM(resampled);
            const base64Audio = helpers.arrayBufferToBase64(pcmData);

            this.sendAudioMessage(base64Audio);
        };

        source.connect(state.audioProcessor);
        state.audioProcessor.connect(state.audioContext.destination);
        console.log('Audio processor connected');
    },

    // Voice Activity Detection using RMS volume from AnalyserNode
    detectVoiceActivity() {
        const { state, config } = Carl;

        if (!state.analyser) return true;

        const bufferLength = state.analyser.fftSize;
        const dataArray = new Float32Array(bufferLength);
        state.analyser.getFloatTimeDomainData(dataArray);

        // Calculate RMS (root mean square) volume
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
            sum += dataArray[i] * dataArray[i];
        }
        const rms = Math.sqrt(sum / bufferLength);

        // Apply smoothing: fast attack, slow release
        if (rms > state.smoothedVolume) {
            state.smoothedVolume = rms;
        } else {
            state.smoothedVolume = state.smoothedVolume * config.VAD_SMOOTHING + rms * (1 - config.VAD_SMOOTHING);
        }

        const now = performance.now();

        // Check if volume exceeds threshold
        if (state.smoothedVolume > config.VAD_THRESHOLD) {
            if (state.silencePacketCount > 0) {
                const silenceDuration = now - state.silenceStartTime;
                console.log(`Speech resumed after ${state.silencePacketCount} silent packets (${silenceDuration.toFixed(0)}ms)`);
                state.resetSilenceTracking();
            }
            state.lastSpeechTime = now;
            return true;
        }

        // Below threshold - track silence
        if (state.silencePacketCount === 0) {
            state.silenceStartTime = now;
            state.lastSilenceLogTime = now;
        }
        state.silencePacketCount++;

        // Log every 5 seconds during extended silence
        if (now - state.lastSilenceLogTime >= config.SILENCE_LOG_INTERVAL) {
            const silenceDuration = now - state.silenceStartTime;
            console.log(`Silence: ${state.silencePacketCount} packets (${silenceDuration.toFixed(0)}ms)`);
            state.lastSilenceLogTime = now;
        }

        // Keep sending for a short time after speech stops (hold time)
        if (now - state.lastSpeechTime < config.VAD_HOLD_TIME) {
            return true;
        }

        return false;
    },

    // Send audio data over WebSocket
    sendAudioMessage(base64Audio) {
        const { state, config } = Carl;

        const audioMessage = {
            realtime_input: {
                media_chunks: [{
                    mime_type: 'audio/pcm',
                    data: base64Audio
                }]
            }
        };

        try {
            state.ws.send(JSON.stringify(audioMessage));
            const now = performance.now();
            if (now - state.lastAudioLogTime >= config.AUDIO_LOG_INTERVAL) {
                console.log('Audio sent:', {
                    size: base64Audio.length,
                    volume: state.smoothedVolume.toFixed(4),
                    wsReady: state.isConnected()
                });
                state.lastAudioLogTime = now;
            }
        } catch (err) {
            console.error('Error sending audio message:', err);
        }
    },

    // Queue audio for playback
    queueForPlayback(base64Audio) {
        const { state, helpers } = Carl;

        state.audioQueue.push(helpers.base64ToArrayBuffer(base64Audio));

        if (!state.isPlayingAudio) {
            this.playNextChunk();
        }
    },

    // Play next audio chunk from queue
    async playNextChunk() {
        const { state, config } = Carl;

        if (state.audioQueue.length === 0) {
            state.isPlayingAudio = false;
            return;
        }

        state.isPlayingAudio = true;

        if (!state.outputAudioContext) {
            state.outputAudioContext = new AudioContext({ sampleRate: config.OUTPUT_SAMPLE_RATE });
        }

        const pcmData = state.audioQueue.shift();
        const int16Array = new Int16Array(pcmData);
        const float32Array = new Float32Array(int16Array.length);

        for (let i = 0; i < int16Array.length; i++) {
            float32Array[i] = int16Array[i] / 32768;
        }

        const audioBuffer = state.outputAudioContext.createBuffer(
            1, float32Array.length, config.OUTPUT_SAMPLE_RATE
        );
        audioBuffer.getChannelData(0).set(float32Array);

        const source = state.outputAudioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(state.outputAudioContext.destination);
        source.onended = () => this.playNextChunk();
        source.start();
    },

    // Clean up audio resources
    cleanup() {
        const { state } = Carl;

        if (state.mediaStream) {
            console.log('Stopping media stream tracks');
            state.mediaStream.getTracks().forEach(track => track.stop());
            state.mediaStream = null;
        }
        if (state.audioContext) {
            console.log('Closing audio context');
            state.audioContext.close();
            state.audioContext = null;
        }
        if (state.outputAudioContext) {
            console.log('Closing output audio context');
            state.outputAudioContext.close();
            state.outputAudioContext = null;
        }

        state.clearAudioQueue();
        state.resetVadState();
    }
};
