/**
 * Gmail Unsubscribe - Main Entry Point
 * Initializes the application and loads all modules
 */

// Global state
window.GmailCleaner = {
    results: [],
    deleteResults: [],
    scanning: false,
    deleteScanning: false,
    currentView: 'login'
};

// Handle limit input warning - shows warning when value is 0 (scan all)
function handleLimitWarning(inputId) {
    const input = document.getElementById(inputId);
    const warning = document.getElementById(inputId + 'Warning');
    const value = parseInt(input.value);

    if (warning) {
        if (value === 0) {
            warning.classList.remove('hidden');
        } else {
            warning.classList.add('hidden');
        }
    }
}

// Get limit value - returns the numeric value (0 means scan all)
function getLimitValue(inputId) {
    const input = document.getElementById(inputId);
    const value = parseInt(input.value);
    return isNaN(value) || value < 0 ? parseInt(input.defaultValue) || 500 : value;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    GmailCleaner.Auth.checkStatus();
    GmailCleaner.Auth.checkWebAuthMode();
    GmailCleaner.UI.setupNavigation();
    GmailCleaner.Filters.setup();
});
