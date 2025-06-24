document.addEventListener('DOMContentLoaded', () => {
    const startButton = document.getElementById('start-button');
    const stopButton = document.getElementById('stop-button');
    const transcriptionTicker = document.getElementById('transcription-ticker');
    const llmInsightsContainer = document.getElementById('llm-insights-container');

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

            // Setup WebRTC for audio streaming
            await setupWebRTC();
            
        } catch (error) {
            console.error('Error starting voice assistant:', error);
            alert('Failed to start voice assistant. Check console for details.');
            stopVoiceAssistant();
        }
    }

    async function sendOfferToBackend(offer) {
        try {
            const response = await fetch('/api/offer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    sdp: offer.sdp,
                    type: offer.type
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const answer = await response.json();
            return answer;
        } catch (error) {
            console.error('Error sending offer to backend:', error);
            throw error;
        }
    }

    async function setupWebRTC() {
        try {
            // Get user media (microphone)
            console.log('🎤 Requesting microphone access...');
            localStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: 16000,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
            console.log('✓ Microphone access granted:', localStream.getTracks().length, 'tracks');

            // Create peer connection
            console.log('🔗 Creating WebRTC peer connection...');
            peerConnection = new RTCPeerConnection({
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' }
                ]
            });

            // Add local stream to peer connection
            localStream.getTracks().forEach(track => {
                console.log('📤 Adding track to peer connection:', track.kind, track.enabled);
                peerConnection.addTrack(track, localStream);
            });

            // Create data channel for receiving transcription and LLM responses
            console.log('📡 Creating data channel...');
            const dataChannel = peerConnection.createDataChannel('data', {
                ordered: true
            });
            
            dataChannel.onopen = () => {
                console.log('📡 Data channel opened');
            };
            
            dataChannel.onmessage = (event) => {
                console.log('📡 Data channel message:', event.data);
                try {
                    const data = JSON.parse(event.data);
                    handleDataChannelMessage(data);
                } catch (error) {
                    console.error('Error parsing data channel message:', error);
                }
            };
            
            dataChannel.onclose = () => {
                console.log('📡 Data channel closed');
            };
            
            dataChannel.onerror = (error) => {
                console.error('📡 Data channel error:', error);
            };

            // Handle ICE candidates
            peerConnection.onicecandidate = (event) => {
                if (event.candidate) {
                    console.log('ICE candidate:', event.candidate);
                }
            };

            // Handle remote stream
            peerConnection.ontrack = (event) => {
                console.log('📺 Received remote stream:', event.streams[0]);
                console.log('📺 Remote stream tracks:', event.streams[0].getTracks().map(t => t.kind));
                const remoteAudio = document.createElement('audio');
                remoteAudio.srcObject = event.streams[0];
                remoteAudio.autoplay = true;
                remoteAudio.volume = 1.0;
                document.body.appendChild(remoteAudio);
                console.log('📺 Remote audio element added to DOM');
            };


            // Create and send offer
            console.log('📝 Creating WebRTC offer...');
            const offer = await peerConnection.createOffer();
            await peerConnection.setLocalDescription(offer);
            console.log('📝 Local description set, sending offer to backend...');
            
            const answer = await sendOfferToBackend(offer);
            console.log('📝 Received answer from backend:', answer ? 'SUCCESS' : 'FAILED');
            
            if (answer && answer.sdp) {
                await peerConnection.setRemoteDescription(new RTCSessionDescription(answer));
                console.log('✅ WebRTC connection established');
                isConnected = true;
                displayStatus('Voice assistant connected via WebRTC');
            }

        } catch (error) {
            console.error('Error setting up WebRTC:', error);
            throw error;
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

    function handleDataChannelMessage(data) {
        console.log('📡 Processing message:', data);
        
        switch (data.type) {
            case 'transcription':
                updateTranscription(data.text, true);
                break;
            case 'llm_response':
                updateLLMInsight(data.text);
                break;
            case 'status':
                console.log('📡 Status update:', data.message);
                break;
            default:
                console.warn('📡 Unknown message type:', data.type);
        }
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
        
        isConnected = false;
        displayStatus('Voice assistant stopped');
    }

    // Handle page unload
    window.addEventListener('beforeunload', () => {
        stopVoiceAssistant();
    });
});