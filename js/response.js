// Response rendering and structured response handling
window.Carl = window.Carl || {};

Carl.response = {
    // Find optimal font size using binary search
    findOptimalFontSize(text) {
        const { ui } = Carl;
        const viewportHeight = window.innerHeight;
        const padding = parseFloat(getComputedStyle(document.body).paddingTop) * 2;
        const toolbarHeight = ui.elements.toolbar.offsetHeight;
        const availableHeight = viewportHeight - padding - toolbarHeight - 20;

        const measureEl = document.createElement('div');
        measureEl.className = 'response measuring';
        measureEl.textContent = text;
        document.body.appendChild(measureEl);

        let minSize = 12;
        let maxSize = 200;
        let optimalSize = minSize;

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
        console.log(`Font size calculation: text length=${text.length}, viewport=${viewportHeight}px, available=${availableHeight}px, optimal=${optimalSize}px`);
        return optimalSize;
    },

    // Start a new response element
    startNew() {
        const { state, ui } = Carl;
        state.currentResponseText = '';
        state.currentResponseEl = document.createElement('div');
        state.currentResponseEl.className = 'response';
        state.currentResponseEl.style.visibility = 'visible';
        ui.elements.log.appendChild(state.currentResponseEl);
    },

    // Update current response with text and recalculate font size
    updateText(text) {
        const { state, ui } = Carl;
        if (!state.currentResponseEl) this.startNew();

        state.currentResponseText += text;
        state.currentResponseEl.textContent = state.currentResponseText;
        state.currentResponseEl.style.fontSize = this.findOptimalFontSize(state.currentResponseText) + 'px';
        ui.scrollToBottom();
    },

    // Finalize the current response
    finalize() {
        const { state, ui } = Carl;

        if (state.currentResponseEl && state.currentResponseText) {
            const fontSize = this.findOptimalFontSize(state.currentResponseText);
            console.log(`Finalizing response: applying font size ${fontSize}px`);
            state.currentResponseEl.style.fontSize = fontSize + 'px';
            state.currentResponseEl = null;
            state.currentResponseText = '';
            ui.scrollToBottom();
        }

        state.resetStructuredState();
    },

    // Parse structured response JSON from the marker format
    parseStructured(text) {
        const { config } = Carl;

        if (!text.startsWith(config.STRUCTURED_RESPONSE_MARKER)) {
            return null;
        }

        const jsonStart = text.indexOf('{');
        const jsonEnd = text.lastIndexOf('}');

        if (jsonStart === -1 || jsonEnd === -1 || jsonEnd <= jsonStart) {
            return null;
        }

        try {
            const jsonStr = text.substring(jsonStart, jsonEnd + 1);
            const parsed = JSON.parse(jsonStr);

            if (Object.keys(parsed).length === 0) {
                return { empty: true };
            }

            return {
                question: parsed.q || '',
                answer: parsed.a || '',
                confidence: parsed.c || 0,
                empty: false
            };
        } catch (e) {
            console.error('Failed to parse structured response:', e);
            return null;
        }
    },

    // Count braces in text and update state depth
    countBraces(text) {
        const { state } = Carl;
        for (const char of text) {
            if (char === '{') state.structuredBraceDepth++;
            if (char === '}') state.structuredBraceDepth--;
        }
    },

    // Process incoming transcription text
    processTranscription(text) {
        const { state, config, ui } = Carl;

        // Check if this is the start of a structured response
        if (!state.isParsingStructured && text.includes(config.STRUCTURED_RESPONSE_MARKER)) {
            const markerIndex = text.indexOf(config.STRUCTURED_RESPONSE_MARKER);

            // Display any text before the marker
            const beforeMarker = text.substring(0, markerIndex);
            if (beforeMarker.trim()) {
                this.updateText(beforeMarker);
            }

            // Start parsing structured response
            state.isParsingStructured = true;
            state.pendingStructuredResponse = text.substring(markerIndex);
            state.structuredBraceDepth = 0;
            this.countBraces(state.pendingStructuredResponse);

            if (state.structuredBraceDepth === 0 && state.pendingStructuredResponse.includes('}')) {
                this.handleCompleteStructured();
            }
            return;
        }

        // Continue parsing a structured response
        if (state.isParsingStructured) {
            state.pendingStructuredResponse += text;
            this.countBraces(text);

            if (state.structuredBraceDepth === 0 && state.pendingStructuredResponse.includes('}')) {
                this.handleCompleteStructured();
            }
            return;
        }

        // Normal text - display directly
        this.updateText(text);
    },

    // Handle a complete structured response
    handleCompleteStructured() {
        const { state } = Carl;

        // Find where the JSON ends
        let braceCount = 0;
        let jsonEndIndex = -1;

        for (let i = 0; i < state.pendingStructuredResponse.length; i++) {
            if (state.pendingStructuredResponse[i] === '{') braceCount++;
            if (state.pendingStructuredResponse[i] === '}') {
                braceCount--;
                if (braceCount === 0) {
                    jsonEndIndex = i;
                    break;
                }
            }
        }

        const structuredPart = state.pendingStructuredResponse.substring(0, jsonEndIndex + 1);
        const afterStructured = state.pendingStructuredResponse.substring(jsonEndIndex + 1);

        console.log(`[MODEL] Complete structured response: ${structuredPart}`);
        if (afterStructured.trim()) {
            console.log(`[MODEL] Text after structured response: "${afterStructured.trim()}"`);
        }

        const parsed = this.parseStructured(structuredPart);

        // Reset parsing state
        state.isParsingStructured = false;
        state.pendingStructuredResponse = '';
        state.structuredBraceDepth = 0;

        if (parsed && !parsed.empty && parsed.question) {
            // Stop audio playback for the uncertain response
            state.clearAudioQueue();

            // Finalize any current response before verification
            if (state.currentResponseEl) {
                this.finalize();
            }

            console.log(`[MODEL] Uncertain (${parsed.confidence}%): "${parsed.question}" - MODEL answer: "${parsed.answer}"`);
            console.log(`[MODEL] Delegating to VERIFICATION_MODEL...`);

            this.verifyWithGeminiPro(parsed.question);
        } else if (parsed && parsed.empty) {
            console.log('[MODEL] Empty structured response - no verification needed');
        }

        // Process any text after the structured response
        if (afterStructured.trim()) {
            console.log(`[MODEL] Processing remaining text after structured response`);
            setTimeout(() => this.processTranscription(afterStructured), 100);
        }
    },

    // Call verification model for fact-checking
    async verifyWithGeminiPro(question) {
        const { state, config, ui } = Carl;

        const url = `${config.REST_URL}/${config.VERIFICATION_MODEL}:streamGenerateContent?key=${state.currentApiKey}&alt=sse`;

        const requestBody = {
            contents: [{
                role: 'user',
                parts: [{ text: question }]
            }],
            generationConfig: {
                maxOutputTokens: 1024
            },
            systemInstruction: {
                parts: [{
                    text: 'Answer the question directly and concisely. Provide accurate, factual information.'
                }]
            },
            tools: [
                { googleSearch: {} },
                { codeExecution: {} }
            ]
        };

        console.log(`[VERIFICATION_MODEL] Sending question: "${question}"`);

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                throw new Error(`VERIFICATION_MODEL API error: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            this.startNew();
            state.currentResponseEl.classList.add('verified');

            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    console.log(`[VERIFICATION_MODEL] Stream complete, total length: ${state.currentResponseText.length}`);
                    break;
                }

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const jsonStr = line.slice(6);
                        if (jsonStr === '[DONE]') continue;

                        try {
                            const data = JSON.parse(jsonStr);
                            const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
                            const groundingMetadata = data.candidates?.[0]?.groundingMetadata;

                            if (groundingMetadata) {
                                console.log('[VERIFICATION] Grounded answer with:', groundingMetadata);
                                state.currentResponseEl.classList.add('grounded');
                            }

                            if (text) {
                                const preview = text.substring(0, 100).replace(/\n/g, ' ');
                                console.log(`[VERIFICATION_MODEL] Received response: ${preview}${text.length > 100 ? '...' : ''}`);
                                this.updateText(text);
                            }
                        } catch (e) {
                            // Ignore parse errors for partial chunks
                        }
                    }
                }
            }

            this.finalize();
        } catch (error) {
            console.error('[VERIFICATION_MODEL] Verification failed:', error);
            if (!state.currentResponseEl) this.startNew();
            state.currentResponseText = `[Verification failed: ${error.message}]`;
            state.currentResponseEl.textContent = state.currentResponseText;
            this.finalize();
        }
    }
};
