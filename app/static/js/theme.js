/**
 * IMAGEKEY Theme Management Script
 * Handles Dark/Light mode switching, persistence via localStorage,
 * and system preference detection.
 */

(function () {
    const THEME_STORAGE_KEY = 'imagekey_theme';
    const htmlElement = document.documentElement;

    /**
     * Get preferred theme: stored theme -> system preference -> light
     */
    function getPreferredTheme() {
        const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);
        if (storedTheme === 'dark' || storedTheme === 'light') {
            return storedTheme;
        }
        // Luxury Obsidian & Champagne Gold is the default mobile/APK theme
        return 'dark';
    }

    /**
     * Apply theme to DOM and sync toggle button icons
     */
    function applyTheme(theme) {
        htmlElement.setAttribute('data-theme', theme);
        localStorage.setItem(THEME_STORAGE_KEY, theme);

        const toggleButtons = document.querySelectorAll('.btn-theme-toggle');
        toggleButtons.forEach(btn => {
            if (theme === 'dark') {
                btn.innerHTML = '☀️';
                btn.setAttribute('title', 'Switch to Light Mode');
                btn.setAttribute('aria-label', 'Switch to Light Mode');
            } else {
                btn.innerHTML = '🌙';
                btn.setAttribute('title', 'Switch to Dark Mode');
                btn.setAttribute('aria-label', 'Switch to Dark Mode');
            }
        });
    }

    /**
     * Toggle between dark and light
     */
    function toggleTheme() {
        const currentTheme = htmlElement.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        applyTheme(newTheme);
    }

    // Initialize theme immediately to prevent FOIT (Flash of Inverted Theme)
    const initialTheme = getPreferredTheme();
    applyTheme(initialTheme);

    // Bind event listeners when DOM is loaded
    document.addEventListener('DOMContentLoaded', () => {
        applyTheme(getPreferredTheme());

        document.querySelectorAll('.btn-theme-toggle').forEach(btn => {
            btn.addEventListener('click', toggleTheme);
        });

        // Listen for system theme changes
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
                if (!localStorage.getItem(THEME_STORAGE_KEY)) {
                    applyTheme(e.matches ? 'dark' : 'light');
                }
            });
        }
    });

    // Expose toggle function globally
    window.IMAGEKEY_THEME = {
        toggle: toggleTheme,
        apply: applyTheme,
        get: getPreferredTheme
    };

    /**
     * Mobile App Toast Notification
     */
    function showToast(message, type = 'info', duration = 2800) {
        let toast = document.getElementById('imagekey-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'imagekey-toast';
            toast.className = 'app-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.className = `app-toast show ${type}`;

        if (toast._timer) clearTimeout(toast._timer);
        toast._timer = setTimeout(() => {
            toast.className = 'app-toast';
        }, duration);
    }

    /**
     * Copy text to clipboard with fallback
     */
    async function copyText(text, successMessage = 'Copied to clipboard!') {
        if (!text) return;
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(text);
            } else {
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed';
                textArea.style.left = '-999999px';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
            }
            showToast(successMessage, 'success');
        } catch (err) {
            console.error('Copy failed:', err);
            showToast('Unable to copy to clipboard', 'warn');
        }
    }

    /**
     * Safe Image File Download
     */
    function downloadImage(publicUid) {
        if (!publicUid) return;
        const link = document.createElement('a');
        link.href = `/api/v1/images/${publicUid}/download`;
        link.download = `IMAGEKEY_${publicUid}.png`;
        link.target = '_blank';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        showToast('Starting image download...', 'info');
    }

    /**
     * Web Share API with mobile file share + desktop fallback
     */
    async function shareImageAndInfo(options) {
        const { uid, title, description } = options;
        const shareUrl = `${window.location.origin}/public/${uid}`;
        const cleanTitle = title || 'IMAGEKEY Visual Key';
        const shareText = `${cleanTitle}${description ? '\n' + description : ''}\n\nScan or verify on IMAGEKEY:\n${shareUrl}`;

        if (navigator.share) {
            try {
                let sharePayload = {
                    title: cleanTitle,
                    text: shareText,
                    url: shareUrl,
                };

                // Attempt to attach image file if supported
                if (navigator.canShare) {
                    try {
                        const imgRes = await fetch(`/api/v1/images/${uid}/download`);
                        if (imgRes.ok) {
                            const blob = await imgRes.blob();
                            const ext = blob.type.includes('png') ? 'png' : 'jpg';
                            const file = new File([blob], `IMAGEKEY_${uid}.${ext}`, { type: blob.type });
                            if (navigator.canShare({ files: [file] })) {
                                sharePayload.files = [file];
                            }
                        }
                    } catch (e) {
                        // Fall back to text + url
                    }
                }

                await navigator.share(sharePayload);
                showToast('Shared successfully!', 'success');
                return;
            } catch (err) {
                if (err.name === 'AbortError') return; // User closed share sheet
                console.warn('Web Share failed, using fallback:', err);
            }
        }

        // Desktop Fallback: Download Image + Copy text to clipboard
        await copyText(shareText, 'Details copied! Downloading image...');
        setTimeout(() => {
            downloadImage(uid);
        }, 300);
    }

    // Expose helpers globally
    window.IMAGEKEY_APP = {
        showToast,
        copyText,
        downloadImage,
        shareImageAndInfo
    };
    window.showToast = showToast;
    window.copyText = copyText;
    window.downloadImage = downloadImage;
    window.shareImageAndInfo = shareImageAndInfo;
})();
