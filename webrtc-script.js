document.addEventListener('DOMContentLoaded', () => {
    const startButton = document.getElementById('start-button');
    const stopButton = document.getElementById('stop-button');
    const transcriptionTicker = document.getElementById('transcription-ticker');
    const llmInsightsContainer = document.getElementById('llm-insights-container');

    let websocket = null;
    let peerConnection = null;
    let localStream = null;
    let isConnected = false;

    startButton.addEventListener('click', startVoiceAssistant);
    stopButton.addEventListener('click', stopVoiceAssistant);

    async function startVoiceAssistant() {
        try {
            startButton.disabled = true;
            stopButton.disabled = false;
            
            transcriptionTicker.textContent = '';
            llmInsightsContainer.textContent = '';

            // Connect to Pipecat backend via WebSocket
            await connectToBackend();
            
            // Setup WebRTC for audio streaming
            await setupWebRTC();
            
        } catch (error) {
            console.error('Error starting voice assistant:', error);
            alert('Failed to start voice assistant. Check console for details.');
            stopVoiceAssistant();
        }
    }

    async function connectToBackend() {
        return new Promise((resolve, reject) => {
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
            
            websocket = new WebSocket(wsUrl);
            
            websocket.onopen = () => {
                console.log('Connected to Pipecat backend');
                isConnected = true;
                resolve();
            };
            
            websocket.onmessage = handleBackendMessage;
            
            websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                reject(error);
            };
            
            websocket.onclose = () => {
                console.log('WebSocket connection closed');
                isConnected = false;
            };
        });
    }

    function handleBackendMessage(event) {
        try {
            const data = JSON.parse(event.data);
            
            switch (data.type) {
                case 'connection':
                    console.log('Backend connection status:', data.status);
                    displayStatus(data.message);
                    break;
                    
                case 'transcription':
                    updateTranscription(data.text, data.is_final);
                    break;
                    
                case 'llm_insight':
                    updateLLMInsight(data.text);
                    break;
                    
                case 'webrtc_answer':
                    handleWebRTCAnswer(data.answer);
                    break;
                    
                case 'error':
                    console.error('Backend error:', data.message);
                    displayError(data.message);
                    break;
                    
                default:
                    console.log('Unknown message type:', data.type);
            }
        } catch (error) {
            console.error('Error parsing backend message:', error);
        }
    }

    async function setupWebRTC() {
        try {
            // Get user media (microphone)
            localStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: 16000,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            // Create peer connection
            peerConnection = new RTCPeerConnection({
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' }
                ]
            });

            // Add local stream to peer connection
            localStream.getTracks().forEach(track => {
                peerConnection.addTrack(track, localStream);
            });

            // Handle ICE candidates
            peerConnection.onicecandidate = (event) => {
                if (event.candidate && websocket && isConnected) {
                    websocket.send(JSON.stringify({
                        type: 'ice_candidate',
                        candidate: event.candidate
                    }));
                }
            };

            // Create and send offer
            const offer = await peerConnection.createOffer();
            await peerConnection.setLocalDescription(offer);
            
            if (websocket && isConnected) {
                websocket.send(JSON.stringify({
                    type: 'webrtc_offer',
                    offer: offer
                }));
            }

            displayStatus('Audio streaming connected');
            
        } catch (error) {
            console.error('Error setting up WebRTC:', error);
            throw error;
        }
    }

    async function handleWebRTCAnswer(answer) {
        try {
            if (peerConnection) {
                await peerConnection.setRemoteDescription(new RTCSessionDescription(answer));
                console.log('WebRTC answer handled successfully');
            }
        } catch (error) {
            console.error('Error handling WebRTC answer:', error);
        }
    }

    function updateTranscription(text, isFinal) {
        if (isFinal) {
            // Add final transcription with a space
            transcriptionTicker.textContent += text + ' ';
            
            // Auto-scroll to show latest text
            transcriptionTicker.scrollLeft = transcriptionTicker.scrollWidth;
        } else {
            // Show partial transcription in a different style
            console.log('Partial transcription:', text);
        }
    }

    function updateLLMInsight(text) {
        if (!text) return;
        
        // Create or update insight element
        let insightElement = llmInsightsContainer.querySelector('.current-insight');
        if (!insightElement) {
            insightElement = document.createElement('div');
            insightElement.className = 'current-insight';
            llmInsightsContainer.appendChild(insightElement);
        }
        
        // Stream the text (append new chunks)
        insightElement.textContent += text;
        
        // Auto-scroll insight container
        llmInsightsContainer.scrollTop = llmInsightsContainer.scrollHeight;
    }

    function displayStatus(message) {
        console.log('Status:', message);
        // You could add a status display element to show connection status
    }

    function displayError(message) {
        console.error('Error:', message);
        // Show error in the insights container
        llmInsightsContainer.innerHTML = `<div class="error">Error: ${message}</div>`;
    }

    function stopVoiceAssistant() {
        startButton.disabled = false;
        stopButton.disabled = true;
        
        // Close WebRTC connection
        if (peerConnection) {
            peerConnection.close();
            peerConnection = null;
        }
        
        // Stop local media stream
        if (localStream) {
            localStream.getTracks().forEach(track => track.stop());
            localStream = null;
        }
        
        // Close WebSocket connection
        if (websocket) {
            websocket.close();
            websocket = null;
        }
        
        isConnected = false;
        displayStatus('Voice assistant stopped');
    }

    // Handle page unload
    window.addEventListener('beforeunload', () => {
        stopVoiceAssistant();
    });
});