// UI manipulation and DOM helpers
window.Carl = window.Carl || {};

Carl.ui = {
    // DOM element cache
    elements: {},
    scrollTimeout: null,

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

    // Scroll to position response wrapper top just below the fixed toolbar
    scrollToResponse(responseEl) {
        if (!responseEl || !window.gsap) return;

        // Debounce scroll updates - clear previous timeout
        if (this.scrollTimeout) {
            clearTimeout(this.scrollTimeout);
        }

        // Defer scroll calculation to batch updates and avoid interrupting ongoing scrolls
        this.scrollTimeout = setTimeout(() => {
            this.scrollTimeout = null;

            // Use requestAnimationFrame to ensure layout is complete after font size changes
            requestAnimationFrame(() => {
                const rect = responseEl.getBoundingClientRect();
                // If user scrolled up significantly (response well above viewport), don't auto-scroll
                if (rect.top > window.innerHeight + 200) return;

                // Get the wrapper and calculate scroll target to position its top just below toolbar
                const wrapper = responseEl.parentElement;
                const wrapperTop = wrapper.offsetTop;
                const toolbarHeight = this.elements.toolbar.offsetHeight;
                const scrollTarget = Math.max(0, wrapperTop - toolbarHeight);

                // Kill any existing scroll animation and start fresh
                gsap.killTweensOf(window);
                gsap.to(window, {
                    scrollTo: { y: scrollTarget },
                    duration: 1.5,
                    ease: 'none'
                });
            });
        }, 100); // 100ms debounce to batch transcription chunks
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
