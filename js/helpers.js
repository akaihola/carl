// Shared utility functions
window.Carl = window.Carl || {};

Carl.helpers = {
    // Format timestamp with full locale options
    formatTimestamp(date = new Date()) {
        return date.toLocaleString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            timeZoneName: 'short'
        });
    },

    // Resample audio from source sample rate to 16kHz
    resampleTo16kHz(float32Array, fromSampleRate) {
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
    },

    // Convert Float32Array to 16-bit PCM ArrayBuffer
    floatTo16BitPCM(float32Array) {
        const buffer = new ArrayBuffer(float32Array.length * 2);
        const view = new DataView(buffer);
        for (let i = 0; i < float32Array.length; i++) {
            const s = Math.max(-1, Math.min(1, float32Array[i]));
            view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        }
        return buffer;
    },

    // Convert ArrayBuffer to base64 string
    arrayBufferToBase64(buffer) {
        let binary = '';
        const bytes = new Uint8Array(buffer);
        const len = bytes.byteLength;
        for (let i = 0; i < len; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return window.btoa(binary);
    },

    // Convert base64 string to ArrayBuffer
    base64ToArrayBuffer(base64) {
        const binaryString = atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return bytes.buffer;
    }
};
