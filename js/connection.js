// WebSocket connection management
window.Carl = window.Carl || {};

Carl.connection = {
    // Toggle connection state
    async toggle() {
        const { state, ui } = Carl;

        console.log('toggleConnection called, ws:', state.ws);
        if (state.ws) {
            console.log('Already connected, disconnecting');
            this.disconnect();
        } else {
            console.log('Not connected, attempting to connect');
            await this.connect();
        }
        ui.blurConnectButton();
    },

    // Establish WebSocket connection
    async connect() {
        const { state, config, ui, audio, location, response } = Carl;

        console.log('connect() called');
        const key = state.currentApiKey;
        const basePrompt = ui.getSystemPrompt();

        if (!key) {
            console.error('No API key available');
            alert('Please enter an API Key');
            return;
        }

        // Get location context and prepend to system prompt
        const locationContext = await location.getContext();
        const prompt = locationContext + basePrompt;
        console.log('API key available, initializing audio...');

        // Initialize audio input
        try {
            await audio.initInput();
        } catch (err) {
            console.error('Audio initialization error:', err);
            alert('Microphone error: ' + err.message);
            return;
        }

        // Initialize WebSocket
        const url = `${config.WS_URL}?key=${key}`;
        console.log('Creating WebSocket connection to:', url);
        state.ws = new WebSocket(url);

        state.ws.onopen = () => {
            console.log('WebSocket connected (readyState:', state.ws.readyState, ')');
            ui.setConnected(true);

            const setupMessage = {
                setup: {
                    model: config.MODEL,
                    generation_config: {
                        response_modalities: ['TEXT']
                    },
                    system_instruction: {
                        parts: [{ text: prompt }]
                    }
                }
            };
            console.log('Sending setup message with model:', config.MODEL);
            console.log('Setup message:', JSON.stringify(setupMessage, null, 2));
            state.ws.send(JSON.stringify(setupMessage));
        };

        state.ws.onmessage = async (event) => {
            try {
                let data = event.data;
                if (data instanceof Blob) {
                    data = await data.text();
                }

                const msg = JSON.parse(data);

                if (msg.serverContent?.modelTurn) {
                    const parts = msg.serverContent.modelTurn.parts;
                    for (const part of parts) {
                        // Log text parts with type indicator
                        if (part.text) {
                            const type = part.thought ? 'thought' : 'response';
                            if (part.thought) {
                                console.log(`[MODEL] Received ${type}:\n${part.text}`);
                            } else {
                                const preview = part.text.substring(0, 100).replace(/\n/g, ' ');
                                console.log(`[MODEL] Received ${type}: ${preview}${part.text.length > 100 ? '...' : ''}`);
                            }
                        }

                        // Skip thought parts (internal reasoning)
                        if (part.thought) continue;

                        // Handle text (Flash 2.0 outputs text only, including Qn:/An: format)
                        if (part.text) {
                            // Parse Qn:/An: format silently (will be handled by response.processTranscription)
                            response.processTranscription(part.text);
                        }
                    }
                }

                // Handle audio transcription
                if (msg.serverContent?.outputTranscription) {
                    const transcription = msg.serverContent.outputTranscription.text;
                    console.log(`[MODEL] Received transcription: ${transcription}`);
                    if (transcription) {
                        response.processTranscription(transcription);
                    }
                }

                // Check if turn is complete
                if (msg.serverContent?.turnComplete) {
                    console.log('[MODEL] Turn complete');
                    response.finalize();
                    // Start verification of any queued facts
                    setTimeout(() => response.verifyNextFact(), 100);
                }
            } catch (err) {
                console.error('Failed to parse message:', event.data);
                console.error('Parse error:', err);
            }
        };

        state.ws.onerror = (err) => {
            console.error('WebSocket Error:', err);

            const errorStr = err.toString().toLowerCase();
            if (errorStr.includes('401') || errorStr.includes('unauthorized') || errorStr.includes('invalid')) {
                console.error('API key appears invalid');
                localStorage.removeItem(config.API_KEY_STORAGE_KEY);
                state.currentApiKey = null;
                ui.showApiKeyInput();
                alert('API key appears to be invalid. Please enter a new one.');
            }

            this.disconnect();
        };

        state.ws.onclose = (event) => {
            console.log('WebSocket closed - code:', event.code, 'reason:', event.reason, 'wasClean:', event.wasClean);
            if (state.ws) {
                this.disconnect();
            }
        };
    },

    // Close connection and clean up resources
    disconnect() {
        const { state, ui, audio, response } = Carl;

        console.log('disconnect() called');
        ui.setConnected(false);

        if (state.ws) {
            console.log('Closing WebSocket');
            state.ws.close();
            state.ws = null;
        }

        audio.cleanup();
        response.finalize();
    },

    // Send text message over WebSocket
    sendTextMessage(text) {
        const { state } = Carl;

        console.log('sendTextMessage called with:', text);
        console.log('ws:', state.ws, 'readyState:', state.ws?.readyState);

        if (!state.isConnected()) {
            console.log('Not connected, aborting sendTextMessage');
            alert('Not connected to the server');
            return;
        }

        console.log('Sending text message to WebSocket');
        const textMessage = {
            client_content: {
                turns: [{
                    role: 'user',
                    parts: [{ text }]
                }],
                turn_complete: true
            }
        };
        state.ws.send(JSON.stringify(textMessage));
    }
};
