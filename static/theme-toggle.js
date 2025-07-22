// Dark mode toggle functionality
(function() {
    'use strict';
    
    // Constants for theme management
    const THEME_KEY = 'preferred-theme';
    const THEME_ATTR = 'data-theme';
    
    // Theme detection and initialization
    function getSystemTheme() {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    
    function getStoredTheme() {
        return localStorage.getItem(THEME_KEY);
    }
    
    function setTheme(theme) {
        document.documentElement.setAttribute(THEME_ATTR, theme);
        localStorage.setItem(THEME_KEY, theme);
        updateToggleButton(theme);
        updateUtterancesTheme(theme);
    }
    
    function getCurrentTheme() {
        return document.documentElement.getAttribute(THEME_ATTR) || getSystemTheme();
    }
    
    function toggleTheme() {
        const currentTheme = getCurrentTheme();
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
    }
    
    function updateToggleButton(theme) {
        const lightOption = document.getElementById('theme-light');
        const darkOption = document.getElementById('theme-dark');
        
        if (lightOption && darkOption) {
            if (theme === 'dark') {
                lightOption.classList.remove('active');
                darkOption.classList.add('active');
            } else {
                lightOption.classList.add('active');
                darkOption.classList.remove('active');
            }
        }
    }
    
    function updateUtterancesTheme(theme) {
        // Update Utterances theme by sending a message to the iframe
        const utterancesFrame = document.querySelector('iframe[src*="utteranc.es"]');
        if (utterancesFrame) {
            const utterancesTheme = theme === 'dark' ? 'github-dark' : 'github-light';
            utterancesFrame.contentWindow.postMessage(
                { type: 'set-theme', theme: utterancesTheme },
                'https://utteranc.es'
            );
        }
    }
    
    function initializeUtterances() {
        // Look for comments sections that need Utterances initialization
        const commentsSections = document.querySelectorAll('.comments-section');
        commentsSections.forEach(section => {
            const existingScript = section.querySelector('script[src*="utteranc.es"]');
            const existingIframe = section.querySelector('iframe[src*="utteranc.es"]');
            
            // Only initialize if script exists but iframe doesn't (meaning script didn't execute)
            if (existingScript && !existingIframe) {
                // Get script attributes
                const repo = existingScript.getAttribute('repo');
                const issueTerm = existingScript.getAttribute('issue-term');
                const label = existingScript.getAttribute('label');
                const currentTheme = getCurrentTheme();
                const theme = currentTheme === 'dark' ? 'github-dark' : 'github-light';
                
                // Remove the non-working script
                existingScript.remove();
                
                // Create and configure new script
                const newScript = document.createElement('script');
                newScript.src = 'https://utteranc.es/client.js';
                newScript.setAttribute('repo', repo);
                newScript.setAttribute('issue-term', issueTerm);
                newScript.setAttribute('label', label);
                newScript.setAttribute('theme', theme);
                newScript.setAttribute('crossorigin', 'anonymous');
                newScript.async = true;
                
                // Append to the comments section
                section.appendChild(newScript);
            }
        });
    }
    
    function createToggleButton() {
        // Find footer element to append theme toggle
        const footer = document.querySelector('footer');
        if (!footer) return null;
        
        // Create theme toggle container
        const toggleContainer = document.createElement('div');
        toggleContainer.className = 'theme-toggle-container';
        
        // Create the toggle text with options
        toggleContainer.innerHTML = `
            <span class="theme-toggle-text">[ 
                <span id="theme-light" class="theme-option">light mode</span> | 
                <span id="theme-dark" class="theme-option">dark mode</span> 
            ]</span>
        `;
        
        // Add click handlers
        const lightOption = toggleContainer.querySelector('#theme-light');
        const darkOption = toggleContainer.querySelector('#theme-dark');
        
        lightOption.addEventListener('click', () => setTheme('light'));
        darkOption.addEventListener('click', () => setTheme('dark'));
        
        // Add keyboard support
        lightOption.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setTheme('light');
            }
        });
        
        darkOption.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setTheme('dark');
            }
        });
        
        // Make options focusable
        lightOption.setAttribute('tabindex', '0');
        darkOption.setAttribute('tabindex', '0');
        
        footer.appendChild(toggleContainer);
        return toggleContainer;
    }
    
    function initializeTheme() {
        // Check if theme is already set manually
        const storedTheme = getStoredTheme();
        const systemTheme = getSystemTheme();
        
        // Use stored theme if available, otherwise use system preference
        const initialTheme = storedTheme || systemTheme;
        
        // Apply the theme
        document.documentElement.setAttribute(THEME_ATTR, initialTheme);
        
        // Create toggle button
        const toggleButton = createToggleButton();
        updateToggleButton(initialTheme);
        
        // Update Utterances theme after a short delay to ensure iframe is loaded
        setTimeout(() => updateUtterancesTheme(initialTheme), 1000);
        
        // Listen for system theme changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
            // Only update if user hasn't manually set a preference
            if (!getStoredTheme()) {
                const newTheme = e.matches ? 'dark' : 'light';
                document.documentElement.setAttribute(THEME_ATTR, newTheme);
                updateToggleButton(newTheme);
                updateUtterancesTheme(newTheme);
            }
        });
    }
    
    // Make initializeUtterances available globally for password-protected content
    window.initializeUtterances = initializeUtterances;
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeTheme);
    } else {
        initializeTheme();
    }
    
})();