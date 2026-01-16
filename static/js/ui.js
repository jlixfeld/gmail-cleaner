/**
 * Gmail Unsubscribe - UI Utilities Module
 */

window.GmailCleaner = window.GmailCleaner || {};

GmailCleaner.UI = {
    /**
     * Sets up click handlers for navigation items and initializes active view.
     */
    setupNavigation() {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const view = item.dataset.view;
                this.showView(view);
            });
        });

        // Initialize the currently active view (trigger any auto-loading)
        const activeNav = document.querySelector('.nav-item.active');
        if (activeNav) {
            const currentView = activeNav.dataset.view;
            // Call view-specific initialization without switching views
            this.initializeView(currentView);
        }
    },

    /**
     * Initializes view-specific features without switching tabs.
     * @param {string} viewName - The view to initialize.
     */
    initializeView(viewName) {
        if (viewName === 'delete' && GmailCleaner.Delete) {
            // Load any existing scan results
            if (typeof GmailCleaner.Delete.loadExistingResults === 'function') {
                GmailCleaner.Delete.loadExistingResults();
            }
            // Auto-scan recipients for protection features
            if (typeof GmailCleaner.Delete.autoScanRecipients === 'function') {
                GmailCleaner.Delete.autoScanRecipients();
            }
        }
    },

    /**
     * Shows specified view, hides others, and updates navigation state.
     * @param {string} viewName - The view to display.
     */
    showView(viewName) {
        GmailCleaner.currentView = viewName;

        // Hide all views
        document.querySelectorAll('.view').forEach(view => {
            view.classList.add('hidden');
        });

        // Show requested view
        const viewId = viewName + 'View';
        const view = document.getElementById(viewId);
        if (view) {
            view.classList.remove('hidden');
        }

        // Update nav active state
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.remove('active');
            if (item.dataset.view === viewName) {
                item.classList.add('active');
            }
        });

        // Special handling for unsubscribe view
        if (viewName === 'unsubscribe') {
            if (GmailCleaner.results.length === 0) {
                document.getElementById('noResults').classList.remove('hidden');
                document.getElementById('resultsSection').classList.add('hidden');
            } else {
                document.getElementById('noResults').classList.add('hidden');
                document.getElementById('resultsSection').classList.remove('hidden');
            }
        }

        // Refresh unread count when switching to Mark Read view
        if (viewName === 'markread') {
            GmailCleaner.MarkRead.refreshUnreadCount();
        }

        // Handle unread view initial state
        if (viewName === 'unread') {
            if (GmailCleaner.Unread && GmailCleaner.Unread.results.length === 0) {
                document.getElementById('unreadNoResults').classList.remove('hidden');
                document.getElementById('unreadResultsSection').classList.add('hidden');
            } else if (GmailCleaner.Unread) {
                document.getElementById('unreadNoResults').classList.add('hidden');
                document.getElementById('unreadResultsSection').classList.remove('hidden');
            }
        }

        // Auto-scan recipients and load existing results when switching to Delete Emails view
        if (viewName === 'delete') {
            if (GmailCleaner.Delete) {
                // Load any existing scan results that weren't displayed
                if (typeof GmailCleaner.Delete.loadExistingResults === 'function') {
                    GmailCleaner.Delete.loadExistingResults();
                }
                // Auto-scan recipients for protection features
                if (typeof GmailCleaner.Delete.autoScanRecipients === 'function') {
                    GmailCleaner.Delete.autoScanRecipients();
                }
            }
        }
    },

    /**
     * Escapes HTML special characters to prevent XSS.
     * @param {string} text - The text to escape.
     * @returns {string} HTML-safe escaped text.
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    },

    /**
     * Formats bytes to human-readable size (B, KB, MB, GB).
     * @param {number} bytes - The byte count to format.
     * @returns {string} Formatted size string or empty string if 0.
     */
    formatSize(bytes) {
        if (!bytes || bytes === 0) return '';
        const units = ['B', 'KB', 'MB', 'GB'];
        let size = bytes;
        let unitIndex = 0;
        while (size >= 1024 && unitIndex < units.length - 1) {
            size /= 1024;
            unitIndex++;
        }
        return size.toFixed(unitIndex > 0 ? 1 : 0) + ' ' + units[unitIndex];
    },

    /**
     * Toggles sidebar visibility on mobile devices.
     */
    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.toggle('open');
    },

    /**
     * Displays a toast notification with auto-dismiss.
     * @param {string} message - The main message to display.
     * @param {string} type - Toast type: 'success', 'error', or 'info'.
     * @param {number} duration - Display duration in milliseconds.
     * @param {string|null} tip - Optional secondary tip message.
     */
    showToast(message, type = 'success', duration = 5000, tip = null) {
        // Create toast container if it doesn't exist
        let container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        // Icon based on type
        const icons = {
            success: '<svg viewBox="0 0 24 24" width="20" height="20"><path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/></svg>',
            error: '<svg viewBox="0 0 24 24" width="20" height="20"><path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/></svg>',
            info: '<svg viewBox="0 0 24 24" width="20" height="20"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>'
        };

        toast.innerHTML = `
            <div class="toast-icon">${icons[type] || icons.success}</div>
            <div class="toast-content">
                <div class="toast-message">${message}</div>
                ${tip ? `<div class="toast-tip">${tip}</div>` : ''}
            </div>
            <button class="toast-close" onclick="this.parentElement.remove()">
                <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/></svg>
            </button>
        `;

        container.appendChild(toast);

        // Trigger animation
        setTimeout(() => toast.classList.add('show'), 10);

        // Auto remove after duration
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    /** Shows a green success toast. */
    showSuccessToast(message, tip = null) {
        this.showToast(message, 'success', 5000, tip);
    },

    /** Shows a red error toast with longer duration. */
    showErrorToast(message) {
        this.showToast(message, 'error', 6000);
    },

    /** Shows a blue info toast. */
    showInfoToast(message) {
        this.showToast(message, 'info', 4000);
    }
};

// Global shortcuts
function showView(viewName) { GmailCleaner.UI.showView(viewName); }
function toggleSidebar() { GmailCleaner.UI.toggleSidebar(); }
function showToast(message, type, duration, tip) { GmailCleaner.UI.showToast(message, type, duration, tip); }
