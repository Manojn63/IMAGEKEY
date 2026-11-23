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

    /**
     * ==============================================================================
     * IMAGEKEY CENTRALIZED API CONFIGURATION & RESILIENT AUTO-SYNC ENGINE
     * ==============================================================================
     */

    const DEFAULT_TUNNEL_URL = 'https://artist-pamela-ratios-logging.trycloudflare.com';
    const SYNC_INTERVAL_MS = 12000; // 12 seconds

    /**
     * Resolves the active base URL for API communication with support for tunnel overrides.
     */
    function getApiBaseUrl() {
        const override = window.IMAGEKEY_API_BASE_URL || localStorage.getItem('imagekey_api_base_url');
        if (override) return override.replace(/\/+$/, '');

        const origin = window.location.origin;
        if (origin && !origin.startsWith('file://')) {
            return origin;
        }
        return DEFAULT_TUNNEL_URL;
    }

    /**
     * Resilient fetch wrapper with cache-busting and automatic retry on startup/tunnel delay.
     */
    const originalFetch = window.fetch ? window.fetch.bind(window) : null;

    async function apiFetch(input, init = {}, retries = 2) {
        let url = input;
        if (typeof input === 'string' && input.startsWith('/')) {
            const base = getApiBaseUrl();
            url = `${base}${input}`;
        }

        const options = { ...init };
        options.cache = 'no-store'; // Strict anti-stale

        const headers = new Headers(options.headers || {});
        headers.set('Cache-Control', 'no-cache, no-store, must-revalidate');
        headers.set('Pragma', 'no-cache');
        headers.set('Expires', '0');
        headers.set('X-Requested-With', 'IMAGEKEY-Client');
        options.headers = headers;

        let attempt = 0;
        while (true) {
            try {
                const response = await originalFetch(url, options);
                return response;
            } catch (error) {
                attempt++;
                if (attempt > retries) {
                    console.error(`[IMAGEKEY-API] Request failed after ${attempt} attempts:`, url, error);
                    throw error;
                }
                const backoffMs = attempt * 600;
                console.warn(`[IMAGEKEY-API] Connection note (${error.message}). Retrying in ${backoffMs}ms (${attempt}/${retries})...`);
                await new Promise(r => setTimeout(r, backoffMs));
            }
        }
    }

    // Intercept global fetch so all existing page scripts automatically get anti-stale & retry resilience
    if (originalFetch) {
        window.fetch = function (input, init) {
            if (typeof input === 'string' && (input.startsWith('/api/') || input.startsWith('/api') || input === '/health')) {
                return apiFetch(input, init);
            }
            return originalFetch(input, init);
        };
    }

    // Auto-Sync state
    let syncVersion = null;
    let syncTimestamp = 0;
    let syncPollTimer = null;
    let isSyncing = false;

    /**
     * Updates UI sync indicators across the layout.
     */
    function updateSyncUi(state, payload = null) {
        const pills = document.querySelectorAll('.sync-status-pill');
        pills.forEach(pill => {
            const dot = pill.querySelector('.sync-dot');
            const label = pill.querySelector('.sync-label');

            if (state === 'syncing') {
                pill.classList.add('syncing');
                if (label) label.textContent = 'Syncing...';
            } else if (state === 'synced') {
                pill.classList.remove('syncing');
                if (dot) dot.style.backgroundColor = '#10B981';
                if (label) label.textContent = 'Live Synced';
            } else if (state === 'updated') {
                pill.classList.remove('syncing');
                if (dot) dot.style.backgroundColor = '#D4AF37';
                if (label) label.textContent = 'Updated';
            } else if (state === 'offline') {
                pill.classList.remove('syncing');
                if (dot) dot.style.backgroundColor = '#EF4444';
                if (label) label.textContent = 'Offline';
            }
        });
    }

    /**
     * Polls /api/sync-status and compares current hash with stored version.
     */
    async function checkSyncStatus(isManual = false) {
        if (isSyncing) return;
        isSyncing = true;
        updateSyncUi('syncing');

        try {
            const res = await apiFetch(`/api/sync-status?_t=${Date.now()}`, { cache: 'no-store' }, 1);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            if (!syncVersion) {
                syncVersion = data.version;
                syncTimestamp = data.timestamp;
                updateSyncUi('synced', data);
            } else if (data.version !== syncVersion) {
                console.log(`[IMAGEKEY-SYNC] Backend data updated: ${syncVersion} -> ${data.version}`);
                const previous = syncVersion;
                syncVersion = data.version;
                syncTimestamp = data.timestamp;
                updateSyncUi('updated', data);

                // Notify custom listeners
                window.dispatchEvent(new CustomEvent('imagekey:synced', {
                    detail: { previousVersion: previous, currentVersion: data.version, data }
                }));

                // Refresh active page components
                triggerPageRefresh(isManual);
            } else {
                updateSyncUi('synced', data);
            }
        } catch (err) {
            console.debug('[IMAGEKEY-SYNC] Check note:', err.message);
            updateSyncUi('offline');
        } finally {
            isSyncing = false;
        }
    }

    /**
     * Automatically triggers re-fetch on the active page without requiring a destructive page reload.
     */
    function triggerPageRefresh(isManual = false) {
        let refreshed = false;

        // Dashboard reloaders
        if (typeof window.loadMyImages === 'function') {
            window.loadMyImages();
            if (typeof window.loadSharedWithMe === 'function') window.loadSharedWithMe();
            refreshed = true;
        }
        // Admin reloaders
        if (typeof window.fetchOverview === 'function') {
            window.fetchOverview();
            if (typeof window.fetchLogs === 'function') window.fetchLogs();
            refreshed = true;
        }
        // Permissions reloaders
        if (typeof window.loadPermissions === 'function') {
            window.loadPermissions();
            refreshed = true;
        }
        // Public View reloaders
        if (typeof window.fetchPublicDetails === 'function') {
            window.fetchPublicDetails();
            refreshed = true;
        }

        if (refreshed) {
            showToast(isManual ? 'Refreshed latest data!' : 'Auto-synced latest updates.', 'info', 2200);
        } else if (isManual) {
            showToast('Checked for updates. You are on the latest version.', 'info', 2000);
        }
    }

    function startSyncPolling() {
        if (syncPollTimer) clearInterval(syncPollTimer);
        syncPollTimer = setInterval(() => {
            if (document.visibilityState === 'visible') {
                checkSyncStatus(false);
            }
        }, SYNC_INTERVAL_MS);
    }

    function stopSyncPolling() {
        if (syncPollTimer) {
            clearInterval(syncPollTimer);
            syncPollTimer = null;
        }
    }

    // Bind lifecycle visibility and network resume handlers
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            checkSyncStatus(false);
            startSyncPolling();
        } else {
            stopSyncPolling();
        }
    });

    window.addEventListener('focus', () => checkSyncStatus(false));
    window.addEventListener('online', () => {
        showToast('Network restored. Syncing...', 'success', 2000);
        checkSyncStatus(true);
    });

    // Start polling immediately when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            checkSyncStatus(false);
            startSyncPolling();
        });
    } else {
        checkSyncStatus(false);
        startSyncPolling();
    }

    // Expose helpers and sync controls globally
    window.IMAGEKEY_CONFIG = {
        DEFAULT_TUNNEL_URL,
        getApiBaseUrl,
        setApiBaseUrl: (url) => {
            if (url) localStorage.setItem('imagekey_api_base_url', url);
            else localStorage.removeItem('imagekey_api_base_url');
        }
    };

    window.IMAGEKEY_SYNC = {
        check: checkSyncStatus,
        refresh: () => checkSyncStatus(true),
        getVersion: () => syncVersion,
        getTimestamp: () => syncTimestamp
    };

    window.apiFetch = apiFetch;
    window.syncNow = () => checkSyncStatus(true);

    // Expose helpers globally
    window.IMAGEKEY_APP = {
        showToast,
        copyText,
        downloadImage,
        shareImageAndInfo,
        apiFetch,
        syncNow: () => checkSyncStatus(true)
    };
    window.showToast = showToast;
    window.copyText = copyText;
    window.downloadImage = downloadImage;
    window.shareImageAndInfo = shareImageAndInfo;
})();
