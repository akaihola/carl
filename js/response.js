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

        const wrapper = document.createElement('div');
        wrapper.className = 'response-wrapper';

        state.currentResponseEl = document.createElement('div');
        state.currentResponseEl.className = 'response';
        state.currentResponseEl.style.visibility = 'visible';

        wrapper.appendChild(state.currentResponseEl);
        ui.elements.log.appendChild(wrapper);
    },

    // Update current response with text and recalculate font size
    updateText(text) {
        const { state, ui } = Carl;
        if (!state.currentResponseEl) this.startNew();

        const isFirstUpdate = state.currentResponseText === '';
        state.currentResponseText += text;
        state.currentResponseEl.textContent = state.currentResponseText;

        const fontSize = this.findOptimalFontSize(state.currentResponseText);

        if (isFirstUpdate) {
            // Disable transition for initial render to prevent jitter
            state.currentResponseEl.style.transition = 'none';
            state.currentResponseEl.style.fontSize = fontSize + 'px';
            state.currentResponseEl.offsetHeight; // Force reflow
            state.currentResponseEl.style.transition = '';
        } else {
            state.currentResponseEl.style.fontSize = fontSize + 'px';
        }

        ui.scrollToResponse(state.currentResponseEl);
    },

    // Finalize the current response
    finalize() {
        const { state, ui } = Carl;

        if (state.currentResponseEl && state.currentResponseText) {
            const fontSize = this.findOptimalFontSize(state.currentResponseText);
            console.log(`Finalizing response: applying font size ${fontSize}px`);
            state.currentResponseEl.style.fontSize = fontSize + 'px';

            // Do a final scroll after font size is applied and layout is settled
            const responseEl = state.currentResponseEl;
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    ui.scrollToResponse(responseEl);
                });
            });

            state.currentResponseEl = null;
            state.currentResponseText = '';
        }
    },


    // Process incoming transcription text
    processTranscription(text) {
        const { state, facts } = Carl;

        // Parse Qn:/An: format silently (Flash 2.0 fact-checker output)
        if (facts.hasFactFormat(text)) {
            facts.parseAndStore(text);
            // Do NOT display Qn:/An: format to user
            return;
        }

        // Normal text - display directly (verification model responses)
        this.updateText(text);
    },

    // Verify next fact in queue (one at a time)
    async verifyNextFact() {
        const { state, config } = Carl;

        // Check if already verifying
        if (state.isVerificationInProgress()) {
            console.log('[VERIFICATION] Already verifying a fact, skipping');
            return;
        }

        // Get next fact to verify
        const factNumber = state.getNextVerification();
        if (!factNumber) {
            console.log('[VERIFICATION] No facts in queue to verify');
            return;
        }

        const fact = state.facts.mapping[factNumber];
        if (!fact || !fact.q || !fact.a) {
            console.log(`[VERIFICATION] Fact ${factNumber} incomplete, skipping`);
            state.removeFact(factNumber);
            state.completeVerification();
            // Try next fact
            setTimeout(() => this.verifyNextFact(), 100);
            return;
        }

        await this.verifyWithGeminiPro(factNumber, fact.q, fact.a);
    },

    // Call verification model for fact-checking
    async verifyWithGeminiPro(factNumber, question, conversationAnswer) {
        const { state, config } = Carl;

        const url = `${config.REST_URL}/${config.VERIFICATION_MODEL}:streamGenerateContent?key=${state.currentApiKey}&alt=sse`;

        const promptText = `Question: ${question}\nUser's Answer: ${conversationAnswer}\n\nPlease verify if this answer is correct.`;

        const requestBody = {
            contents: [{
                role: 'user',
                parts: [{ text: promptText }]
            }],
            generationConfig: {
                maxOutputTokens: 1024
            },
            systemInstruction: {
                parts: [{
                    text: config.VERIFICATION_SYSTEM_PROMPT
                }]
            },
            tools: [
                { googleSearch: {} },
                { codeExecution: {} }
            ]
        };

        console.log(`[VERIFICATION] Q${factNumber}: "${question}", Answer: "${conversationAnswer}"`);

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

            let verificationText = '';
            this.startNew();

            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    console.log(`[VERIFICATION] Complete for Q${factNumber}: ${verificationText.substring(0, 100)}`);
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
                                console.log('[VERIFICATION] Grounded with:', groundingMetadata);
                            }

                            if (text) {
                                verificationText += text;
                                this.updateText(text);
                            }
                        } catch (e) {
                            // Ignore parse errors for partial chunks
                        }
                    }
                }
            }

            this.finalize();

            // Check if first word is "CORRECT"
            const firstWord = verificationText.trim().split(/\s+/)[0].toLowerCase();
            if (firstWord === 'correct') {
                state.facts.mapping[factNumber].f = 'CORRECT';
                console.log(`[VERIFICATION] Q${factNumber} marked CORRECT`);
            } else {
                state.facts.mapping[factNumber].f = verificationText;
                console.log(`[VERIFICATION] Q${factNumber} fact updated`);
            }

            // Remove from queue and complete verification
            state.removeFact(factNumber);
            state.completeVerification();

            // Try next fact
            setTimeout(() => this.verifyNextFact(), 100);
        } catch (error) {
            console.error('[VERIFICATION] Verification failed:', error);
            this.startNew();
            state.currentResponseText = `[Verification failed: ${error.message}]`;
            state.currentResponseEl.textContent = state.currentResponseText;
            this.finalize();

            state.removeFact(factNumber);
            state.completeVerification();

            // Try next fact
            setTimeout(() => this.verifyNextFact(), 500);
        }
    }
};
