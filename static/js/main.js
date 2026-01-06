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
    currentView: 'login',
    sortOrder: {
        subscription: 'desc',
        delete: 'desc',
        unread: 'desc'
    }
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

// Sort results by date (last_date field)
function sortResultsByDate(results, order) {
    return [...results].sort((a, b) => {
        const dateA = a.last_date ? new Date(a.last_date) : new Date(0);
        const dateB = b.last_date ? new Date(b.last_date) : new Date(0);
        return order === 'desc' ? dateB - dateA : dateA - dateB;
    });
}

// Toggle sort order and update UI
function toggleSortOrder(type) {
    const currentOrder = GmailCleaner.sortOrder[type];
    GmailCleaner.sortOrder[type] = currentOrder === 'desc' ? 'asc' : 'desc';
    updateSortIndicator(type);

    // Re-display results with new sort order
    if (type === 'subscription') {
        GmailCleaner.Scanner.displayResults();
    } else if (type === 'delete') {
        GmailCleaner.Delete.displayResults();
    } else if (type === 'unread') {
        GmailCleaner.Unread.displayResults();
    }
}

// Update sort indicator icon
function updateSortIndicator(type) {
    const indicator = document.getElementById(`${type}SortIndicator`);
    if (indicator) {
        const isDesc = GmailCleaner.sortOrder[type] === 'desc';
        indicator.classList.toggle('sort-asc', !isDesc);
        indicator.classList.toggle('sort-desc', isDesc);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    GmailCleaner.Auth.checkStatus();
    GmailCleaner.Auth.checkWebAuthMode();
    GmailCleaner.UI.setupNavigation();
    GmailCleaner.Filters.setup();
});
