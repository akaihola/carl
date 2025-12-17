// UI manipulation and DOM helpers
window.Carl = window.Carl || {};

Carl.ui = {
    // DOM element cache
    elements: {},

    // Initialize element references
    init() {
        this.elements = {
            menu: document.getElementById('menu'),
            menuBtn: document.getElementById('menuBtn'),
            controls: document.getElementById('controls'),
            apiKeySection: document.getElementById('apiKeySection'),
            apiKeyInput: document.getElementById('apiKey'),
            connectBtn: document.getElementById('connectBtn'),
            clearApiKeyBtn: document.getElementById('clearApiKeyBtn'),
            systemPrompt: document.getElementById('systemPrompt'),
            toolbar: document.getElementById('toolbar'),
            log: document.getElementById('log')
        };
    },

    // Menu functions
    toggleMenu() {
        this.elements.menu.classList.toggle('open');
        this.elements.menuBtn.classList.toggle('active');
    },

    closeMenu() {
        this.elements.menu.classList.remove('open');
        this.elements.menuBtn.classList.remove('active');
    },

    closeMenuOnBackdrop(event) {
        if (event.target.id === 'menu') {
            this.closeMenu();
        }
    },

    // API key UI states
    showApiKeyInput() {
        this.elements.controls.classList.remove('hidden');
        this.elements.apiKeySection.style.display = 'flex';
        this.elements.connectBtn.style.display = 'none';
        this.elements.clearApiKeyBtn.style.display = 'none';
    },

    showConnectButton() {
        this.elements.controls.classList.add('hidden');
        this.elements.apiKeySection.style.display = 'none';
        this.elements.connectBtn.style.display = 'inline-block';
        this.elements.clearApiKeyBtn.style.display = 'inline-block';
    },

    // Connection button state
    setConnected(connected) {
        this.elements.connectBtn.textContent = connected ? 'Disconnect' : 'Connect & Start';
    },

    blurConnectButton() {
        this.elements.connectBtn.blur();
    },

    // Scroll management
    scrollToBottom() {
        const { state } = Carl;
        if (state.userHasScrolledUp) return;

        requestAnimationFrame(() => {
            state.isProgrammaticScrolling = true;
            clearTimeout(state.scrollEndTimeout);
            window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' });
            state.scrollEndTimeout = setTimeout(() => { state.isProgrammaticScrolling = false; }, 1000);
        });
    },

    // Check if user is at bottom of page
    isAtBottom() {
        return (window.innerHeight + window.scrollY) >= (document.documentElement.scrollHeight - 10);
    },

    // Get system prompt value
    getSystemPrompt() {
        return this.elements.systemPrompt.value;
    },

    // Get API key input value
    getApiKeyInputValue() {
        return this.elements.apiKeyInput.value.trim();
    },

    // Clear API key input
    clearApiKeyInput() {
        this.elements.apiKeyInput.value = '';
    }
};
