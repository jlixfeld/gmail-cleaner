/**
 * Gmail Unsubscribe - Delete Emails Module
 */

window.GmailCleaner = window.GmailCleaner || {};

GmailCleaner.Delete = {
  // Valid senders, known recipients, and overrides state (loaded from DB)
  validSenders: new Set(),
  myRecipients: new Set(),
  recipientOverrides: new Set(),
  recipientsScanInProgress: false,

  // Domain grouping state
  groupByDomain: false,
  domainGroups: [],
  expandedDomains: new Set(),

  // Selection state (persists across expand/collapse)
  selectedDomains: new Set(),
  selectedSenders: new Set(),

  formatMostRecentDate(firstDate, lastDate) {
    /**
     * Parse RFC 2822 date string and format as MM/DD/YYYY
     * Returns only the most recent date
     */
    const formatDate = (dateStr) => {
      try {
        const date = new Date(dateStr);
        if (isNaN(date.getTime())) return null;
        const m = String(date.getMonth() + 1).padStart(2, "0");
        const d = String(date.getDate()).padStart(2, "0");
        const y = date.getFullYear();
        return `${m}/${d}/${y}`;
      } catch {
        return null;
      }
    };

    // Return the most recent date (last_date is usually more recent)
    const firstDateObj = firstDate ? new Date(firstDate) : null;
    const lastDateObj = lastDate ? new Date(lastDate) : null;

    if (firstDateObj && lastDateObj) {
      return (
        formatDate(firstDateObj > lastDateObj ? firstDate : lastDate) || ""
      );
    }
    return formatDate(lastDate) || formatDate(firstDate) || "";
  },

  // Sort results by current sort settings (date or count)
  sortResults(results) {
    const sortBy = GmailCleaner.sortBy.delete;
    const sortOrder = GmailCleaner.sortOrder.delete;

    return [...results].sort((a, b) => {
      if (sortBy === "count") {
        const countA = a.count || 0;
        const countB = b.count || 0;
        return sortOrder === "desc" ? countB - countA : countA - countB;
      } else {
        // Default: sort by date
        const dateA = a.last_date ? new Date(a.last_date) : new Date(0);
        const dateB = b.last_date ? new Date(b.last_date) : new Date(0);
        return sortOrder === "desc" ? dateB - dateA : dateA - dateB;
      }
    });
  },

  // Sort domain groups by current sort settings
  sortDomainGroups(groups) {
    const sortBy = GmailCleaner.sortBy.delete;
    const sortOrder = GmailCleaner.sortOrder.delete;

    return [...groups].sort((a, b) => {
      if (sortBy === "count") {
        const countA = a.totalEmails || 0;
        const countB = b.totalEmails || 0;
        return sortOrder === "desc" ? countB - countA : countA - countB;
      } else {
        // Default: sort by most recent date (lastDate)
        const dateA = a.lastDate ? new Date(a.lastDate) : new Date(0);
        const dateB = b.lastDate ? new Date(b.lastDate) : new Date(0);
        return sortOrder === "desc" ? dateB - dateA : dateA - dateB;
      }
    });
  },

  // Track if we've already scanned recipients this session
  recipientsScanComplete: false,

  // Auto-scan recipients when Delete tab is selected
  async autoScanRecipients() {
    if (this.recipientsScanInProgress) return;

    const authResponse = await fetch("/api/auth-status");
    const authStatus = await authResponse.json();
    if (!authStatus.logged_in) return;

    // Load valid senders first (always refresh from database)
    await this.loadValidSenders();

    // Load existing recipients and overrides from database
    await this.loadMyRecipients();
    await this.loadRecipientOverrides();

    // Skip scanning if we already have recipients (either from DB or previous scan)
    if (this.myRecipients.size > 0 || this.recipientsScanComplete) {
      this.updateReferenceCounts();
      return;
    }

    // Show the spinner overlay
    this.recipientsScanInProgress = true;
    const overlay = document.getElementById("recipientsScanOverlay");
    if (overlay) overlay.classList.remove("hidden");

    try {
      // Start the recipients scan
      await fetch("/api/scan-recipients", { method: "POST" });

      // Poll for progress
      await this.pollRecipientsScanProgress();
    } catch (error) {
      console.error("Error scanning recipients:", error);
      this.hideRecipientsScanOverlay();
    }
  },

  async pollRecipientsScanProgress() {
    try {
      const response = await fetch("/api/recipients-scan-status");
      const status = await response.json();

      // Update message if provided
      const messageEl = document.getElementById("recipientsScanMessage");
      if (messageEl && status.message) {
        messageEl.textContent = status.message;
      }

      if (status.done) {
        // Load the recipients into local set
        await this.loadMyRecipients();
        this.hideRecipientsScanOverlay();

        // Update the UI counts
        this.updateReferenceCounts();
      } else {
        setTimeout(() => this.pollRecipientsScanProgress(), 300);
      }
    } catch (error) {
      setTimeout(() => this.pollRecipientsScanProgress(), 500);
    }
  },

  hideRecipientsScanOverlay() {
    this.recipientsScanInProgress = false;
    this.recipientsScanComplete = true; // Mark scan as done for this session
    const overlay = document.getElementById("recipientsScanOverlay");
    if (overlay) overlay.classList.add("hidden");
  },

  async loadValidSenders() {
    try {
      const response = await fetch("/api/valid-senders");
      const data = await response.json();
      this.validSenders = new Set(
        data.senders.map((s) => s.sender_email.toLowerCase()),
      );
      this.updateReferenceCounts();
    } catch (error) {
      console.error("Error loading valid senders:", error);
    }
  },

  async loadMyRecipients() {
    try {
      const response = await fetch("/api/my-recipients");
      const data = await response.json();
      this.myRecipients = new Set(
        data.recipients.map((r) => r.recipient_email.toLowerCase()),
      );
      this.updateReferenceCounts();
    } catch (error) {
      console.error("Error loading my recipients:", error);
    }
  },

  async loadRecipientOverrides() {
    try {
      const response = await fetch("/api/recipient-overrides");
      const data = await response.json();
      this.recipientOverrides = new Set(
        data.overrides.map((o) => o.sender_email.toLowerCase()),
      );
      this.updateReferenceCounts();
    } catch (error) {
      console.error("Error loading recipient overrides:", error);
    }
  },

  updateReferenceCounts() {
    const validCount = document.getElementById("validSendersCount");
    const recipientsCount = document.getElementById("knownRecipientsCount");
    const overridesCount = document.getElementById("recipientOverridesCount");
    if (validCount) validCount.textContent = this.validSenders.size;
    if (recipientsCount) recipientsCount.textContent = this.myRecipients.size;
    if (overridesCount) overridesCount.textContent = this.recipientOverrides.size;
  },

  // Tri-state toggle: Red -> Green -> Orange -> Red
  // Red (neither): Not protected, can delete
  // Green (valid): Protected via valid senders
  // Orange (override): Marked as deletable even if known recipient
  async cycleSenderState(email) {
    const emailLower = email.toLowerCase();
    const isValid = this.validSenders.has(emailLower);
    const isOverride = this.recipientOverrides.has(emailLower);

    try {
      if (!isValid && !isOverride) {
        // Red -> Green: Add to valid senders
        await fetch("/api/valid-senders", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sender_email: email }),
        });
        this.validSenders.add(emailLower);
      } else if (isValid) {
        // Green -> Orange: Remove from valid, add to overrides
        await fetch("/api/valid-senders", {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sender_email: email }),
        });
        await fetch("/api/recipient-overrides", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sender_email: email }),
        });
        this.validSenders.delete(emailLower);
        this.recipientOverrides.add(emailLower);
      } else {
        // Orange -> Red: Remove from overrides
        await fetch("/api/recipient-overrides", {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sender_email: email }),
        });
        this.recipientOverrides.delete(emailLower);
      }

      // Update counts and re-render
      this.updateReferenceCounts();
      this.displayResults();
      this.restoreSelectionState();
    } catch (error) {
      console.error("Error cycling sender state:", error);
      GmailCleaner.UI.showErrorToast("Failed to update sender status");
    }
  },

  // Check if sender is protected
  // Protected if: valid sender OR (known recipient WITHOUT override)
  isProtectedSender(email) {
    const emailLower = email.toLowerCase();
    if (this.validSenders.has(emailLower)) return true;
    if (
      this.myRecipients.has(emailLower) &&
      !this.recipientOverrides.has(emailLower)
    )
      return true;
    return false;
  },

  // Modal handlers
  async showValidSendersList() {
    const modal = document.getElementById("validSendersModal");
    const list = document.getElementById("validSendersList");
    const empty = document.getElementById("validSendersEmpty");

    // Refresh from server
    await this.loadValidSenders();

    list.innerHTML = "";

    if (this.validSenders.size === 0) {
      empty.classList.remove("hidden");
      list.classList.add("hidden");
    } else {
      empty.classList.add("hidden");
      list.classList.remove("hidden");

      Array.from(this.validSenders)
        .sort()
        .forEach((email) => {
          const item = document.createElement("div");
          item.className = "reference-list-item";
          const jsEscapedEmail = email
            .replace(/'/g, "\\'")
            .replace(/"/g, '\\"');
          item.innerHTML = `
                    <span class="reference-email">${GmailCleaner.UI.escapeHtml(email)}</span>
                    <button class="remove-btn" onclick="GmailCleaner.Delete.removeValidSenderFromList('${jsEscapedEmail}')" title="Remove from valid senders">
                        <svg viewBox="0 0 24 24" width="18" height="18">
                            <path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                        </svg>
                    </button>
                `;
          list.appendChild(item);
        });
    }

    modal.classList.remove("hidden");
  },

  closeValidSendersModal() {
    const modal = document.getElementById("validSendersModal");
    modal.classList.add("hidden");
  },

  async removeValidSenderFromList(email) {
    const emailLower = email.toLowerCase();
    try {
      // Remove from valid senders
      await fetch("/api/valid-senders", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sender_email: email }),
      });
      this.validSenders.delete(emailLower);
      this.updateReferenceCounts();
      this.displayResults();
      this.restoreSelectionState();
    } catch (error) {
      console.error("Error removing valid sender:", error);
      GmailCleaner.UI.showErrorToast("Failed to remove valid sender");
    }
    // Refresh the modal list
    await this.showValidSendersList();
  },

  async showKnownRecipientsList() {
    const modal = document.getElementById("knownRecipientsModal");
    const list = document.getElementById("knownRecipientsList");
    const empty = document.getElementById("knownRecipientsEmpty");

    // Refresh from server
    await this.loadMyRecipients();

    list.innerHTML = "";

    if (this.myRecipients.size === 0) {
      empty.classList.remove("hidden");
      list.classList.add("hidden");
    } else {
      empty.classList.add("hidden");
      list.classList.remove("hidden");

      Array.from(this.myRecipients)
        .sort()
        .forEach((email) => {
          const item = document.createElement("div");
          item.className = "reference-list-item";
          item.innerHTML = `
                    <span class="reference-email">${GmailCleaner.UI.escapeHtml(email)}</span>
                `;
          list.appendChild(item);
        });
    }

    modal.classList.remove("hidden");
  },

  closeKnownRecipientsModal() {
    const modal = document.getElementById("knownRecipientsModal");
    modal.classList.add("hidden");
  },

  // Selection state management
  getDomainCheckboxState(domain) {
    const group = this.domainGroups.find((g) => g.domain === domain);
    if (!group) return "none";

    // Only count non-protected senders
    const selectableSenders = group.senders.filter(
      (s) => !this.isProtectedSender(s.email),
    );
    if (selectableSenders.length === 0) return "none"; // All senders are protected

    const senderEmails = selectableSenders.map((s) => s.email);
    const selectedCount = senderEmails.filter((e) =>
      this.selectedSenders.has(e),
    ).length;

    if (selectedCount === 0) return "none";
    if (selectedCount === senderEmails.length) return "all";
    return "partial";
  },

  updateDomainCheckboxVisual(domain) {
    const checkbox = document.querySelector(
      `.domain-cb[data-domain="${CSS.escape(domain)}"]`,
    );
    if (!checkbox) return;

    const state = this.getDomainCheckboxState(domain);
    const checkmark = checkbox.nextElementSibling;

    checkbox.checked = state === "all";
    checkbox.indeterminate = state === "partial";

    if (checkmark) {
      checkmark.classList.toggle("indeterminate", state === "partial");
    }
  },

  updateAllDomainCheckboxStates() {
    this.domainGroups.forEach((group) => {
      this.updateDomainCheckboxVisual(group.domain);
    });
    this.updateSelectAllState();
  },

  updateSelectAllState() {
    const selectAll = document.getElementById("deleteSelectAll");
    if (!selectAll) return;

    if (this.groupByDomain) {
      const allDomains = this.domainGroups.length;
      const allSelected = this.domainGroups.every(
        (g) => this.getDomainCheckboxState(g.domain) === "all",
      );
      const someSelected = this.domainGroups.some(
        (g) => this.getDomainCheckboxState(g.domain) !== "none",
      );

      selectAll.checked = allDomains > 0 && allSelected;
      selectAll.indeterminate = someSelected && !allSelected;
    } else {
      // In flat view, only count non-protected senders
      const selectableResults = GmailCleaner.deleteResults.filter(
        (r) => !this.isProtectedSender(r.email),
      );
      const allSelectable = selectableResults.length;
      const selectedCount = selectableResults.filter((r) =>
        this.selectedSenders.has(r.email),
      ).length;
      selectAll.checked = allSelectable > 0 && selectedCount === allSelectable;
      selectAll.indeterminate =
        selectedCount > 0 && selectedCount < allSelectable;
    }
  },

  handleDomainCheckboxChange(domain, isChecked) {
    const group = this.domainGroups.find((g) => g.domain === domain);
    if (!group) return;

    const currentState = this.getDomainCheckboxState(domain);

    // Two-click cycle: partial → all, all → none, none → all
    let selectAll;
    if (currentState === "partial") {
      selectAll = true;
    } else if (currentState === "all") {
      selectAll = false;
    } else {
      selectAll = true;
    }

    // Update selectedSenders for all non-protected senders in this domain
    group.senders.forEach((sender) => {
      // Skip protected senders (valid senders and known recipients)
      if (this.isProtectedSender(sender.email)) return;

      if (selectAll) {
        this.selectedSenders.add(sender.email);
      } else {
        this.selectedSenders.delete(sender.email);
      }
    });

    // Update domain selection state
    if (selectAll) {
      this.selectedDomains.add(domain);
    } else {
      this.selectedDomains.delete(domain);
    }

    // Update visible sender checkboxes
    const senderContainer = document.querySelector(
      `.domain-senders-container[data-domain="${CSS.escape(domain)}"]`,
    );
    if (senderContainer) {
      senderContainer.querySelectorAll(".sender-cb").forEach((cb) => {
        cb.checked = selectAll;
      });
    }

    // Update visual state
    this.updateDomainCheckboxVisual(domain);
    this.updateSelectAllState();
    this.updateDomainDeleteButton(domain);
  },

  handleSenderCheckboxChange(email, domain, isChecked) {
    if (isChecked) {
      this.selectedSenders.add(email);
    } else {
      this.selectedSenders.delete(email);
    }

    // Update domain checkbox state
    this.updateDomainCheckboxVisual(domain);

    // Update selectedDomains based on state
    const state = this.getDomainCheckboxState(domain);
    if (state === "all") {
      this.selectedDomains.add(domain);
    } else {
      this.selectedDomains.delete(domain);
    }

    this.updateSelectAllState();
    this.updateDomainDeleteButton(domain);
  },

  handleFlatSenderCheckboxChange(email, isChecked) {
    if (isChecked) {
      this.selectedSenders.add(email);
    } else {
      this.selectedSenders.delete(email);
    }
    this.updateSelectAllState();
  },

  updateDomainDeleteButton(domain) {
    const group = this.domainGroups.find((g) => g.domain === domain);
    if (!group) return;

    // Find selected non-protected senders in this domain
    const selectedInDomain = group.senders.filter(
      (s) =>
        this.selectedSenders.has(s.email) && !this.isProtectedSender(s.email),
    );

    // Calculate email count: if selections exist, sum selected; otherwise 0
    const emailCount =
      selectedInDomain.length > 0
        ? selectedInDomain.reduce((sum, s) => sum + s.count, 0)
        : 0;

    // Find and update the button
    const btn = document.querySelector(
      `.delete-btn[data-domain="${CSS.escape(domain)}"]`,
    );
    if (btn) {
      btn.textContent = `Delete ${emailCount.toLocaleString()}`;
    }
  },

  restoreSelectionState() {
    // Restore domain checkbox states
    document.querySelectorAll(".domain-cb").forEach((cb) => {
      const domain = cb.dataset.domain;
      this.updateDomainCheckboxVisual(domain);
    });

    // Restore sender checkbox states
    document.querySelectorAll(".sender-cb, .delete-cb").forEach((cb) => {
      const email = cb.dataset.email;
      if (email) {
        cb.checked = this.selectedSenders.has(email);
      }
    });

    this.updateSelectAllState();
  },

  clearSelectionState() {
    this.selectedDomains.clear();
    this.selectedSenders.clear();
  },

  async startScan() {
    if (GmailCleaner.deleteScanning) return;

    const authResponse = await fetch("/api/auth-status");
    const authStatus = await authResponse.json();

    if (!authStatus.logged_in) {
      GmailCleaner.Auth.signIn();
      return;
    }

    GmailCleaner.deleteScanning = true;

    const scanBtn = document.getElementById("deleteScanBtn");
    const progressCard = document.getElementById("deleteProgressCard");

    scanBtn.disabled = true;
    scanBtn.innerHTML = `
            <svg class="spinner" viewBox="0 0 24 24" width="18" height="18">
                <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="60" stroke-linecap="round"/>
            </svg>
            Scanning...
        `;
    progressCard.classList.remove("hidden");

    const filters = GmailCleaner.Filters.get();

    try {
      // Always use the main scan endpoint (it now scans all and annotates results)
      const response = await fetch("/api/delete-scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          limit: 0, // Scan all
          filters: filters,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg =
          errorData.detail || `Request failed with status ${response.status}`;
        throw new Error(errorMsg);
      }

      this.pollProgress();
    } catch (error) {
      alert("Error: " + error.message);
      this.resetScan();
    }
  },

  async pollProgress() {
    try {
      const response = await fetch("/api/delete-scan-status");
      const status = await response.json();

      const progressBar = document.getElementById("deleteProgressBar");
      const progressText = document.getElementById("deleteProgressText");

      progressBar.style.width = status.progress + "%";
      progressText.textContent = status.message;

      if (status.done) {
        if (!status.error) {
          const resultsResponse = await fetch("/api/delete-scan-results");
          GmailCleaner.deleteResults = await resultsResponse.json();
          this.displayResults();
        } else {
          alert("Error: " + status.error);
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
    const scanBtn = document.getElementById("deleteScanBtn");
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
    const resultsList = document.getElementById("deleteResultsList");
    const resultsSection = document.getElementById("deleteResultsSection");
    const noResults = document.getElementById("deleteNoResults");
    const badge = document.getElementById("deleteSendersBadge");

    resultsList.innerHTML = "";

    if (GmailCleaner.deleteResults.length === 0) {
      badge.textContent = "0";
      resultsSection.classList.add("hidden");
      noResults.classList.remove("hidden");
      this.setActionButtonsEnabled(false);
      return;
    }

    resultsSection.classList.remove("hidden");
    noResults.classList.add("hidden");
    this.setActionButtonsEnabled(true);

    // Dispatch to the right renderer
    if (this.groupByDomain) {
      this.buildDomainGroups();
      this.displayDomainResults();
      badge.textContent = this.domainGroups.length + " domains";
    } else {
      this.displayFlatResults();
      badge.textContent = GmailCleaner.deleteResults.length;
    }
  },

  displayFlatResults() {
    const resultsList = document.getElementById("deleteResultsList");

    // Sort results by date or count
    const sortedResults = this.sortResults(GmailCleaner.deleteResults);

    sortedResults.forEach((r, i) => {
      // Find original index for actions
      const originalIndex = GmailCleaner.deleteResults.indexOf(r);
      const item = document.createElement("div");

      const emailLower = r.email.toLowerCase();
      const isValidSender = this.validSenders.has(emailLower);
      const isKnownRecipient = this.myRecipients.has(emailLower);
      const isOverride = this.recipientOverrides.has(emailLower);
      // Protected if: valid sender OR (known recipient WITHOUT override)
      const isProtected =
        isValidSender || (isKnownRecipient && !isOverride);

      item.className = "result-item" + (isProtected ? " protected-row" : "");

      const recentDate = this.formatMostRecentDate(r.first_date, r.last_date);
      const dateDisplay = recentDate
        ? `<div class="result-date-range">${recentDate}</div>`
        : "";
      const jsEscapedEmail = r.email.replace(/'/g, "\\'").replace(/"/g, '\\"');

      // Tri-state button: Green (valid) -> Orange (override) -> Red (default)
      let btnClass, btnTitle, btnIcon;
      if (isValidSender) {
        // Green state - protected
        btnClass = "valid";
        btnTitle = "Protected (click to mark as override)";
        btnIcon =
          '<path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>';
      } else if (isOverride) {
        // Orange state - override (can delete)
        btnClass = "override";
        btnTitle = "Override: Will be deleted (click to remove)";
        btnIcon =
          '<path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>';
      } else {
        // Red state - deletable (or protected if known recipient)
        btnClass = "invalid";
        btnTitle = isKnownRecipient
          ? "Known recipient - protected (click to protect)"
          : "Not protected (click to protect)";
        btnIcon =
          '<path fill="currentColor" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>';
      }

      // Checkbox and delete button (hidden for protected rows via CSS)
      const checkboxHtml = `
                <label class="checkbox-wrapper result-checkbox">
                    <input type="checkbox" class="delete-cb" data-index="${originalIndex}" data-email="${GmailCleaner.UI.escapeHtml(r.email)}" onchange="GmailCleaner.Delete.handleFlatSenderCheckboxChange('${jsEscapedEmail}', this.checked)" ${isProtected ? "disabled" : ""}>
                    <span class="checkmark"></span>
                </label>`;

      const deleteBtn = `
                <button class="unsub-btn delete-btn" id="delete-${originalIndex}" onclick="GmailCleaner.Delete.deleteSenderEmails(${originalIndex})" ${isProtected ? "disabled" : ""}>
                    Delete ${r.count}
                </button>`;

      item.innerHTML = `
                ${checkboxHtml}
                <div class="sender-status-buttons">
                    <button class="sender-status-btn valid-sender-btn ${btnClass}" onclick="GmailCleaner.Delete.cycleSenderState('${jsEscapedEmail}')" title="${btnTitle}">
                        <svg viewBox="0 0 24 24" width="14" height="14">${btnIcon}</svg>
                    </button>
                </div>
                <div class="result-content">
                    <div class="result-sender">${GmailCleaner.UI.escapeHtml(r.email)}</div>
                    <div class="result-subject">${GmailCleaner.UI.escapeHtml(r.subjects[0] || "No subject")}</div>
                    <div class="result-meta">
                        ${dateDisplay}
                        <span class="result-count">${r.count} emails</span>
                    </div>
                </div>
                <div class="result-actions">
                    ${deleteBtn}
                </div>
            `;
      resultsList.appendChild(item);
    });
  },

  toggleGroupByDomain() {
    const toggle = document.getElementById("groupByDomainToggle");
    this.groupByDomain = toggle.checked;

    // Reset selections when toggling
    document.getElementById("deleteSelectAll").checked = false;
    document.getElementById("deleteSelectAll").indeterminate = false;
    this.expandedDomains.clear();
    this.clearSelectionState();

    // Re-render
    this.displayResults();
  },

  buildDomainGroups() {
    const domainMap = new Map();

    GmailCleaner.deleteResults.forEach((sender) => {
      const domain =
        sender.domain || sender.email.split("@").pop().toLowerCase();
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
        sender.recipients.forEach((r) => group.uniqueRecipients.add(r));
      }

      // Track date range
      if (sender.first_date) {
        if (
          !group.firstDate ||
          new Date(sender.first_date) < new Date(group.firstDate)
        ) {
          group.firstDate = sender.first_date;
        }
      }
      if (sender.last_date) {
        if (
          !group.lastDate ||
          new Date(sender.last_date) > new Date(group.lastDate)
        ) {
          group.lastDate = sender.last_date;
        }
      }
    });

    // Convert sets to arrays (sorting happens in displayDomainResults)
    this.domainGroups = Array.from(domainMap.values()).map((group) => ({
      ...group,
      uniqueSenders: Array.from(group.uniqueSenders),
      uniqueRecipients: Array.from(group.uniqueRecipients),
    }));
  },

  displayDomainResults() {
    const resultsList = document.getElementById("deleteResultsList");

    // Sort domain groups by current sort settings
    const sortedGroups = this.sortDomainGroups(this.domainGroups);

    sortedGroups.forEach((group, i) => {
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
    const row = document.createElement("div");
    row.className = "result-item domain-row" + (isExpanded ? " expanded" : "");
    row.dataset.domain = group.domain;

    const recentDate = this.formatMostRecentDate(
      group.firstDate,
      group.lastDate,
    );
    const dateDisplay = recentDate
      ? `<div class="result-date-range">${recentDate}</div>`
      : "";

    const sendersTooltip = group.uniqueSenders.join("\n");
    const recipientsTooltip = group.uniqueRecipients.join("\n");

    const escapedDomain = GmailCleaner.UI.escapeHtml(group.domain);
    const jsEscapedDomain = group.domain
      .replace(/'/g, "\\'")
      .replace(/"/g, '\\"');

    row.innerHTML = `
            <label class="checkbox-wrapper result-checkbox">
                <input type="checkbox" class="domain-cb" data-domain="${escapedDomain}" data-index="${index}" onchange="GmailCleaner.Delete.handleDomainCheckboxChange('${jsEscapedDomain}', this.checked)">
                <span class="checkmark"></span>
            </label>
            <button class="expand-toggle" onclick="GmailCleaner.Delete.toggleDomainExpand('${escapedDomain}')">
                <svg viewBox="0 0 24 24" width="18" height="18">
                    <path fill="currentColor" d="${isExpanded ? "M7 10l5 5 5-5H7z" : "M10 17l5-5-5-5v10z"}"/>
                </svg>
            </button>
            <div class="result-content" onclick="GmailCleaner.Delete.toggleDomainExpand('${escapedDomain}')" style="cursor: pointer;">
                <div class="result-sender domain-name">${GmailCleaner.UI.escapeHtml(group.domain)}</div>
                <div class="domain-pills">
                    <span class="pill sender-pill" data-tooltip="${GmailCleaner.UI.escapeHtml(sendersTooltip)}">${group.uniqueSenders.length} sender${group.uniqueSenders.length !== 1 ? "s" : ""}</span>
                    ${group.uniqueRecipients.length > 0 ? `<span class="pill recipient-pill" data-tooltip="${GmailCleaner.UI.escapeHtml(recipientsTooltip)}">${group.uniqueRecipients.length} recipient${group.uniqueRecipients.length !== 1 ? "s" : ""}</span>` : ""}
                </div>
                <div class="result-meta">
                    ${dateDisplay}
                    <span class="result-count">${group.totalEmails} emails</span>
                </div>
            </div>
            <div class="result-actions">
                <button class="unsub-btn delete-btn" id="delete-domain-${index}" data-domain="${escapedDomain}" onclick="GmailCleaner.Delete.deleteDomainEmails('${GmailCleaner.UI.escapeHtml(group.domain)}')">
                    Delete 0
                </button>
            </div>
        `;

    return row;
  },

  createSendersTable(group) {
    const container = document.createElement("div");
    container.className = "domain-senders-container";
    container.dataset.domain = group.domain;

    // Sort senders by current sort settings (date or count)
    const sortedSenders = this.sortResults(group.senders);

    sortedSenders.forEach((sender) => {
      const originalIndex = GmailCleaner.deleteResults.indexOf(sender);
      const recipients = sender.recipients || [];
      const recipientsTooltip = recipients.join("\n");
      const jsEscapedEmail = sender.email
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"');
      const jsEscapedDomain = group.domain
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"');

      const emailLower = sender.email.toLowerCase();
      const isValidSender = this.validSenders.has(emailLower);
      const isKnownRecipient = this.myRecipients.has(emailLower);
      const isOverride = this.recipientOverrides.has(emailLower);
      // Protected if: valid sender OR (known recipient WITHOUT override)
      const isProtected =
        isValidSender || (isKnownRecipient && !isOverride);

      // Build recipients display: show first recipient inline with arrow
      let recipientsHtml = "";
      if (recipients.length > 0) {
        const firstRecipient = recipients[0];
        if (recipients.length === 1) {
          recipientsHtml = `<span class="recipient-inline">→ ${GmailCleaner.UI.escapeHtml(firstRecipient)}</span>`;
        } else {
          recipientsHtml = `<span class="recipient-inline" data-tooltip="${GmailCleaner.UI.escapeHtml(recipientsTooltip)}">→ ${GmailCleaner.UI.escapeHtml(firstRecipient)} <span class="recipient-more">+${recipients.length - 1}</span></span>`;
        }
      }

      // Build subjects display
      const subjects = sender.subjects || [];
      const subjectsTooltip = subjects.join("\n");
      const subjectInline =
        sender.count === 1 && subjects.length > 0
          ? `<div class="result-subject">${GmailCleaner.UI.escapeHtml(subjects[0])}</div>`
          : "";

      // Most recent date
      const recentDate = this.formatMostRecentDate(
        sender.first_date,
        sender.last_date,
      );

      // Email count: pill with tooltip if multiple emails with subjects
      const emailCountHtml =
        subjects.length > 0 && sender.count > 1
          ? `<span class="pill email-count-pill small" data-tooltip="${GmailCleaner.UI.escapeHtml(subjectsTooltip)}">${sender.count} emails</span>`
          : `<span class="result-count">${sender.count} emails</span>`;

      // Tri-state button: Green (valid) -> Orange (override) -> Red (default)
      let btnClass, btnTitle, btnIcon;
      if (isValidSender) {
        // Green state - protected
        btnClass = "valid";
        btnTitle = "Protected (click to mark as override)";
        btnIcon =
          '<path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>';
      } else if (isOverride) {
        // Orange state - override (can delete)
        btnClass = "override";
        btnTitle = "Override: Will be deleted (click to remove)";
        btnIcon =
          '<path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>';
      } else {
        // Red state - deletable (or protected if known recipient)
        btnClass = "invalid";
        btnTitle = isKnownRecipient
          ? "Known recipient - protected (click to protect)"
          : "Not protected (click to protect)";
        btnIcon =
          '<path fill="currentColor" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>';
      }

      const senderRow = document.createElement("div");
      senderRow.className =
        "result-item sender-row nested" + (isProtected ? " protected-row" : "");
      senderRow.innerHTML = `
                <label class="checkbox-wrapper result-checkbox">
                    <input type="checkbox" class="delete-cb sender-cb" data-index="${originalIndex}" data-email="${GmailCleaner.UI.escapeHtml(sender.email)}" data-domain="${GmailCleaner.UI.escapeHtml(group.domain)}" onchange="GmailCleaner.Delete.handleSenderCheckboxChange('${jsEscapedEmail}', '${jsEscapedDomain}', this.checked)" ${isProtected ? "disabled" : ""}>
                    <span class="checkmark"></span>
                </label>
                <div class="sender-status-buttons">
                    <button class="sender-status-btn valid-sender-btn ${btnClass}" onclick="GmailCleaner.Delete.cycleSenderState('${jsEscapedEmail}')" title="${btnTitle}">
                        <svg viewBox="0 0 24 24" width="14" height="14">${btnIcon}</svg>
                    </button>
                </div>
                <div class="result-content">
                    <div class="sender-recipient-row">
                        <span class="result-sender">${GmailCleaner.UI.escapeHtml(sender.display_email || sender.email)}</span>
                        ${recipientsHtml}
                    </div>
                    ${subjectInline}
                    <div class="result-meta">
                        ${recentDate ? `<span class="result-date">${recentDate}</span>` : ""}
                        ${emailCountHtml}
                    </div>
                </div>
                <div class="result-actions">
                    <button class="unsub-btn delete-btn" id="delete-${originalIndex}" onclick="GmailCleaner.Delete.deleteSenderEmails(${originalIndex})" ${isProtected ? "disabled" : ""}>
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
    this.restoreSelectionState();
  },

  async deleteDomainEmails(domain) {
    const group = this.domainGroups.find((g) => g.domain === domain);
    if (!group) return;

    // Only delete selected non-protected senders in this domain
    const selectedInDomain = group.senders.filter(
      (s) =>
        this.selectedSenders.has(s.email) && !this.isProtectedSender(s.email),
    );

    if (selectedInDomain.length === 0) {
      alert("No senders selected in this domain. Select senders to delete.");
      return;
    }

    const senderEmails = selectedInDomain.map((s) => s.email);
    const senderCount = senderEmails.length;
    const totalEmails = selectedInDomain.reduce((sum, s) => sum + s.count, 0);

    if (
      !confirm(
        `Delete ${totalEmails} emails from ${senderCount} sender${senderCount !== 1 ? "s" : ""} at @${domain}?\n\nThis will move them to Trash.`,
      )
    ) {
      return;
    }

    // Show bulk delete overlay
    this.showDeleteOverlay(senderCount, totalEmails);

    try {
      await fetch("/api/delete-emails-bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ senders: senderEmails }),
      });

      // Poll for progress using the same bulk delete status
      this.pollDomainDeleteProgress(domain);
    } catch (error) {
      this.hideDeleteOverlay();
      alert("Error: " + error.message);
    }
  },

  async pollDomainDeleteProgress(domain) {
    try {
      const response = await fetch("/api/delete-bulk-status");
      const status = await response.json();

      this.updateDeleteOverlay(status);

      if (status.done) {
        this.hideDeleteOverlay();

        if (!status.error) {
          const deletedCount = status.deleted_count || 0;
          GmailCleaner.UI.showSuccessToast(
            `Deleted ${deletedCount.toLocaleString()} emails from @${domain}`,
          );

          // Refresh results
          setTimeout(async () => {
            const resultsResponse = await fetch("/api/delete-scan-results");
            GmailCleaner.deleteResults = await resultsResponse.json();
            this.clearSelectionState();
            this.displayResults();
            document.getElementById("deleteSelectAll").checked = false;
            document.getElementById("deleteSelectAll").indeterminate = false;
          }, 1000);
        } else {
          alert("Error: " + status.error);
        }
      } else {
        setTimeout(() => this.pollDomainDeleteProgress(domain), 300);
      }
    } catch (error) {
      setTimeout(() => this.pollDomainDeleteProgress(domain), 500);
    }
  },

  setActionButtonsEnabled(enabled) {
    const buttons = [
      "applyLabelBtn",
      "archiveBtn",
      "importantBtn",
      "downloadBtn",
      "deleteSelectedBtn",
    ];
    buttons.forEach((id) => {
      const btn = document.getElementById(id);
      if (btn) {
        btn.disabled = !enabled;
      }
    });
  },

  toggleSelectAll() {
    const selectAll = document.getElementById("deleteSelectAll");
    const checked = selectAll.checked;

    // Clear selection state first
    this.selectedDomains.clear();
    this.selectedSenders.clear();

    if (this.groupByDomain) {
      // In domain view, update all domains and their senders (skip protected)
      this.domainGroups.forEach((group) => {
        if (checked) {
          // Only add domain if it has selectable senders
          const hasSelectableSenders = group.senders.some(
            (s) => !this.isProtectedSender(s.email),
          );
          if (hasSelectableSenders) {
            this.selectedDomains.add(group.domain);
          }
          group.senders.forEach((s) => {
            if (!this.isProtectedSender(s.email)) {
              this.selectedSenders.add(s.email);
            }
          });
        }
      });

      // Update checkboxes (only non-disabled ones)
      document.querySelectorAll(".domain-cb").forEach((cb) => {
        if (!cb.disabled) {
          cb.checked = checked;
          cb.indeterminate = false;
          const checkmark = cb.nextElementSibling;
          if (checkmark) checkmark.classList.remove("indeterminate");
        }
      });
      document.querySelectorAll(".sender-cb").forEach((cb) => {
        if (!cb.disabled) {
          cb.checked = checked;
        }
      });
    } else {
      // In flat view, select all sender checkboxes (skip protected)
      if (checked) {
        GmailCleaner.deleteResults.forEach((r) => {
          if (!this.isProtectedSender(r.email)) {
            this.selectedSenders.add(r.email);
          }
        });
      }
      document.querySelectorAll(".delete-cb").forEach((cb) => {
        if (!cb.disabled) {
          cb.checked = checked;
        }
      });
    }

    // Update visual states
    this.updateAllDomainCheckboxStates();
  },

  async deleteSenderEmails(index) {
    const r = GmailCleaner.deleteResults[index];
    const btn = document.getElementById("delete-" + index);

    // Safety check: don't delete protected senders
    if (this.isProtectedSender(r.email)) {
      alert(
        "This sender is protected (valid sender or known recipient) and cannot be deleted.",
      );
      return;
    }

    if (
      !confirm(
        `Delete ALL ${r.count} emails from ${r.email}?\n\nThis will move them to Trash.`,
      )
    ) {
      return;
    }

    btn.disabled = true;
    btn.classList.add("btn-deleting");
    btn.innerHTML = `
            <svg class="spinner" viewBox="0 0 24 24" width="14" height="14">
                <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="60" stroke-linecap="round"/>
            </svg>
            Deleting...
        `;

    try {
      const response = await fetch("/api/delete-emails", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sender: r.email }),
      });
      const result = await response.json();

      if (result.success) {
        btn.classList.remove("btn-deleting");
        btn.innerHTML = `✓ Deleted ${result.deleted}!`;
        btn.classList.add("success");
        GmailCleaner.UI.showSuccessToast(
          `Deleted ${result.deleted} emails from ${r.email}`,
        );
        setTimeout(() => {
          GmailCleaner.deleteResults = GmailCleaner.deleteResults.filter(
            (_, i) => i !== index,
          );
          this.displayResults();
        }, 1500);
      } else {
        btn.classList.remove("btn-deleting");
        btn.innerHTML = "Error";
        alert("Error: " + result.message);
        btn.disabled = false;
        btn.innerHTML = `Delete ${r.count}`;
      }
    } catch (error) {
      alert("Error: " + error.message);
      btn.classList.remove("btn-deleting");
      btn.disabled = false;
      btn.innerHTML = `Delete ${r.count}`;
    }
  },

  async deleteSelected() {
    // Use selectedSenders Set for reliable selection state
    // Double-check by filtering out any protected senders (defense in depth)
    const senderEmails = Array.from(this.selectedSenders).filter(
      (email) => !this.isProtectedSender(email),
    );

    if (senderEmails.length === 0) {
      alert("Please select at least one sender to delete emails from.");
      return;
    }

    // Calculate total email count
    let totalEmails = 0;
    senderEmails.forEach((email) => {
      const result = GmailCleaner.deleteResults.find((r) => r.email === email);
      if (result) totalEmails += result.count;
    });

    if (
      !confirm(
        `Delete ${totalEmails} emails from ${senderEmails.length} senders?\n\nThis will move them to Trash.`,
      )
    ) {
      return;
    }

    // Show bulk delete overlay with progress bar
    this.showDeleteOverlay(senderEmails.length, totalEmails);

    // Collect sender info for button updates
    const senderInfoList = senderEmails
      .map((email) => {
        const index = GmailCleaner.deleteResults.findIndex(
          (r) => r.email === email,
        );
        return {
          email,
          index,
          count: GmailCleaner.deleteResults[index]?.count || 0,
        };
      })
      .filter((info) => info.index >= 0);

    // Update buttons to show deleting state
    senderInfoList.forEach((info) => {
      const btn = document.getElementById("delete-" + info.index);
      if (btn) {
        btn.disabled = true;
        btn.classList.add("btn-deleting");
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
      await fetch("/api/delete-emails-bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ senders: senderEmails }),
      });

      // Poll for progress
      this.pollDeleteProgress(senderInfoList);
    } catch (error) {
      this.hideDeleteOverlay();
      alert("Error: " + error.message);
    }
  },

  async pollDeleteProgress(senderInfoList) {
    try {
      const response = await fetch("/api/delete-bulk-status");
      const status = await response.json();

      // Update progress bar in overlay
      this.updateDeleteOverlay(status);

      if (status.done) {
        this.hideDeleteOverlay();

        if (!status.error) {
          const deletedCount = status.deleted_count || 0;
          senderInfoList.forEach((info) => {
            const btn = document.getElementById("delete-" + info.index);
            if (btn) {
              btn.classList.remove("btn-deleting");
              btn.innerHTML = "✓ Deleted!";
              btn.classList.add("success");
            }
          });

          GmailCleaner.UI.showSuccessToast(
            `Deleted ${deletedCount.toLocaleString()} emails from ${senderInfoList.length} senders`,
          );

          setTimeout(async () => {
            const resultsResponse = await fetch("/api/delete-scan-results");
            GmailCleaner.deleteResults = await resultsResponse.json();
            this.clearSelectionState();
            this.displayResults();
            document.getElementById("deleteSelectAll").checked = false;
            document.getElementById("deleteSelectAll").indeterminate = false;
          }, 1000);
        } else {
          alert("Error: " + status.error);
          senderInfoList.forEach((info) => {
            const btn = document.getElementById("delete-" + info.index);
            if (btn) {
              btn.classList.remove("btn-deleting");
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

    const overlay = document.createElement("div");
    overlay.id = "deleteOverlay";
    overlay.className = "delete-overlay";
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
    const progressBar = document.getElementById("deleteBulkProgressBar");
    const progressText = document.getElementById("deleteBulkProgressText");
    const stats = document.getElementById("deleteBulkStats");
    const overlay = document.getElementById("deleteOverlay");

    if (progressBar) {
      progressBar.style.width = status.progress + "%";
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
    const overlay = document.getElementById("deleteOverlay");
    if (overlay) {
      overlay.remove();
    }
  },

  // Known senders cache functionality
  async startKnownSendersScan() {
    if (this.buildingKnownSenders) return;

    const authResponse = await fetch("/api/auth-status");
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
    const limit = getLimitValue("sentScanLimit");

    // Show building overlay
    this.showKnownSendersOverlay();

    try {
      const response = await fetch("/api/build-known-senders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: limit }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          errorData.detail || "Failed to start building known senders",
        );
      }

      // Poll for progress
      await this.pollKnownSendersProgress();
    } catch (error) {
      this.hideKnownSendersOverlay();
      this.buildingKnownSenders = false;
      alert("Error building known senders: " + error.message);
    }
  },

  async pollKnownSendersProgress() {
    try {
      const response = await fetch("/api/known-senders-status");
      const status = await response.json();

      this.updateKnownSendersOverlay(status);

      if (status.done) {
        this.hideKnownSendersOverlay();
        this.buildingKnownSenders = false;

        if (!status.error) {
          this.knownSendersCached = true;
          this.updateKnownSendersStatusText(status.sender_count);
        } else {
          alert("Error: " + status.error);
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

    const overlay = document.createElement("div");
    overlay.id = "knownSendersOverlay";
    overlay.className = "delete-overlay";
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
    const progressBar = document.getElementById("knownSendersProgressBar");
    const progressText = document.getElementById("knownSendersProgressText");
    const stats = document.getElementById("knownSendersStats");

    if (progressBar) {
      progressBar.style.width = status.progress + "%";
    }
    if (progressText) {
      progressText.textContent = status.message;
    }
    if (stats) {
      stats.textContent = `${status.sender_count || 0} contacts found from ${status.scanned_emails || 0} emails`;
    }
  },

  hideKnownSendersOverlay() {
    const overlay = document.getElementById("knownSendersOverlay");
    if (overlay) {
      overlay.remove();
    }
  },

  updateKnownSendersStatusText(count) {
    const statusText = document.getElementById("knownSendersStatusText");
    if (statusText) {
      statusText.textContent = `Known senders: ${count.toLocaleString()} contacts cached`;
      statusText.classList.add("cached");
    }
  },

  resetKnownSendersScan() {
    this.buildingKnownSenders = false;
    const scanBtn = document.getElementById("deleteUnknownBtn");
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
    const checkboxes = document.querySelectorAll(".delete-cb:checked");
    if (checkboxes.length === 0) {
      GmailCleaner.UI.showInfoToast(
        "Please select at least one sender to download emails from.",
      );
      return;
    }

    let totalEmails = 0;
    const senderEmails = [];
    checkboxes.forEach((cb) => {
      const index = parseInt(cb.dataset.index);
      const r = GmailCleaner.deleteResults[index];
      totalEmails += r.count;
      senderEmails.push(r.email);
    });

    // Show download overlay
    this.showDownloadOverlay(checkboxes.length, totalEmails);

    try {
      // Start background download
      await fetch("/api/download-emails", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ senders: senderEmails }),
      });

      // Poll for progress
      this.pollDownloadProgress();
    } catch (error) {
      this.hideDownloadOverlay();
      GmailCleaner.UI.showErrorToast("Error: " + error.message);
    }
  },

  async pollDownloadProgress() {
    try {
      const response = await fetch("/api/download-status");
      const status = await response.json();

      this.updateDownloadOverlay(status);

      if (status.done) {
        if (!status.error) {
          // Trigger CSV download
          window.location.href = "/api/download-csv";
          setTimeout(() => {
            this.hideDownloadOverlay();
            GmailCleaner.UI.showSuccessToast(
              `Successfully exported ${status.fetched_count.toLocaleString()} emails to CSV file. Check your downloads folder.`,
              "Tip: You can open the CSV in Excel or Google Sheets for easy viewing",
            );
          }, 500);
        } else {
          this.hideDownloadOverlay();
          GmailCleaner.UI.showErrorToast("Error: " + status.error);
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

    const overlay = document.createElement("div");
    overlay.id = "downloadOverlay";
    overlay.className = "download-overlay";
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
    const overlay = document.getElementById("downloadOverlay");
    if (!overlay) return;

    const progressBar = document.getElementById("downloadProgressBar");
    const progressText = document.getElementById("downloadProgressText");
    const stats = document.getElementById("downloadStats");

    if (progressBar) {
      progressBar.style.width = status.progress + "%";
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
    const overlay = document.getElementById("downloadOverlay");
    if (overlay) {
      overlay.remove();
    }
  },
};

// Global shortcuts
function startDeleteScan() {
  GmailCleaner.Delete.startScan();
}
function startKnownSendersScan() {
  GmailCleaner.Delete.startKnownSendersScan();
}
function toggleDeleteSelectAll() {
  GmailCleaner.Delete.toggleSelectAll();
}
function deleteSelectedSenders() {
  GmailCleaner.Delete.deleteSelected();
}
function downloadSelectedEmails() {
  GmailCleaner.Delete.downloadSelected();
}
