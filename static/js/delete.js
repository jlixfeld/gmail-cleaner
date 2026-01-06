/**
 * Gmail Unsubscribe - Delete Emails Module
 */

window.GmailCleaner = window.GmailCleaner || {};

GmailCleaner.Delete = {
    // Unknown senders state
    knownSendersCached: false,
    buildingKnownSenders: false,

    // Domain grouping state
    groupByDomain: false,
    domainGroups: [],
    expandedDomains: new Set(),

    formatDateRange(firstDate, lastDate) {
        /**
         * Parse RFC 2822 date string and format as MM/DD/YYYY
         * Example: "Wed, 15 Nov 2025 10:30:00 +0000" -> "11/15/2025"
         * Returns date range from oldest to newest
         */
        const formatDate = (dateStr) => {
            try {
                const date = new Date(dateStr);
                if (isNaN(date.getTime())) return null;
                const m = String(date.getMonth() + 1).padStart(2, '0');
                const d = String(date.getDate()).padStart(2, '0');
                const y = date.getFullYear();
                return `${m}/${d}/${y}`;
            } catch {
                return null;
            }
        };

        const first = formatDate(firstDate);
        const last = formatDate(lastDate);

        if (!first || !last) return '';
        if (first === last) return first;

        // Compare dates to determine order (oldest to newest)
        const firstDateObj = new Date(firstDate);
        const lastDateObj = new Date(lastDate);

        if (firstDateObj <= lastDateObj) {
            return `${first} to ${last}`;
        } else {
            return `${last} to ${first}`;
        }
    },

    async startScan() {
        if (GmailCleaner.deleteScanning) return;

        const authResponse = await fetch('/api/auth-status');
        const authStatus = await authResponse.json();

        if (!authStatus.logged_in) {
            GmailCleaner.Auth.signIn();
            return;
        }

        // Check if filter toggle is enabled
        const filterToggle = document.getElementById('filterKnownSendersToggle');
        const filterEnabled = filterToggle && filterToggle.checked;

        // If filter is enabled but no cache exists, show error
        if (filterEnabled && !this.knownSendersCached) {
            alert('Please run "Scan Known Senders" first to build the known senders cache before filtering.');
            return;
        }

        GmailCleaner.deleteScanning = true;

        const scanBtn = document.getElementById('deleteScanBtn');
        const progressCard = document.getElementById('deleteProgressCard');

        scanBtn.disabled = true;
        scanBtn.innerHTML = `
            <svg class="spinner" viewBox="0 0 24 24" width="18" height="18">
                <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="60" stroke-linecap="round"/>
            </svg>
            Scanning...
        `;
        progressCard.classList.remove('hidden');

        const limit = getLimitValue('deleteScanLimit');
        const filters = GmailCleaner.Filters.get();

        // Choose endpoint based on filter toggle state
        const endpoint = filterEnabled ? '/api/delete-scan-unknown' : '/api/delete-scan';

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    limit: limit,
                    filters: filters
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                const errorMsg = errorData.detail || `Request failed with status ${response.status}`;
                throw new Error(errorMsg);
            }

            this.pollProgress();
        } catch (error) {
            alert('Error: ' + error.message);
            this.resetScan();
        }
    },

    async pollProgress() {
        try {
            const response = await fetch('/api/delete-scan-status');
            const status = await response.json();

            const progressBar = document.getElementById('deleteProgressBar');
            const progressText = document.getElementById('deleteProgressText');

            progressBar.style.width = status.progress + '%';
            progressText.textContent = status.message;

            if (status.done) {
                if (!status.error) {
                    const resultsResponse = await fetch('/api/delete-scan-results');
                    GmailCleaner.deleteResults = await resultsResponse.json();
                    this.displayResults();
                } else {
                    alert('Error: ' + status.error);
                }
                this.resetScan();
            } else {
                setTimeout(() => this.pollProgress(), 300);
            }
        } catch (error) {
            setTimeout(() => this.pollProgress(), 500);
        }
    },

    resetScan() {
        GmailCleaner.deleteScanning = false;
        const scanBtn = document.getElementById('deleteScanBtn');
        scanBtn.disabled = false;
        scanBtn.innerHTML = `
            <svg viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
            </svg>
            Scan Senders
        `;
        // Also reset known senders button if it exists
        this.resetKnownSendersScan();
    },

    displayResults() {
        const resultsList = document.getElementById('deleteResultsList');
        const resultsSection = document.getElementById('deleteResultsSection');
        const noResults = document.getElementById('deleteNoResults');
        const badge = document.getElementById('deleteSendersBadge');

        resultsList.innerHTML = '';

        if (GmailCleaner.deleteResults.length === 0) {
            badge.textContent = '0';
            resultsSection.classList.add('hidden');
            noResults.classList.remove('hidden');
            this.setActionButtonsEnabled(false);
            return;
        }

        resultsSection.classList.remove('hidden');
        noResults.classList.add('hidden');
        this.setActionButtonsEnabled(true);

        // Dispatch to the right renderer
        if (this.groupByDomain) {
            this.buildDomainGroups();
            this.displayDomainResults();
            badge.textContent = this.domainGroups.length + ' domains';
        } else {
            this.displayFlatResults();
            badge.textContent = GmailCleaner.deleteResults.length;
        }
    },

    displayFlatResults() {
        const resultsList = document.getElementById('deleteResultsList');

        // Sort results by date
        const sortedResults = sortResultsByDate(GmailCleaner.deleteResults, GmailCleaner.sortOrder.delete);

        sortedResults.forEach((r, i) => {
            // Find original index for actions
            const originalIndex = GmailCleaner.deleteResults.indexOf(r);
            const item = document.createElement('div');
            item.className = 'result-item';

            const dateRange = this.formatDateRange(r.first_date, r.last_date);
            const dateRangeDisplay = dateRange ? `<div class="result-date-range">${dateRange}</div>` : '';

            item.innerHTML = `
                <label class="checkbox-wrapper result-checkbox">
                    <input type="checkbox" class="delete-cb" data-index="${originalIndex}" data-email="${GmailCleaner.UI.escapeHtml(r.email)}">
                    <span class="checkmark"></span>
                </label>
                <div class="result-content">
                    <div class="result-sender">${GmailCleaner.UI.escapeHtml(r.email)}</div>
                    <div class="result-subject">${GmailCleaner.UI.escapeHtml(r.subjects[0] || 'No subject')}</div>
                    <div class="result-meta">
                        ${dateRangeDisplay}
                        <span class="result-count">${r.count} emails</span>
                    </div>
                </div>
                <div class="result-actions">
                    <button class="unsub-btn delete-btn" id="delete-${originalIndex}" onclick="GmailCleaner.Delete.deleteSenderEmails(${originalIndex})">
                        Delete ${r.count}
                    </button>
                </div>
            `;
            resultsList.appendChild(item);
        });
    },

    toggleGroupByDomain() {
        const toggle = document.getElementById('groupByDomainToggle');
        this.groupByDomain = toggle.checked;

        // Reset selections when toggling
        document.getElementById('deleteSelectAll').checked = false;
        this.expandedDomains.clear();

        // Re-render
        this.displayResults();
    },

    buildDomainGroups() {
        const domainMap = new Map();

        GmailCleaner.deleteResults.forEach(sender => {
            const domain = sender.domain || sender.email.split('@').pop().toLowerCase();
            if (!domainMap.has(domain)) {
                domainMap.set(domain, {
                    domain: domain,
                    totalEmails: 0,
                    senders: [],
                    uniqueSenders: new Set(),
                    uniqueRecipients: new Set(),
                    firstDate: null,
                    lastDate: null,
                });
            }

            const group = domainMap.get(domain);
            group.totalEmails += sender.count;
            group.senders.push(sender);
            group.uniqueSenders.add(sender.email);

            // Merge recipients
            if (sender.recipients) {
                sender.recipients.forEach(r => group.uniqueRecipients.add(r));
            }

            // Track date range
            if (sender.first_date) {
                if (!group.firstDate || new Date(sender.first_date) < new Date(group.firstDate)) {
                    group.firstDate = sender.first_date;
                }
            }
            if (sender.last_date) {
                if (!group.lastDate || new Date(sender.last_date) > new Date(group.lastDate)) {
                    group.lastDate = sender.last_date;
                }
            }
        });

        // Convert sets to arrays and sort by total emails
        this.domainGroups = Array.from(domainMap.values())
            .map(group => ({
                ...group,
                uniqueSenders: Array.from(group.uniqueSenders),
                uniqueRecipients: Array.from(group.uniqueRecipients),
            }))
            .sort((a, b) => b.totalEmails - a.totalEmails);
    },

    displayDomainResults() {
        const resultsList = document.getElementById('deleteResultsList');

        this.domainGroups.forEach((group, i) => {
            const isExpanded = this.expandedDomains.has(group.domain);
            const domainRow = this.createDomainRow(group, i, isExpanded);
            resultsList.appendChild(domainRow);

            if (isExpanded) {
                const sendersTable = this.createSendersTable(group);
                resultsList.appendChild(sendersTable);
            }
        });
    },

    createDomainRow(group, index, isExpanded) {
        const row = document.createElement('div');
        row.className = 'result-item domain-row' + (isExpanded ? ' expanded' : '');
        row.dataset.domain = group.domain;

        const dateRange = this.formatDateRange(group.firstDate, group.lastDate);
        const dateRangeDisplay = dateRange ? `<div class="result-date-range">${dateRange}</div>` : '';

        const sendersTooltip = group.uniqueSenders.join('\n');
        const recipientsTooltip = group.uniqueRecipients.join('\n');

        row.innerHTML = `
            <label class="checkbox-wrapper result-checkbox">
                <input type="checkbox" class="domain-cb" data-domain="${GmailCleaner.UI.escapeHtml(group.domain)}" data-index="${index}">
                <span class="checkmark"></span>
            </label>
            <button class="expand-toggle" onclick="GmailCleaner.Delete.toggleDomainExpand('${GmailCleaner.UI.escapeHtml(group.domain)}')">
                <svg viewBox="0 0 24 24" width="18" height="18">
                    <path fill="currentColor" d="${isExpanded ? 'M7 10l5 5 5-5H7z' : 'M10 17l5-5-5-5v10z'}"/>
                </svg>
            </button>
            <div class="result-content" onclick="GmailCleaner.Delete.toggleDomainExpand('${GmailCleaner.UI.escapeHtml(group.domain)}')" style="cursor: pointer;">
                <div class="result-sender domain-name">${GmailCleaner.UI.escapeHtml(group.domain)}</div>
                <div class="domain-pills">
                    <span class="pill sender-pill" data-tooltip="${GmailCleaner.UI.escapeHtml(sendersTooltip)}">${group.uniqueSenders.length} sender${group.uniqueSenders.length !== 1 ? 's' : ''}</span>
                    ${group.uniqueRecipients.length > 0 ? `<span class="pill recipient-pill" data-tooltip="${GmailCleaner.UI.escapeHtml(recipientsTooltip)}">${group.uniqueRecipients.length} recipient${group.uniqueRecipients.length !== 1 ? 's' : ''}</span>` : ''}
                </div>
                <div class="result-meta">
                    ${dateRangeDisplay}
                    <span class="result-count">${group.totalEmails} emails</span>
                </div>
            </div>
            <div class="result-actions">
                <button class="unsub-btn delete-btn" id="delete-domain-${index}" onclick="GmailCleaner.Delete.deleteDomainEmails('${GmailCleaner.UI.escapeHtml(group.domain)}')">
                    Delete ${group.totalEmails}
                </button>
            </div>
        `;

        return row;
    },

    createSendersTable(group) {
        const container = document.createElement('div');
        container.className = 'domain-senders-container';
        container.dataset.domain = group.domain;

        // Sort senders by count
        const sortedSenders = [...group.senders].sort((a, b) => b.count - a.count);

        sortedSenders.forEach(sender => {
            const originalIndex = GmailCleaner.deleteResults.indexOf(sender);
            const recipientsTooltip = (sender.recipients || []).join('\n');

            const senderRow = document.createElement('div');
            senderRow.className = 'result-item sender-row nested';
            senderRow.innerHTML = `
                <label class="checkbox-wrapper result-checkbox">
                    <input type="checkbox" class="delete-cb sender-cb" data-index="${originalIndex}" data-email="${GmailCleaner.UI.escapeHtml(sender.email)}" data-domain="${GmailCleaner.UI.escapeHtml(group.domain)}">
                    <span class="checkmark"></span>
                </label>
                <div class="result-content">
                    <div class="result-sender">${GmailCleaner.UI.escapeHtml(sender.email)}</div>
                    ${sender.recipients && sender.recipients.length > 0 ? `<span class="pill recipient-pill small" data-tooltip="${GmailCleaner.UI.escapeHtml(recipientsTooltip)}">${sender.recipients.length}</span>` : ''}
                    <div class="result-meta">
                        <span class="result-count">${sender.count} emails</span>
                    </div>
                </div>
                <div class="result-actions">
                    <button class="unsub-btn delete-btn" id="delete-${originalIndex}" onclick="GmailCleaner.Delete.deleteSenderEmails(${originalIndex})">
                        Delete ${sender.count}
                    </button>
                </div>
            `;
            container.appendChild(senderRow);
        });

        return container;
    },

    toggleDomainExpand(domain) {
        if (this.expandedDomains.has(domain)) {
            this.expandedDomains.delete(domain);
        } else {
            this.expandedDomains.add(domain);
        }
        this.displayResults();
    },

    async deleteDomainEmails(domain) {
        const group = this.domainGroups.find(g => g.domain === domain);
        if (!group) return;

        const senderEmails = group.senders.map(s => s.email);
        const totalEmails = group.totalEmails;

        if (!confirm(`Delete ALL ${totalEmails} emails from ${senderEmails.length} senders in ${domain}?\n\nThis will move them to Trash.`)) {
            return;
        }

        // Show bulk delete overlay
        this.showDeleteOverlay(senderEmails.length, totalEmails);

        try {
            await fetch('/api/delete-domain', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ domain: domain, senders: senderEmails })
            });

            // Poll for progress using the same bulk delete status
            this.pollDomainDeleteProgress(domain, senderEmails);
        } catch (error) {
            this.hideDeleteOverlay();
            alert('Error: ' + error.message);
        }
    },

    async pollDomainDeleteProgress(domain, senderEmails) {
        try {
            const response = await fetch('/api/delete-bulk-status');
            const status = await response.json();

            this.updateDeleteOverlay(status);

            if (status.done) {
                this.hideDeleteOverlay();

                if (!status.error) {
                    const deletedCount = status.deleted_count || 0;
                    GmailCleaner.UI.showSuccessToast(`Deleted ${deletedCount.toLocaleString()} emails from ${domain}`);

                    // Refresh results
                    setTimeout(async () => {
                        const resultsResponse = await fetch('/api/delete-scan-results');
                        GmailCleaner.deleteResults = await resultsResponse.json();
                        this.displayResults();
                        document.getElementById('deleteSelectAll').checked = false;
                    }, 1000);
                } else {
                    alert('Error: ' + status.error);
                }
            } else {
                setTimeout(() => this.pollDomainDeleteProgress(domain, senderEmails), 300);
            }
        } catch (error) {
            setTimeout(() => this.pollDomainDeleteProgress(domain, senderEmails), 500);
        }
    },

    setActionButtonsEnabled(enabled) {
        const buttons = [
            'applyLabelBtn',
            'archiveBtn',
            'importantBtn',
            'downloadBtn',
            'deleteSelectedBtn'
        ];
        buttons.forEach(id => {
            const btn = document.getElementById(id);
            if (btn) {
                btn.disabled = !enabled;
            }
        });
    },

    toggleSelectAll() {
        const selectAll = document.getElementById('deleteSelectAll');
        const checked = selectAll.checked;

        if (this.groupByDomain) {
            // In domain view, select domain checkboxes
            document.querySelectorAll('.domain-cb').forEach(cb => {
                cb.checked = checked;
            });
            // Also select nested sender checkboxes if visible
            document.querySelectorAll('.sender-cb').forEach(cb => {
                cb.checked = checked;
            });
        } else {
            // In flat view, select all sender checkboxes
            document.querySelectorAll('.delete-cb').forEach(cb => {
                cb.checked = checked;
            });
        }
    },

    async deleteSenderEmails(index) {
        const r = GmailCleaner.deleteResults[index];
        const btn = document.getElementById('delete-' + index);

        if (!confirm(`Delete ALL ${r.count} emails from ${r.email}?\n\nThis will move them to Trash.`)) {
            return;
        }

        btn.disabled = true;
        btn.classList.add('btn-deleting');
        btn.innerHTML = `
            <svg class="spinner" viewBox="0 0 24 24" width="14" height="14">
                <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="60" stroke-linecap="round"/>
            </svg>
            Deleting...
        `;

        try {
            const response = await fetch('/api/delete-emails', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sender: r.email })
            });
            const result = await response.json();

            if (result.success) {
                btn.classList.remove('btn-deleting');
                btn.innerHTML = `✓ Deleted ${result.deleted}!`;
                btn.classList.add('success');
                GmailCleaner.UI.showSuccessToast(`Deleted ${result.deleted} emails from ${r.email}`);
                setTimeout(() => {
                    GmailCleaner.deleteResults = GmailCleaner.deleteResults.filter((_, i) => i !== index);
                    this.displayResults();
                }, 1500);
            } else {
                btn.classList.remove('btn-deleting');
                btn.innerHTML = 'Error';
                alert('Error: ' + result.message);
                btn.disabled = false;
                btn.innerHTML = `Delete ${r.count}`;
            }
        } catch (error) {
            alert('Error: ' + error.message);
            btn.classList.remove('btn-deleting');
            btn.disabled = false;
            btn.innerHTML = `Delete ${r.count}`;
        }
    },

    async deleteSelected() {
        let totalEmails = 0;
        const senderEmails = [];
        const senderSet = new Set(); // Avoid duplicates

        if (this.groupByDomain) {
            // Collect from checked domains
            document.querySelectorAll('.domain-cb:checked').forEach(cb => {
                const domain = cb.dataset.domain;
                const group = this.domainGroups.find(g => g.domain === domain);
                if (group) {
                    group.senders.forEach(s => {
                        if (!senderSet.has(s.email)) {
                            senderSet.add(s.email);
                            senderEmails.push(s.email);
                            totalEmails += s.count;
                        }
                    });
                }
            });

            // Also collect from individually checked senders (in expanded domains)
            document.querySelectorAll('.sender-cb:checked').forEach(cb => {
                const email = cb.dataset.email;
                if (!senderSet.has(email)) {
                    senderSet.add(email);
                    const index = parseInt(cb.dataset.index);
                    const r = GmailCleaner.deleteResults[index];
                    senderEmails.push(email);
                    totalEmails += r.count;
                }
            });
        } else {
            // Flat view - collect from checked senders
            document.querySelectorAll('.delete-cb:checked').forEach(cb => {
                const index = parseInt(cb.dataset.index);
                const r = GmailCleaner.deleteResults[index];
                totalEmails += r.count;
                senderEmails.push(r.email);
            });
        }

        if (senderEmails.length === 0) {
            alert('Please select at least one sender to delete emails from.');
            return;
        }

        if (!confirm(`Delete ${totalEmails} emails from ${senderEmails.length} senders?\n\nThis will move them to Trash.`)) {
            return;
        }

        // Show bulk delete overlay with progress bar
        this.showDeleteOverlay(senderEmails.length, totalEmails);

        // Collect sender info for button updates
        const senderInfoList = senderEmails.map(email => {
            const index = GmailCleaner.deleteResults.findIndex(r => r.email === email);
            return { email, index, count: GmailCleaner.deleteResults[index]?.count || 0 };
        }).filter(info => info.index >= 0);

        // Update buttons to show deleting state
        senderInfoList.forEach(info => {
            const btn = document.getElementById('delete-' + info.index);
            if (btn) {
                btn.disabled = true;
                btn.classList.add('btn-deleting');
                btn.innerHTML = `
                    <svg class="spinner" viewBox="0 0 24 24" width="14" height="14">
                        <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="60" stroke-linecap="round"/>
                    </svg>
                    Deleting...
                `;
            }
        });

        try {
            // Start the background task
            await fetch('/api/delete-emails-bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ senders: senderEmails })
            });

            // Poll for progress
            this.pollDeleteProgress(senderInfoList);
        } catch (error) {
            this.hideDeleteOverlay();
            alert('Error: ' + error.message);
        }
    },

    async pollDeleteProgress(senderInfoList) {
        try {
            const response = await fetch('/api/delete-bulk-status');
            const status = await response.json();

            // Update progress bar in overlay
            this.updateDeleteOverlay(status);

            if (status.done) {
                this.hideDeleteOverlay();

                if (!status.error) {
                    const deletedCount = status.deleted_count || 0;
                    senderInfoList.forEach(info => {
                        const btn = document.getElementById('delete-' + info.index);
                        if (btn) {
                            btn.classList.remove('btn-deleting');
                            btn.innerHTML = '✓ Deleted!';
                            btn.classList.add('success');
                        }
                    });

                    GmailCleaner.UI.showSuccessToast(`Deleted ${deletedCount.toLocaleString()} emails from ${senderInfoList.length} senders`);

                    setTimeout(async () => {
                        const resultsResponse = await fetch('/api/delete-scan-results');
                        GmailCleaner.deleteResults = await resultsResponse.json();
                        this.displayResults();
                        document.getElementById('deleteSelectAll').checked = false;
                    }, 1000);
                } else {
                    alert('Error: ' + status.error);
                    senderInfoList.forEach(info => {
                        const btn = document.getElementById('delete-' + info.index);
                        if (btn) {
                            btn.classList.remove('btn-deleting');
                            btn.disabled = false;
                            btn.innerHTML = `Delete ${info.count}`;
                        }
                    });
                }
            } else {
                setTimeout(() => this.pollDeleteProgress(senderInfoList), 300);
            }
        } catch (error) {
            setTimeout(() => this.pollDeleteProgress(senderInfoList), 500);
        }
    },

    showDeleteOverlay(senderCount, emailCount) {
        // Remove any existing overlay
        this.hideDeleteOverlay();

        const overlay = document.createElement('div');
        overlay.id = 'deleteOverlay';
        overlay.className = 'delete-overlay';
        overlay.innerHTML = `
            <div class="delete-overlay-content">
                <svg class="delete-overlay-spinner spinner" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="10" fill="none" stroke="#3b82f6" stroke-width="2" stroke-dasharray="60" stroke-linecap="round"/>
                </svg>
                <h3>Deleting Emails...</h3>
                <div class="delete-progress-container">
                    <div class="delete-progress-bar" id="deleteBulkProgressBar"></div>
                </div>
                <p id="deleteBulkProgressText">Starting deletion...</p>
                <p class="delete-stats" id="deleteBulkStats">0/${senderCount} senders | 0 emails deleted</p>
            </div>
        `;
        overlay.dataset.totalSenders = senderCount;
        document.body.appendChild(overlay);
    },

    updateDeleteOverlay(status) {
        const progressBar = document.getElementById('deleteBulkProgressBar');
        const progressText = document.getElementById('deleteBulkProgressText');
        const stats = document.getElementById('deleteBulkStats');
        const overlay = document.getElementById('deleteOverlay');

        if (progressBar) {
            progressBar.style.width = status.progress + '%';
        }
        if (progressText) {
            progressText.textContent = status.message;
        }
        if (stats && overlay) {
            const totalSenders = overlay.dataset.totalSenders || status.total_senders;
            if (status.progress <= 40) {
                // Phase 1: Collecting emails
                stats.textContent = `Scanning ${status.current_sender || 0}/${totalSenders} senders...`;
            } else {
                // Phase 2: Deleting
                stats.textContent = `${status.deleted_count || 0} emails deleted`;
            }
        }
    },

    hideDeleteOverlay() {
        const overlay = document.getElementById('deleteOverlay');
        if (overlay) {
            overlay.remove();
        }
    },

    // Known senders cache functionality
    async startKnownSendersScan() {
        if (this.buildingKnownSenders) return;

        const authResponse = await fetch('/api/auth-status');
        const authStatus = await authResponse.json();

        if (!authStatus.logged_in) {
            GmailCleaner.Auth.signIn();
            return;
        }

        // Build the known senders cache
        await this.buildKnownSenders();
    },

    async buildKnownSenders() {
        this.buildingKnownSenders = true;

        // Get limit from text input (0 = scan all)
        const limit = getLimitValue('sentScanLimit');

        // Show building overlay
        this.showKnownSendersOverlay();

        try {
            const response = await fetch('/api/build-known-senders', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ limit: limit })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Failed to start building known senders');
            }

            // Poll for progress
            await this.pollKnownSendersProgress();
        } catch (error) {
            this.hideKnownSendersOverlay();
            this.buildingKnownSenders = false;
            alert('Error building known senders: ' + error.message);
        }
    },

    async pollKnownSendersProgress() {
        try {
            const response = await fetch('/api/known-senders-status');
            const status = await response.json();

            this.updateKnownSendersOverlay(status);

            if (status.done) {
                this.hideKnownSendersOverlay();
                this.buildingKnownSenders = false;

                if (!status.error) {
                    this.knownSendersCached = true;
                    this.updateKnownSendersStatusText(status.sender_count);
                } else {
                    alert('Error: ' + status.error);
                }
            } else {
                setTimeout(() => this.pollKnownSendersProgress(), 300);
            }
        } catch (error) {
            setTimeout(() => this.pollKnownSendersProgress(), 500);
        }
    },

    showKnownSendersOverlay() {
        this.hideKnownSendersOverlay();

        const overlay = document.createElement('div');
        overlay.id = 'knownSendersOverlay';
        overlay.className = 'delete-overlay';
        overlay.innerHTML = `
            <div class="delete-overlay-content">
                <svg class="delete-overlay-spinner spinner" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="10" fill="none" stroke="#8b5cf6" stroke-width="2" stroke-dasharray="60" stroke-linecap="round"/>
                </svg>
                <h3>Building Known Senders Cache...</h3>
                <div class="delete-progress-container">
                    <div class="delete-progress-bar" id="knownSendersProgressBar" style="background: #8b5cf6;"></div>
                </div>
                <p id="knownSendersProgressText">Scanning sent emails...</p>
                <p class="delete-stats" id="knownSendersStats">0 contacts found</p>
            </div>
        `;
        document.body.appendChild(overlay);
    },

    updateKnownSendersOverlay(status) {
        const progressBar = document.getElementById('knownSendersProgressBar');
        const progressText = document.getElementById('knownSendersProgressText');
        const stats = document.getElementById('knownSendersStats');

        if (progressBar) {
            progressBar.style.width = status.progress + '%';
        }
        if (progressText) {
            progressText.textContent = status.message;
        }
        if (stats) {
            stats.textContent = `${status.sender_count || 0} contacts found from ${status.scanned_emails || 0} emails`;
        }
    },

    hideKnownSendersOverlay() {
        const overlay = document.getElementById('knownSendersOverlay');
        if (overlay) {
            overlay.remove();
        }
    },

    updateKnownSendersStatusText(count) {
        const statusText = document.getElementById('knownSendersStatusText');
        if (statusText) {
            statusText.textContent = `Known senders: ${count.toLocaleString()} contacts cached`;
            statusText.classList.add('cached');
        }
    },

    resetKnownSendersScan() {
        this.buildingKnownSenders = false;
        const scanBtn = document.getElementById('deleteUnknownBtn');
        if (scanBtn) {
            scanBtn.disabled = false;
            scanBtn.innerHTML = `
                <svg viewBox="0 0 24 24" width="18" height="18">
                    <path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                </svg>
                Scan Known Senders
            `;
        }
    },

    // Download emails functionality
    async downloadSelected() {
        const checkboxes = document.querySelectorAll('.delete-cb:checked');
        if (checkboxes.length === 0) {
            GmailCleaner.UI.showInfoToast('Please select at least one sender to download emails from.');
            return;
        }

        let totalEmails = 0;
        const senderEmails = [];
        checkboxes.forEach(cb => {
            const index = parseInt(cb.dataset.index);
            const r = GmailCleaner.deleteResults[index];
            totalEmails += r.count;
            senderEmails.push(r.email);
        });

        // Show download overlay
        this.showDownloadOverlay(checkboxes.length, totalEmails);

        try {
            // Start background download
            await fetch('/api/download-emails', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ senders: senderEmails })
            });

            // Poll for progress
            this.pollDownloadProgress();
        } catch (error) {
            this.hideDownloadOverlay();
            GmailCleaner.UI.showErrorToast('Error: ' + error.message);
        }
    },

    async pollDownloadProgress() {
        try {
            const response = await fetch('/api/download-status');
            const status = await response.json();

            this.updateDownloadOverlay(status);

            if (status.done) {
                if (!status.error) {
                    // Trigger CSV download
                    window.location.href = '/api/download-csv';
                    setTimeout(() => {
                        this.hideDownloadOverlay();
                        GmailCleaner.UI.showSuccessToast(
                            `Successfully exported ${status.fetched_count.toLocaleString()} emails to CSV file. Check your downloads folder.`,
                            'Tip: You can open the CSV in Excel or Google Sheets for easy viewing'
                        );
                    }, 500);
                } else {
                    this.hideDownloadOverlay();
                    GmailCleaner.UI.showErrorToast('Error: ' + status.error);
                }
            } else {
                setTimeout(() => this.pollDownloadProgress(), 300);
            }
        } catch (error) {
            setTimeout(() => this.pollDownloadProgress(), 500);
        }
    },

    showDownloadOverlay(senderCount, emailCount) {
        this.hideDownloadOverlay();

        const overlay = document.createElement('div');
        overlay.id = 'downloadOverlay';
        overlay.className = 'download-overlay';
        overlay.innerHTML = `
            <div class="download-overlay-content">
                <svg class="download-overlay-spinner spinner" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="10" fill="none" stroke="#10b981" stroke-width="2" stroke-dasharray="60" stroke-linecap="round"/>
                </svg>
                <h3>Downloading Email Data...</h3>
                <div class="download-progress-container">
                    <div class="download-progress-bar" id="downloadProgressBar"></div>
                </div>
                <p id="downloadProgressText">Starting download...</p>
                <p class="download-stats" id="downloadStats">0/${emailCount} emails from ${senderCount} senders</p>
                <p class="download-note">This may take a moment for large mailboxes</p>
            </div>
        `;
        overlay.dataset.totalEmails = emailCount;
        document.body.appendChild(overlay);
    },

    updateDownloadOverlay(status) {
        const overlay = document.getElementById('downloadOverlay');
        if (!overlay) return;

        const progressBar = document.getElementById('downloadProgressBar');
        const progressText = document.getElementById('downloadProgressText');
        const stats = document.getElementById('downloadStats');

        if (progressBar) {
            progressBar.style.width = status.progress + '%';
        }
        if (progressText) {
            progressText.textContent = status.message;
        }
        if (stats) {
            const totalEmails = overlay.dataset.totalEmails || status.total_emails;
            stats.textContent = `${status.fetched_count || 0}/${totalEmails} emails fetched`;
        }
    },

    hideDownloadOverlay() {
        const overlay = document.getElementById('downloadOverlay');
        if (overlay) {
            overlay.remove();
        }
    }
};

// Global shortcuts
function startDeleteScan() { GmailCleaner.Delete.startScan(); }
function startKnownSendersScan() { GmailCleaner.Delete.startKnownSendersScan(); }
function toggleDeleteSelectAll() { GmailCleaner.Delete.toggleSelectAll(); }
function deleteSelectedSenders() { GmailCleaner.Delete.deleteSelected(); }
function downloadSelectedEmails() { GmailCleaner.Delete.downloadSelected(); }
