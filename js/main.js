// Main entry point - initialization and global event handlers
window.Carl = window.Carl || {};

// Expose functions to global scope for HTML onclick handlers
window.toggleConnection = () => Carl.connection.toggle();
window.toggleMenu = () => Carl.ui.toggleMenu();
window.closeMenu = () => Carl.ui.closeMenu();
window.closeMenuOnBackdrop = (e) => Carl.ui.closeMenuOnBackdrop(e);
window.submitApiKey = () => Carl.apiKey.submit();
window.clearApiKey = () => Carl.apiKey.clear();

// API key management
Carl.apiKey = {
    submit() {
        const { state, config, ui } = Carl;
        const key = ui.getApiKeyInputValue();

        if (!key) {
            alert('Please enter an API Key');
            return;
        }

        localStorage.setItem(config.API_KEY_STORAGE_KEY, key);
        state.currentApiKey = key;
        ui.clearApiKeyInput();
        ui.showConnectButton();
    },

    clear() {
        const { state, config, ui } = Carl;

        if (confirm('Are you sure you want to clear the saved API key?')) {
            localStorage.removeItem(config.API_KEY_STORAGE_KEY);
            state.currentApiKey = null;
            ui.showApiKeyInput();
        }
    }
};

// Initialize application
Carl.init = function() {
    const { state, config, ui } = Carl;

    // Initialize UI element references
    ui.init();

    // Load saved API key
    const savedKey = localStorage.getItem(config.API_KEY_STORAGE_KEY);
    if (savedKey) {
        state.currentApiKey = savedKey;
        ui.showConnectButton();
    } else {
        ui.showApiKeyInput();
    }

    // Global Enter key handler
    document.addEventListener('keydown', (e) => {
        console.log('keydown:', e.key, 'activeElement:', document.activeElement?.tagName, document.activeElement?.id);

        if (e.key === 'Enter' && state.isConnected()) {
            const activeEl = document.activeElement;
            const isInputFocused = activeEl && (
                activeEl.tagName === 'INPUT' ||
                activeEl.tagName === 'TEXTAREA' ||
                activeEl.tagName === 'BUTTON'
            );

            console.log('Enter pressed, isInputFocused:', isInputFocused);
            if (!isInputFocused) {
                e.preventDefault();
                Carl.connection.sendTextMessage('Tell me another intriguing fact.');
            }
        }
    });
};

// Run initialization when DOM is ready
window.addEventListener('DOMContentLoaded', () => Carl.init());
