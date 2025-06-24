document.addEventListener('DOMContentLoaded', () => {
    const assemblyaiApiKeyInput = document.getElementById('assemblyai-api-key');
    const llmApiKeyInput = document.getElementById('llm-api-key');
    const startButton = document.getElementById('start-button');
    const stopButton = document.getElementById('stop-button');
    const transcriptionTicker = document.getElementById('transcription-ticker');
    const llmInsightsContainer = document.getElementById('llm-insights-container');

    let recorder;
    let socket;

    // Load API keys from localStorage
    assemblyaiApiKeyInput.value = localStorage.getItem('assemblyaiApiKey') || '';
    llmApiKeyInput.value = localStorage.getItem('llmApiKey') || '';

    // Save API keys to localStorage on input change
    assemblyaiApiKeyInput.addEventListener('change', () => {
        localStorage.setItem('assemblyaiApiKey', assemblyaiApiKeyInput.value);
    });

    llmApiKeyInput.addEventListener('change', () => {
        localStorage.setItem('llmApiKey', llmApiKeyInput.value);
    });

    startButton.addEventListener('click', startTranscription);
    stopButton.addEventListener('click', stopTranscription);

    async function startTranscription() {
        const assemblyaiApiKey = assemblyaiApiKeyInput.value;
        if (!assemblyaiApiKey) {
            alert('Please enter your AssemblyAI API key.');
            return;
        }

        startButton.disabled = true;
        stopButton.disabled = false;

        try {
            // DIAGNOSTIC LOGGING - Let's validate our assumptions
            console.log('🔍 DIAGNOSTIC: Starting token request');
            console.log('🔍 DIAGNOSTIC: API Key length:', assemblyaiApiKey ? assemblyaiApiKey.length : 'undefined');
            console.log('🔍 DIAGNOSTIC: Request origin:', window.location.origin);
            console.log('🔍 DIAGNOSTIC: User agent:', navigator.userAgent.substring(0, 50));
            
            // This is a simplified implementation based on the AssemblyAI documentation.
            // A full implementation would require handling tokens for authentication.
            // For this MVP, we are assuming a direct WebSocket connection which may require
            // a backend to securely generate a temporary token. [3, 16]
            // The official AssemblyAI browser example uses a server for this.
            // Ref: https://github.com/AssemblyAI/realtime-transcription-browser-js-example [3]

            // Try different authorization header formats for diagnosis
            const authHeaders = {
                'Authorization': assemblyaiApiKey,
                'Content-Type': 'application/json'
            };
            console.log('🔍 DIAGNOSTIC: Request headers:', authHeaders);

            const response = await fetch('https://api.assemblyai.com/v2/realtime/token', {
                method: 'POST',
                headers: authHeaders
            });

            console.log('🔍 DIAGNOSTIC: Response status:', response.status);
            console.log('🔍 DIAGNOSTIC: Response headers:', [...response.headers.entries()]);
            console.log('🔍 DIAGNOSTIC: Response ok:', response.ok);
            
            if (!response.ok) {
                const responseText = await response.text();
                console.log('🔍 DIAGNOSTIC: Response body:', responseText);
                console.log('🔍 DIAGNOSTIC: CORS headers check:');
                console.log('  - Access-Control-Allow-Origin:', response.headers.get('Access-Control-Allow-Origin'));
                console.log('  - Access-Control-Allow-Methods:', response.headers.get('Access-Control-Allow-Methods'));
                console.log('  - Access-Control-Allow-Headers:', response.headers.get('Access-Control-Allow-Headers'));
                throw new Error(`Failed to get temporary token. Status: ${response.status}, Body: ${responseText}`);
            }

            const data = await response.json();
            console.log('🔍 DIAGNOSTIC: Response data:', data);
            const token = data.token;


            socket = new WebSocket(`wss://api.assemblyai.com/v2/realtime/ws?token=${token}`);

            socket.onmessage = (message) => {
                const res = JSON.parse(message.data);
                if (res.message_type === 'FinalTranscript') {
                    const newText = res.text + ' ';
                    transcriptionTicker.textContent += newText;

                    // Placeholder for LLM Insight Logic
                    // 1. Take the full text from transcriptionTicker.textContent
                    // 2. Send it to the LLM API
                    // 3. Display the result in llmInsightsContainer
                    console.log('Utterance complete. Full transcript:', transcriptionTicker.textContent);
                    // getLlmInsight(transcriptionTicker.textContent);
                } else if(res.message_type === 'PartialTranscript') {
                    // This is where you would handle the continuously updating transcript
                    // for the "news ticker" effect. For now, we just log it.
                    // To implement the ticker, you'd update an element's content here.
                    console.log('Partial transcript:', res.text);
                }
            };

            socket.onerror = (event) => {
                console.error('WebSocket error:', event);
                stopTranscription();
            };

            socket.onclose = (event) => {
                console.log('WebSocket closed:', event);
                socket = null;
            };

            socket.onopen = async () => {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                recorder = new MediaRecorder(stream);
                recorder.ondataavailable = (event) => {
                    if (event.data.size > 0 && socket && socket.readyState === 1) {
                         const message = {
                            "audio_data": event.data.toString('base64')
                        };
                        socket.send(JSON.stringify(message));
                    }
                };
                recorder.start(1000); // Send data every second
            };


        } catch (error) {
            console.log('🔍 DIAGNOSTIC: Caught error type:', error.constructor.name);
            console.log('🔍 DIAGNOSTIC: Error message:', error.message);
            console.log('🔍 DIAGNOSTIC: Full error:', error);
            
            if (error.name === 'TypeError' && error.message.includes('NetworkError')) {
                console.log('🔍 DIAGNOSTIC: This is a CORS/Network error - confirms browser CORS restriction');
            }
            
            console.error('Error starting transcription:', error);
            alert('Failed to start transcription. Check the console for details.');
            stopTranscription();
        }
    }

    function stopTranscription() {
        if (recorder) {
            recorder.stop();
            recorder = null;
        }
        if (socket) {
            socket.close();
        }

        startButton.disabled = false;
        stopButton.disabled = true;
    }

    // Placeholder function for where the LLM integration logic will go.
    async function getLlmInsight(text) {
        const llmApiKey = llmApiKeyInput.value;
        if (!llmApiKey) {
            console.warn('LLM API key not set.');
            return;
        }

        llmInsightsContainer.textContent = 'Getting insight...';

        // LLM API call logic will go here.
        // Example using fetch to a hypothetical LLM API endpoint. [1, 4]
        try {
            /*
            const response = await fetch('LLM_API_ENDPOINT', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${llmApiKey}`
                },
                body: JSON.stringify({
                    prompt: `Provide a brief insight into this conversation:\n\n${text}`
                })
            });
            const data = await response.json();
            llmInsightsContainer.textContent = data.insight;
            */
            llmInsightsContainer.textContent = "Insight will appear here."; // Placeholder
        } catch (error) {
            console.error('Error getting LLM insight:', error);
            llmInsightsContainer.textContent = 'Could not get insight.';
        }
    }

    // Placeholder for where the news ticker animation logic will go.
    // This could be a CSS animation triggered by a class,
    // or a JavaScript-based animation. [2, 6]
    function updateNewsTicker() {
        // Logic to make the text in `transcriptionTicker` scroll.
    }

});
