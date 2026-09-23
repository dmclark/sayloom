(() => {
  "use strict";

  const CLEANUP_DEBOUNCE_MS = 700;
  const PUBLICATION_DEBOUNCE_MS = 150;
  const WORKSPACE_PREFERENCES_KEY = "local-text.workspace-preferences.v1";
  const DEFAULT_STACKED_SHARE = 55;
  const DEFAULT_SIDE_BY_SIDE_SHARE = 50;
  const MINIMUM_ORIGINAL_SHARE = 25;
  const MAXIMUM_ORIGINAL_SHARE = 75;
  const EVIDENCE_EXCLUSION_DISPOSITIONS = new Set([
    "not_voiceitt",
    "cannot_reliably_reconstruct",
    "exclude",
  ]);
  const narrowWorkspace = window.matchMedia
    ? window.matchMedia("(max-width: 980px)")
    : { matches: false, addEventListener() {} };

  const elements = {
    original: document.querySelector("#original-text"),
    prepared: document.querySelector("#prepared-text"),
    cleanupEnabled: document.querySelector("#cleanup-enabled"),
    defaultPreparationMode: document.querySelector("#default-preparation-mode"),
    modeSaveState: document.querySelector("#mode-save-state"),
    runSmartCorrection: document.querySelector("#run-smart-correction"),
    smartCorrectionState: document.querySelector("#smart-correction-state"),
    smartTaskContextField: document.querySelector("#smart-task-context-field"),
    smartTaskContext: document.querySelector("#smart-task-context"),
    smartRepairReview: document.querySelector("#smart-repair-review"),
    smartRepairNote: document.querySelector("#smart-repair-note"),
    smartRepairSummary: document.querySelector("#smart-repair-summary"),
    smartRepairList: document.querySelector("#smart-repair-list"),
    smartRepairSelection: document.querySelector("#smart-repair-selection"),
    smartRepairContext: document.querySelector("#smart-repair-context"),
    smartRepairReason: document.querySelector("#smart-repair-reason"),
    runCleanup: document.querySelector("#run-cleanup"),
    clear: document.querySelector("#clear-text"),
    originalCount: document.querySelector("#original-count"),
    preparedCount: document.querySelector("#prepared-count"),
    outgoingKind: document.querySelector("#outgoing-kind"),
    selectPrepared: document.querySelector("#select-prepared"),
    selectOriginal: document.querySelector("#select-original"),
    copyOutgoing: document.querySelector("#copy-outgoing"),
    copyOutgoingState: document.querySelector("#copy-outgoing-state"),
    publication: document.querySelector("#publication-state"),
    cleanupRecovery: document.querySelector("#cleanup-recovery"),
    cleanupStatus: document.querySelector("#cleanup-status"),
    retryCleanup: document.querySelector("#retry-cleanup"),
    modelLabel: document.querySelector("#model-label"),
    cleanupDisclosure: document.querySelector("#cleanup-disclosure"),
    cleanupDisclosureSummary: document.querySelector("#cleanup-disclosure-summary"),
    cleanupRouteList: document.querySelector("#cleanup-route-list"),
    cleanupProcessingDisclosure: document.querySelector("#cleanup-processing-disclosure"),
    cleanupFallbackDisclosure: document.querySelector("#cleanup-fallback-disclosure"),
    cleanupCorpusDisclosure: document.querySelector("#cleanup-corpus-disclosure"),
    cleanupValidationDetail: document.querySelector("#cleanup-validation-detail"),
    workspaceShell: document.querySelector(".workspace-shell"),
    workspace: document.querySelector(".workspace"),
    workspaceResizer: document.querySelector("#workspace-resizer"),
    layoutStacked: document.querySelector("#layout-stacked"),
    layoutSideBySide: document.querySelector("#layout-side-by-side"),
    maximizeOriginal: document.querySelector("#maximize-original"),
    maximizeOriginalIcon: document.querySelector("#maximize-original span"),
    maximizePrepared: document.querySelector("#maximize-prepared"),
    maximizePreparedIcon: document.querySelector("#maximize-prepared span"),
    toggleSidebar: document.querySelector("#toggle-sidebar"),
    toggleSidebarIcon: document.querySelector("#toggle-sidebar span"),
    errorDialog: document.querySelector("#error-details-dialog"),
    errorLedger: document.querySelector("#error-details-ledger"),
    closeErrorDialog: document.querySelector("#close-error-details"),
    copyError: document.querySelector("#copy-error-details"),
    workspaceControls: document.querySelector("#workspace-controls"),
    workspaceOutgoing: document.querySelector("#workspace-outgoing"),
    navWorkspace: document.querySelector("#nav-workspace"),
    navSettings: document.querySelector("#nav-settings"),
    navEvaluation: document.querySelector("#nav-evaluation"),
    settingsManager: document.querySelector("#settings-manager"),
    targetList: document.querySelector("#target-list"),
    targetAddItem: document.querySelector("#target-add-item"),
    newTarget: document.querySelector("#new-target"),
    targetDialog: document.querySelector("#target-dialog"),
    targetDetail: document.querySelector("#target-detail"),
    targetListBack: document.querySelector("#target-list-back"),
    targetDetailTitle: document.querySelector("#target-detail-title"),
    targetPrimaryState: document.querySelector("#target-primary-state"),
    targetSaveState: document.querySelector("#target-save-state"),
    targetPreset: document.querySelector("#target-preset"),
    targetDisplayName: document.querySelector("#target-display-name"),
    targetApplicationName: document.querySelector("#target-application-name"),
    targetBundleId: document.querySelector("#target-bundle-id"),
    targetIcon: document.querySelector("#target-icon"),
    targetStrategy: document.querySelector("#target-strategy"),
    targetPreview: document.querySelector("#target-preview"),
    targetInstallationState: document.querySelector("#target-installation-state"),
    targetAvailability: document.querySelector("#target-availability"),
    targetPermission: document.querySelector("#target-permission"),
    targetReadinessAction: document.querySelector("#target-readiness-action"),
    targetErrors: document.querySelector("#target-errors"),
    installTarget: document.querySelector("#install-target"),
    checkTarget: document.querySelector("#check-target"),
    toggleTargetEnabled: document.querySelector("#toggle-target-enabled"),
    removeTarget: document.querySelector("#remove-target"),
    evidenceCollectionControl: document.querySelector(".evidence-collection-control"),
    evidenceCollectionToggle: document.querySelector("#evidence-collection-toggle"),
    evidenceCollectionState: document.querySelector("#evidence-collection-state"),
    withdrawEvidence: document.querySelector("#withdraw-evidence"),
    evidenceAttestationDialog: document.querySelector("#evidence-attestation-dialog"),
    evidenceAttestationForm: document.querySelector("#evidence-attestation-form"),
    evidenceSourceAttestation: document.querySelector("#evidence-source-attestation"),
    evidenceAttestationStatus: document.querySelector("#evidence-attestation-status"),
    cancelEvidenceAttestation: document.querySelector("#cancel-evidence-attestation"),
    cancelEvidenceAttestationSecondary: document.querySelector("#cancel-evidence-attestation-secondary"),
    evidenceJudgmentDialog: document.querySelector("#evidence-judgment-dialog"),
    evidenceJudgmentTitle: document.querySelector("#evidence-judgment-title"),
    evidenceJudgmentForm: document.querySelector("#evidence-judgment-form"),
    evidenceDisposition: document.querySelector("#evidence-disposition"),
    evidenceIntendedField: document.querySelector("#evidence-intended-field"),
    evidenceIntendedText: document.querySelector("#evidence-intended-text"),
    evidenceJudgmentStatus: document.querySelector("#evidence-judgment-status"),
    cancelEvidenceJudgment: document.querySelector("#cancel-evidence-judgment"),
    cancelEvidenceJudgmentSecondary: document.querySelector("#cancel-evidence-judgment-secondary"),
    evidenceFailureDialog: document.querySelector("#evidence-failure-dialog"),
    evidenceFailureMessage: document.querySelector("#evidence-failure-message"),
    retryEvidenceCollection: document.querySelector("#retry-evidence-collection"),
    continueWithoutEvidence: document.querySelector("#continue-without-evidence"),
    cancelEvidenceRecovery: document.querySelector("#cancel-evidence-recovery"),
    saveEvaluationCase: document.querySelector("#save-evaluation-case"),
    evaluationManager: document.querySelector("#evaluation-manager"),
    evaluationStatus: document.querySelector("#evaluation-status"),
    evaluationCaseList: document.querySelector("#evaluation-case-list"),
    refreshEvaluation: document.querySelector("#refresh-evaluation"),
    previewEvaluationExport: document.querySelector("#preview-evaluation-export"),
    evaluationCaptureDialog: document.querySelector("#evaluation-capture-dialog"),
    evaluationCaptureForm: document.querySelector("#evaluation-capture-form"),
    evaluationSourceCategory: document.querySelector("#evaluation-source-category"),
    evaluationSourceText: document.querySelector("#evaluation-source-text"),
    evaluationProviderOutput: document.querySelector("#evaluation-provider-output"),
    evaluationExpectedCleanup: document.querySelector("#evaluation-expected-cleanup"),
    evaluationProviderContext: document.querySelector("#evaluation-provider-context"),
    evaluationPromptContext: document.querySelector("#evaluation-prompt-context"),
    evaluationCaptureStatus: document.querySelector("#evaluation-capture-status"),
    cancelEvaluationCapture: document.querySelector("#cancel-evaluation-capture"),
    cancelEvaluationCaptureSecondary: document.querySelector("#cancel-evaluation-capture-secondary"),
    evaluationReviewDialog: document.querySelector("#evaluation-review-dialog"),
    evaluationReviewMetadata: document.querySelector("#evaluation-review-metadata"),
    evaluationReviewSource: document.querySelector("#evaluation-review-source"),
    evaluationReviewProviderOutput: document.querySelector("#evaluation-review-provider-output"),
    evaluationReviewExpected: document.querySelector("#evaluation-review-expected"),
    evaluationReviewStatus: document.querySelector("#evaluation-review-status"),
    closeEvaluationReview: document.querySelector("#close-evaluation-review"),
    evaluationExpiryForm: document.querySelector("#evaluation-expiry-form"),
    evaluationEarlierExpiry: document.querySelector("#evaluation-earlier-expiry"),
    evaluationHoldForm: document.querySelector("#evaluation-hold-form"),
    evaluationBenchmarkId: document.querySelector("#evaluation-benchmark-id"),
    evaluationBenchmarkRelease: document.querySelector("#evaluation-benchmark-release"),
    deleteEvaluationCase: document.querySelector("#delete-evaluation-case"),
    evaluationExportDialog: document.querySelector("#evaluation-export-dialog"),
    evaluationExportWarning: document.querySelector("#evaluation-export-warning"),
    evaluationExportMetadata: document.querySelector("#evaluation-export-metadata"),
    evaluationExportStatus: document.querySelector("#evaluation-export-status"),
    confirmEvaluationExport: document.querySelector("#confirm-evaluation-export"),
    cancelEvaluationExport: document.querySelector("#cancel-evaluation-export"),
    cancelEvaluationExportSecondary: document.querySelector("#cancel-evaluation-export-secondary"),
  };

  let status = "unchanged";
  let cleanupTimer = null;
  let publicationTimer = null;
  let copyFeedbackTimer = null;
  let publicationChain = Promise.resolve();
  let publicationSequence = 0;
  let activeRequest = null;
  let requestSequence = 0;
  let replaceAllPending = false;
  let syntheticPastePending = false;
  let syntheticPasteTimer = null;
  let returnSelectionPending = false;
  let activeResizePointer = null;
  let layoutPreference = "stacked";
  let stackedShare = DEFAULT_STACKED_SHARE;
  let sideBySideShare = DEFAULT_SIDE_BY_SIDE_SHARE;
  let sidebarCollapsed = false;
  let maximizedPane = null;
  let originalOutgoingOverride = false;
  let defaultPreparationMode = "conservative";
  let draftCorrectionMode = null;
  let currentOriginalText = elements.original.value;
  let explicitSmartState = "hidden";
  let explicitSmartMessage = "";
  let smartRepairs = [];
  let selectedSmartRepair = null;
  let smartRepairResultCurrent = false;
  let targetRecords = [];
  let selectedTargetId = null;
  let targetDirty = false;
  let targetDraftIsNew = false;
  let targetLocalError = null;
  let evidenceReady = false;
  let evidenceLease = null;
  let evidenceLeaseTimer = null;
  let blockedEvidenceLease = null;
  let evidenceReceipt = null;
  let frozenEvidence = null;
  let evidenceRecovery = null;
  let evidenceCancellation = Promise.resolve();
  let evaluationAvailable = false;
  let currentEvaluation = null;
  let evaluationCases = [];
  let reviewedEvaluationCase = null;
  let evaluationExportPreview = null;
  const errors = { cleanup: null, publication: null };
  const browserSessionId = globalThis.crypto?.randomUUID?.()
    || `00000000-0000-4000-8000-${String(Math.random()).slice(2).padEnd(12, "0").slice(0, 12)}`;
  const evidenceLeaseStorageKey = "local-text.evidence-lease.v1";

  function storedEvidenceLease() {
    try {
      return globalThis.sessionStorage?.getItem(evidenceLeaseStorageKey) || null;
    } catch (_error) {
      return null;
    }
  }

  function storeEvidenceLease(leaseToken) {
    try {
      if (leaseToken) globalThis.sessionStorage?.setItem(evidenceLeaseStorageKey, leaseToken);
      else globalThis.sessionStorage?.removeItem(evidenceLeaseStorageKey);
    } catch (_error) { /* Reload disarming still has the pagehide fallback. */ }
  }

  const targetPresets = {
    amp: ["Amp", "Amp", "com.google.Chrome.app.bpgpkfmeagdpdcenbogglipmfkalmple", "synthetic_paste"],
    iterm: ["iTerm", "iTerm", "com.googlecode.iterm2", "iterm_write"],
    supacode: ["Supacode", "Supacode", "app.supabit.supacode", "synthetic_paste"],
    "vs-code": ["VS Code", "Visual Studio Code", "com.microsoft.VSCode", "synthetic_paste"],
  };

  function setStatus(nextStatus) {
    status = nextStatus;
    elements.outgoingKind.dataset.state = nextStatus;
    renderCountsAndSelection();
  }

  function effectiveCorrectionMode() {
    return draftCorrectionMode || (defaultPreparationMode === "smart" ? "smart" : "conservative");
  }

  function isEvidenceExclusion(disposition) {
    return EVIDENCE_EXCLUSION_DISPOSITIONS.has(disposition);
  }

  function renderExplicitSmartAction() {
    const automaticSmart = draftCorrectionMode === "smart";
    const buttonVisible = !automaticSmart
      && ["available", "running", "retry", "waiting"].includes(explicitSmartState);
    elements.runSmartCorrection.hidden = !buttonVisible;
    elements.runSmartCorrection.disabled = ["running", "waiting"].includes(explicitSmartState);
    elements.runSmartCorrection.textContent = {
      available: "Run Smart correction",
      running: "Running Smart correction…",
      retry: "Retry Smart correction",
      waiting: "Waiting for Intended wording…",
    }[explicitSmartState] || "Run Smart correction";
    elements.smartCorrectionState.hidden = !explicitSmartMessage || automaticSmart;
    elements.smartCorrectionState.textContent = automaticSmart ? "" : explicitSmartMessage;
    elements.retryCleanup.hidden = explicitSmartState === "retry";
  }

  function setExplicitSmartState(nextState, message = "") {
    explicitSmartState = nextState;
    explicitSmartMessage = message;
    renderExplicitSmartAction();
  }

  function validateSmartRepairs(repairs, originalText, preparedText) {
    if (!Array.isArray(repairs)) return false;
    const operations = new Set(["addition", "removal", "replacement"]);
    const originalCharacters = Array.from(originalText);
    const preparedCharacters = Array.from(preparedText);
    const codePointOffsets = (characters) => {
      const offsets = [0];
      characters.forEach((character) => offsets.push(offsets.at(-1) + character.length));
      return offsets;
    };
    const originalOffsets = codePointOffsets(originalCharacters);
    const preparedOffsets = codePointOffsets(preparedCharacters);
    const lexicalTokens = (text) => [...text.matchAll(/[\p{L}\p{N}\p{M}_]+(?:['’][\p{L}\p{N}\p{M}_]+)*['’]?/gu)]
      .map((match) => {
        const word = match[0].toLocaleLowerCase().replaceAll("’", "'");
        const forms = [word.replaceAll("'", "")];
        if (word.endsWith("'s")) forms.push(word.slice(0, -2).replaceAll("'", ""));
        return {
          start: match.index,
          end: match.index + match[0].length,
          canonical: forms.sort((left, right) => left.length - right.length || left.localeCompare(right))[0],
        };
      });
    const originalTokens = lexicalTokens(originalText);
    const preparedTokens = lexicalTokens(preparedText);
    const validSpan = (span, characters) => {
      return span
      && Number.isInteger(span.start)
      && Number.isInteger(span.end)
      && span.start >= 0
      && span.end >= span.start
      && span.end <= characters.length
      && typeof span.text === "string"
      && span.text === characters.slice(span.start, span.end).join("");
    };
    let previousOriginalEnd = 0;
    let previousPreparedEnd = 0;
    const validRepairs = repairs.every((repair, index) => {
      if (
        !repair || !operations.has(repair.operation)
        || repair.queue_position !== index + 1
        || typeof repair.context !== "string"
        || typeof repair.inspection_reason !== "string"
        || !validSpan(repair.original_span, originalCharacters)
        || !validSpan(repair.prepared_span, preparedCharacters)
      ) return false;
      const originalEmpty = repair.original_span.start === repair.original_span.end;
      const preparedEmpty = repair.prepared_span.start === repair.prepared_span.end;
      const ordered = repair.original_span.start >= previousOriginalEnd
        && repair.prepared_span.start >= previousPreparedEnd;
      previousOriginalEnd = repair.original_span.end;
      previousPreparedEnd = repair.prepared_span.end;
      return ordered && {
        addition: originalEmpty && !preparedEmpty,
        removal: !originalEmpty && preparedEmpty,
        replacement: !originalEmpty && !preparedEmpty,
      }[repair.operation];
    });
    if (!validRepairs) return false;
    const unaffected = (tokens, spans) => tokens
      .filter((token) => !spans.some(
        (span) => span.start < span.end && token.start >= span.start && token.end <= span.end,
      ))
      .map((token) => token.canonical);
    const utf16Spans = (key, offsets) => repairs.map((repair) => ({
      start: offsets[repair[key].start],
      end: offsets[repair[key].end],
    }));
    const originalUnaffected = unaffected(originalTokens, utf16Spans("original_span", originalOffsets));
    const preparedUnaffected = unaffected(preparedTokens, utf16Spans("prepared_span", preparedOffsets));
    return originalUnaffected.length === preparedUnaffected.length
      && originalUnaffected.every((token, index) => token === preparedUnaffected[index]);
  }

  function invalidateSmartRepairReview() {
    smartRepairs = [];
    selectedSmartRepair = null;
    smartRepairResultCurrent = false;
    elements.prepared.dataset.repairCount = "0";
    renderSmartRepairReview();
  }

  function renderSmartRepairReview() {
    elements.smartRepairReview.hidden = !smartRepairResultCurrent;
    elements.workspace.classList.toggle("has-smart-repair-review", smartRepairResultCurrent);
    elements.smartRepairList.textContent = "";
    if (!smartRepairResultCurrent) {
      elements.smartRepairSelection.hidden = true;
      return;
    }

    elements.smartRepairSummary.textContent = smartRepairs.length === 0
      ? "No lexical repairs"
      : `${smartRepairs.length} repair${smartRepairs.length === 1 ? "" : "s"}`;
    smartRepairs.forEach((repair) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      const meta = document.createElement("span");
      const change = document.createElement("span");
      const original = document.createElement("del");
      const separator = document.createElement("span");
      const prepared = document.createElement("ins");
      button.type = "button";
      button.className = "smart-repair-item";
      button.setAttribute("aria-current", String(repair.queue_position === selectedSmartRepair));
      meta.className = "smart-repair-item-meta";
      meta.textContent = `${repair.queue_position} · ${repair.operation}`;
      change.className = "smart-repair-item-change";
      original.textContent = repair.original_span.text || "∅";
      original.setAttribute("aria-label", `Original: ${original.textContent}`);
      separator.textContent = " → ";
      separator.setAttribute("aria-hidden", "true");
      prepared.textContent = repair.prepared_span.text || "∅";
      prepared.setAttribute("aria-label", `Prepared: ${prepared.textContent}`);
      change.append(original, separator, prepared);
      button.append(meta, change);
      button.addEventListener("click", () => selectSmartRepair(repair.queue_position));
      item.append(button);
      elements.smartRepairList.append(item);
    });

    const selected = smartRepairs.find(
      (repair) => repair.queue_position === selectedSmartRepair,
    );
    elements.smartRepairSelection.hidden = !selected;
    elements.smartRepairNote.hidden = Boolean(selected);
    if (!selected) return;
    elements.smartRepairContext.textContent = `Context: ${selected.context}`;
    elements.smartRepairContext.title = elements.smartRepairContext.textContent;
    elements.smartRepairReason.textContent = selected.inspection_reason;
    elements.smartRepairReason.title = elements.smartRepairReason.textContent;
  }

  function selectSmartRepair(queuePosition) {
    const repair = smartRepairs.find((candidate) => candidate.queue_position === queuePosition);
    if (!repair) return;
    selectedSmartRepair = queuePosition;
    renderSmartRepairReview();
    const span = repair.operation === "removal" ? repair.original_span : repair.prepared_span;
    const editor = repair.operation === "removal" ? elements.original : elements.prepared;
    const utf16Start = Array.from(editor.value).slice(0, span.start).join("").length;
    const utf16End = Array.from(editor.value).slice(0, span.end).join("").length;
    editor.focus({ preventScroll: true });
    editor.setSelectionRange(utf16Start, utf16End);
  }

  function showSmartRepairResult(repairs) {
    smartRepairs = repairs;
    selectedSmartRepair = null;
    smartRepairResultCurrent = true;
    elements.prepared.dataset.repairCount = String(repairs.length);
    renderSmartRepairReview();
  }

  function renderCorrectionMode() {
    elements.defaultPreparationMode.value = defaultPreparationMode;
    elements.smartTaskContextField.hidden = draftCorrectionMode !== "smart";
    elements.smartTaskContext.disabled = draftCorrectionMode !== "smart";
    renderExplicitSmartAction();
  }

  function readWorkspacePreferences() {
    try {
      const saved = JSON.parse(window.localStorage?.getItem(WORKSPACE_PREFERENCES_KEY) || "{}");
      if (["stacked", "side-by-side"].includes(saved.layout)) layoutPreference = saved.layout;
      if (Number.isFinite(saved.stackedShare)) stackedShare = saved.stackedShare;
      if (Number.isFinite(saved.sideBySideShare)) sideBySideShare = saved.sideBySideShare;
      sidebarCollapsed = saved.sidebarCollapsed === true;
    } catch (_error) {
      // Browser storage can be unavailable; interface preferences are optional.
    }
  }

  function saveWorkspacePreferences() {
    try {
      window.localStorage?.setItem(WORKSPACE_PREFERENCES_KEY, JSON.stringify({
        layout: layoutPreference,
        stackedShare,
        sideBySideShare,
        sidebarCollapsed,
      }));
    } catch (_error) {
      // Keep the workspace usable when browser storage is blocked.
    }
  }

  function effectiveLayout() {
    return narrowWorkspace.matches ? "stacked" : layoutPreference;
  }

  function setWorkspaceShare(value, persist = false) {
    const originalShare = Math.min(
      MAXIMUM_ORIGINAL_SHARE,
      Math.max(MINIMUM_ORIGINAL_SHARE, Math.round(value)),
    );
    if (effectiveLayout() === "side-by-side") sideBySideShare = originalShare;
    else stackedShare = originalShare;
    elements.workspace.style.setProperty("--original-share", `${originalShare}fr`);
    elements.workspace.style.setProperty("--prepared-share", `${100 - originalShare}fr`);
    elements.workspaceResizer.setAttribute("aria-valuenow", String(originalShare));
    elements.workspaceResizer.setAttribute(
      "aria-valuetext",
      `Original ${originalShare} percent, Prepared ${100 - originalShare} percent`,
    );
    if (persist) saveWorkspacePreferences();
  }

  function renderWorkspaceLayout() {
    const layout = effectiveLayout();
    const sideBySide = layout === "side-by-side";
    elements.workspace.classList.toggle("is-side-by-side", sideBySide);
    elements.layoutStacked.setAttribute("aria-pressed", String(!sideBySide));
    elements.layoutSideBySide.setAttribute("aria-pressed", String(sideBySide));
    elements.layoutSideBySide.disabled = narrowWorkspace.matches;
    elements.layoutSideBySide.title = narrowWorkspace.matches
      ? "Side-by-side layout is available on wider viewports"
      : "";
    elements.workspaceResizer.setAttribute("aria-orientation", sideBySide ? "vertical" : "horizontal");
    setWorkspaceShare(sideBySide ? sideBySideShare : stackedShare);
  }

  function setLayoutPreference(layout) {
    layoutPreference = layout;
    maximizedPane = null;
    renderMaximizedPane();
    renderWorkspaceLayout();
    saveWorkspacePreferences();
  }

  function renderSidebar() {
    elements.workspaceShell.classList.toggle("is-sidebar-collapsed", sidebarCollapsed);
    elements.toggleSidebar.setAttribute("aria-expanded", String(!sidebarCollapsed));
    elements.toggleSidebar.setAttribute(
      "aria-label",
      sidebarCollapsed ? "Expand navigation" : "Collapse navigation",
    );
    elements.toggleSidebarIcon.textContent = sidebarCollapsed ? "›" : "‹";
  }

  function renderMaximizedPane() {
    elements.workspace.classList.toggle("is-original-maximized", maximizedPane === "original");
    elements.workspace.classList.toggle("is-prepared-maximized", maximizedPane === "prepared");
    [
      ["original", elements.maximizeOriginal, elements.maximizeOriginalIcon],
      ["prepared", elements.maximizePrepared, elements.maximizePreparedIcon],
    ].forEach(([pane, button, icon]) => {
        const maximized = maximizedPane === pane;
        const label = pane === "original" ? "Original" : "Prepared";
        button.setAttribute("aria-pressed", String(maximized));
        button.setAttribute("aria-label", `${maximized ? "Restore" : "Maximize"} ${label} pane`);
        icon.textContent = maximized ? "Restore" : "Maximize";
      });
  }

  function toggleMaximizedPane(pane) {
    maximizedPane = maximizedPane === pane ? null : pane;
    renderMaximizedPane();
  }

  function resizeFromPointer(event) {
    const bounds = elements.workspace.getBoundingClientRect();
    const share = effectiveLayout() === "side-by-side"
      ? ((event.clientX - bounds.left) / bounds.width) * 100
      : ((event.clientY - bounds.top) / bounds.height) * 100;
    setWorkspaceShare(share);
  }

  function preparedIsCurrent() {
    return elements.cleanupEnabled.checked
      && Boolean(elements.original.value)
      && (status === "prepared" || status === "unchanged")
      && Boolean(elements.prepared.value);
  }

  function fallbackLabel() {
    if (!elements.original.value) return "Nothing yet";
    if (originalOutgoingOverride) return "Using Original — Selected for this draft";
    if (preparedIsCurrent()) return status === "unchanged"
      ? "Using Prepared — Result unchanged"
      : "Using Prepared";
    return {
      waiting: "Using Original — Replacement Prepared pending",
      cleaning: "Using Original — Cleanup in progress",
      disabled: "Using Original — Cleanup disabled",
      timeout: "Using Original",
      error: "Using Original",
    }[status] || "Using Original — Prepared unavailable";
  }

  function selectedOutgoingState() {
    const originalText = elements.original.value;
    const preparedText = elements.prepared.value;
    const usePrepared = !originalOutgoingOverride && preparedIsCurrent();
    const outgoingText = usePrepared ? preparedText : originalText;
    const outgoingKind = outgoingText ? (usePrepared ? "prepared" : "original") : "empty";

    return {
      cleanup_enabled: elements.cleanupEnabled.checked,
      original_text: originalText,
      prepared_text: preparedText,
      outgoing_text: outgoingText,
      outgoing_kind: outgoingKind,
      status,
      correction_mode: effectiveCorrectionMode(),
      evidence_lease_token: evidenceLease || blockedEvidenceLease,
      evidence_receipt: evidenceReceipt?.originalText === originalText
        ? evidenceReceipt.token
        : null,
    };
  }

  function renderCountsAndSelection() {
    elements.originalCount.textContent = String(elements.original.value.length);
    elements.preparedCount.textContent = String(elements.prepared.value.length);
    const usePrepared = selectedOutgoingState().outgoing_kind === "prepared";
    elements.selectPrepared.disabled = !preparedIsCurrent();
    elements.selectPrepared.setAttribute("aria-pressed", String(usePrepared));
    elements.selectOriginal.setAttribute("aria-pressed", String(!usePrepared));
    elements.outgoingKind.textContent = fallbackLabel();
    elements.copyOutgoing.disabled = !selectedOutgoingState().outgoing_text;
  }

  function setPublicationState(nextState, label) {
    elements.publication.dataset.state = nextState;
    elements.publication.lastElementChild.textContent = label;
    elements.publication.hidden = nextState !== "error";
  }

  function invalidateEvaluationCapture() {
    currentEvaluation = null;
    elements.saveEvaluationCase.disabled = true;
  }

  function renderCleanupConfiguration(configuration) {
    const routes = Array.isArray(configuration?.routes) ? configuration.routes : [];
    const disclosure = configuration?.disclosure || {};
    elements.cleanupDisclosure.dataset.status = configuration?.status || "unavailable";
    elements.cleanupDisclosureSummary.textContent = typeof disclosure.summary === "string"
      ? disclosure.summary
      : "Cleanup provider is not configured";
    elements.cleanupRouteList.textContent = "";
    routes.forEach((route) => {
      if (typeof route?.provider !== "string" || typeof route?.model !== "string") return;
      const item = document.createElement("li");
      const provider = route.provider === "openai"
        ? "OpenAI"
        : route.provider.charAt(0).toUpperCase() + route.provider.slice(1);
      item.textContent = `${provider} · ${route.model}`;
      elements.cleanupRouteList.append(item);
    });
    elements.cleanupRouteList.hidden = routes.length === 0;
    elements.cleanupProcessingDisclosure.textContent = disclosure.processing || "";
    elements.cleanupFallbackDisclosure.textContent = disclosure.fallback || "";
    elements.cleanupCorpusDisclosure.textContent = disclosure.corpus || "";
    const validationError = configuration?.validation_error;
    elements.cleanupValidationDetail.hidden = typeof validationError !== "string";
    elements.cleanupValidationDetail.textContent = typeof validationError === "string"
      ? `Configuration status: ${validationError.replaceAll("_", " ")}.`
      : "";

    elements.modelLabel.textContent = routes.length
      ? routes.map((route) => route.provider === "openai" ? "OpenAI" : "Gemini").join(" → ")
      : configuration?.status === "invalid"
        ? "Cleanup configuration invalid"
        : "Cleanup configuration needed";
  }

  function errorFields(error) {
    return [
      ["Operation", error.operation],
      ["Local time", error.localTime],
      ["Model", error.model === null ? "Not available" : error.model],
      ["HTTP status", error.httpStatus === null ? "Not available" : String(error.httpStatus)],
      ["Code", error.code],
      ["Sanitized message", error.message],
      ["Recovery action", error.retryAction],
    ];
  }

  function errorTrigger(kind) {
    return kind === "cleanup" ? elements.cleanupStatus : elements.publication;
  }

  function makeError({ operation, summary, model = null, httpStatus = null, code, message, retryAction }) {
    return {
      operation,
      summary,
      localTime: new Date().toLocaleString(),
      model,
      httpStatus,
      code,
      message,
      retryAction,
    };
  }

  function setError(kind, error) {
    errors[kind] = error;
    const trigger = errorTrigger(kind);
    if (kind === "cleanup") elements.cleanupRecovery.hidden = error === null;
    else trigger.disabled = error === null;
    trigger.classList.toggle("has-error-details", error !== null);
    if (error === null) {
      trigger.removeAttribute("aria-label");
      if (elements.errorDialog.open && elements.errorDialog.dataset.kind === kind) {
        elements.errorDialog.close();
      }
      return;
    }
    const statusText = kind === "cleanup" ? "Cleanup unavailable" : trigger.textContent.trim();
    if (kind === "cleanup") trigger.textContent = statusText;
    trigger.setAttribute("aria-label", `${statusText}. View ${kind} error details`);
  }

  function setCleanupError(error) {
    setError("cleanup", error);
  }

  function setPublicationError(error) {
    setError("publication", error);
  }

  function openErrorDetails(kind) {
    const error = errors[kind];
    if (!error) return;
    elements.errorDialog.dataset.kind = kind;
    elements.errorLedger.textContent = "";
    errorFields(error).forEach(([label, value]) => {
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = label;
      description.textContent = value;
      elements.errorLedger.append(term, description);
    });
    elements.copyError.textContent = "Copy details";
    elements.errorDialog.showModal();
  }

  async function copyError() {
    const error = errors[elements.errorDialog.dataset.kind];
    if (!error) return;
    const text = errorFields(error).map(([label, value]) => `${label}: ${value}`).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      elements.copyError.textContent = "Copied";
    } catch (_error) {
      elements.copyError.textContent = "Copy unavailable";
    }
    window.setTimeout(() => { elements.copyError.textContent = "Copy details"; }, 1_500);
  }

  function showCopyFeedback(buttonLabel, announcement) {
    window.clearTimeout(copyFeedbackTimer);
    elements.copyOutgoing.textContent = buttonLabel;
    elements.copyOutgoingState.textContent = announcement;
    copyFeedbackTimer = window.setTimeout(() => {
      elements.copyOutgoing.textContent = "Copy";
      elements.copyOutgoingState.textContent = "";
      copyFeedbackTimer = null;
    }, 1_500);
  }

  async function copyOutgoing() {
    if (!selectedOutgoingState().outgoing_text) return;
    if (evidenceLease && evidenceReceipt?.originalText !== elements.original.value) {
      await requestEvidenceJudgment(
        elements.original.value,
        effectiveCorrectionMode() === "smart" ? elements.smartTaskContext.value : "",
        false,
        effectiveCorrectionMode(),
        "copy",
      );
      return;
    }
    try {
      if (!evidenceLease && !blockedEvidenceLease) {
        await navigator.clipboard.writeText(selectedOutgoingState().outgoing_text);
        showCopyFeedback("Copied", "Outgoing copied.");
        return;
      }
      await publishNow();
      const response = await fetch("/api/outgoing-state");
      if (response.status === 409) {
        throw makeError({
          operation: "Outgoing copy",
          summary: "Outgoing copy is waiting for intended-meaning confirmation.",
          httpStatus: 409,
          code: "evidence_confirmation_required",
          message: "Complete intended-meaning confirmation in Sayloom, then retry.",
          retryAction: "Complete confirmation in Sayloom, then retry Copy.",
        });
      }
      if (!response.ok) throw await safeHttpError(response, "Outgoing copy");
      const outgoing = await readJson(response, "Outgoing copy");
      if (typeof outgoing?.outgoing_text !== "string") {
        throw makeError({
          operation: "Outgoing copy",
          summary: "Outgoing copy is waiting for intended-meaning confirmation.",
          code: "evidence_confirmation_required",
          message: "Complete intended-meaning confirmation in Sayloom, then retry.",
          retryAction: "Complete confirmation in Sayloom, then retry Copy.",
        });
      }
      await navigator.clipboard.writeText(outgoing.outgoing_text);
      showCopyFeedback("Copied", "Outgoing copied.");
    } catch (error) {
      showCopyFeedback(
        "Copy unavailable",
        error?.message || "Outgoing could not be copied.",
      );
    }
  }

  async function safeHttpError(response, operation) {
    let detail = null;
    try {
      const payload = await response.json();
      if (
        payload && typeof payload.detail === "object"
        && typeof payload.detail.code === "string"
        && typeof payload.detail.message === "string"
        && typeof payload.detail.retry_action === "string"
      ) detail = payload.detail;
    } catch (_error) {
      detail = null;
    }
    return makeError({
      operation,
      summary: `${operation} was rejected by the server.`,
      httpStatus: response.status,
      code: detail?.code || "server_rejection",
      message: detail?.message || "No additional safe detail is available.",
      retryAction: detail?.retry_action || "Retry the operation.",
    });
  }

  function networkError(operation) {
    return makeError({
      operation,
      summary: `${operation} could not reach the local service.`,
      code: "network_unavailable",
      message: "The browser could not connect to the local API.",
      retryAction: "Check the local service, then retry.",
    });
  }

  function malformedResponseError(operation, httpStatus) {
    return makeError({
      operation,
      summary: `${operation} returned an unreadable response.`,
      httpStatus,
      code: "malformed_response",
      message: "The response did not match the expected safe API contract.",
      retryAction: "Retry the operation. If it continues, restart through the controlled workflow.",
    });
  }

  async function readJson(response, operation) {
    try {
      return await response.json();
    } catch (_error) {
      throw malformedResponseError(operation, response.status);
    }
  }

  function schedulePublication() {
    renderCountsAndSelection();
    setPublicationError(null);
    setPublicationState("pending", "Publishing…");
    publicationSequence += 1;
    window.clearTimeout(publicationTimer);
    publicationTimer = window.setTimeout(publishNow, PUBLICATION_DEBOUNCE_MS);
  }

  function publishNow() {
    window.clearTimeout(publicationTimer);
    publicationTimer = null;
    renderCountsAndSelection();
    setPublicationError(null);
    const snapshot = selectedOutgoingState();
    const sequence = ++publicationSequence;
    publicationChain = publicationChain.then(async () => {
      try {
        const response = await fetch("/api/outgoing-state", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(snapshot),
        });
        if (!response.ok) {
          const error = await safeHttpError(response, "Outgoing publication");
          if (sequence === publicationSequence) {
            setPublicationState("error", "State unavailable");
            setPublicationError(error);
          }
          return;
        }
        const result = await readJson(response, "Outgoing publication");
        if (!result || typeof result.revision !== "number") {
          if (sequence === publicationSequence) {
            setPublicationState("error", "State unavailable");
            setPublicationError(malformedResponseError("Outgoing publication", response.status));
          }
          return;
        }
        if (sequence === publicationSequence) {
          setPublicationError(null);
          setPublicationState("ready", "State published");
        }
      } catch (error) {
        if (sequence === publicationSequence) {
          setPublicationState("error", "State unavailable");
          setPublicationError(error?.code ? error : networkError("Outgoing publication"));
        }
      }
    });
    return publicationChain;
  }

  function clearPublishedState() {
    setPublicationError(null);
    const sequence = ++publicationSequence;
    publicationChain = publicationChain.then(async () => {
      try {
        const response = await fetch("/api/outgoing-state", { method: "DELETE" });
        if (!response.ok) {
          const error = await safeHttpError(response, "Outgoing clear");
          if (sequence === publicationSequence) {
            setPublicationState("error", "Clear not published");
            setPublicationError(error);
          }
          return;
        }
        const result = await readJson(response, "Outgoing clear");
        if (!result || typeof result.revision !== "number") {
          if (sequence === publicationSequence) {
            setPublicationState("error", "Clear not published");
            setPublicationError(malformedResponseError("Outgoing clear", response.status));
          }
          return;
        }
        if (sequence === publicationSequence) {
          setPublicationError(null);
          setPublicationState("ready", "State cleared");
        }
      } catch (error) {
        if (sequence === publicationSequence) {
          setPublicationState("error", "Clear not published");
          setPublicationError(error?.code ? error : networkError("Outgoing clear"));
        }
      }
    });
    return publicationChain;
  }

  function abortActiveRequest() {
    if (!activeRequest) return false;
    activeRequest.abort();
    activeRequest = null;
    requestSequence += 1;
    return true;
  }

  function restoreOriginalSelection(selection) {
    if (!selection.wasFocused) return;
    elements.original.focus({ preventScroll: true });
    const end = Math.min(selection.end, elements.original.value.length);
    elements.original.setSelectionRange(Math.min(selection.start, end), end);
  }

  async function runCleanup(requestedCorrectionMode = null, bypassEvidence = false) {
    window.clearTimeout(cleanupTimer);
    cleanupTimer = null;
    abortActiveRequest();
    setCleanupError(null);
    invalidateSmartRepairReview();
    invalidateEvaluationCapture();

    const originalText = elements.original.value;
    const explicitSmart = requestedCorrectionMode === "smart"
      && effectiveCorrectionMode() !== "smart";
    const correctionMode = explicitSmart ? "smart" : effectiveCorrectionMode();
    const taskContext = correctionMode === "smart" ? elements.smartTaskContext.value : "";
    if (explicitSmart) setExplicitSmartState("running");
    if (!originalText.trim()) {
      elements.prepared.value = originalText;
      setStatus("unchanged");
      setExplicitSmartState("hidden");
      schedulePublication();
      return;
    }
    if (!elements.cleanupEnabled.checked) {
      elements.prepared.value = originalText;
      setStatus("disabled");
      if (explicitSmart) setExplicitSmartState("retry", "Smart correction needs cleanup enabled.");
      schedulePublication();
      return;
    }
    if (
      evidenceLease
      && !bypassEvidence
      && evidenceReceipt?.originalText !== originalText
    ) {
      if (explicitSmart) setExplicitSmartState("waiting", "Waiting for Intended wording.");
      await requestEvidenceJudgment(
        originalText,
        taskContext,
        explicitSmart,
        correctionMode,
      );
      return;
    }

    const sequence = ++requestSequence;
    const controller = new AbortController();
    const selection = {
      wasFocused: document.activeElement === elements.original,
      start: elements.original.selectionStart,
      end: elements.original.selectionEnd,
    };
    activeRequest = controller;
    setStatus("cleaning");
    schedulePublication();

    try {
      const response = await fetch("/api/cleanup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          original_text: originalText,
          enabled: true,
          correction_mode: correctionMode,
          ...(taskContext.trim() ? { task_context: taskContext } : {}),
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const error = await safeHttpError(response, "Cleanup");
        if (
          sequence !== requestSequence
          || originalText !== elements.original.value
          || taskContext !== (correctionMode === "smart" ? elements.smartTaskContext.value : "")
        ) return;
        elements.prepared.value = originalText;
        setStatus("error");
        setCleanupError(error);
        if (explicitSmart) setExplicitSmartState("retry", "Smart correction failed.");
        restoreOriginalSelection(selection);
        return;
      }
      const result = await readJson(response, "Cleanup");
      if (
        sequence !== requestSequence
        || originalText !== elements.original.value
        || taskContext !== (correctionMode === "smart" ? elements.smartTaskContext.value : "")
      ) return;
      if (
        !result || typeof result.prepared_text !== "string"
        || !["prepared", "unchanged", "empty_input", "disabled", "timeout", "provider_error"].includes(result.status)
        || (correctionMode === "smart" && !validateSmartRepairs(
          result.lexical_repairs, originalText, result.prepared_text,
        ))
      ) {
        elements.prepared.value = originalText;
        setStatus("error");
        setCleanupError(malformedResponseError("Cleanup", response.status));
        if (explicitSmart) setExplicitSmartState("retry", "Smart correction failed.");
        restoreOriginalSelection(selection);
        return;
      }

      elements.prepared.value = result.prepared_text;
      const statusMap = {
        prepared: "prepared",
        unchanged: "unchanged",
        empty_input: "unchanged",
        disabled: "disabled",
        timeout: "timeout",
        provider_error: "error",
      };
      setStatus(statusMap[result.status]);
      if (
        correctionMode === "smart"
        && ["prepared", "unchanged"].includes(result.status)
      ) showSmartRepairResult(result.lexical_repairs);
      if (explicitSmart && ["prepared", "unchanged"].includes(result.status)) {
        setExplicitSmartState(
          "success",
          result.status === "prepared" ? "Smart correction applied." : "Smart correction unchanged.",
        );
      } else if (correctionMode === "conservative" && ["prepared", "unchanged"].includes(result.status)) {
        setExplicitSmartState("available");
      } else if (explicitSmart) {
        setExplicitSmartState("retry", "Smart correction failed.");
      }
      if (result.status === "timeout" || result.status === "provider_error") {
        const safe = result.error;
        setCleanupError(makeError({
          operation: "Cleanup",
          summary: result.status === "timeout"
            ? "Cleanup timed out; Outgoing is using Original."
            : "Cleanup failed; Outgoing is using Original.",
          model: typeof result.model === "string" ? result.model : null,
          httpStatus: Number.isInteger(safe?.http_status) ? safe.http_status : null,
          code: typeof safe?.code === "string" ? safe.code : "cleanup_unavailable",
          message: typeof safe?.message === "string"
            ? safe.message
            : "No additional safe detail is available.",
          retryAction: typeof safe?.retry_action === "string"
            ? safe.retry_action
            : "Retry cleanup or continue with Original.",
        }));
      } else {
        setCleanupError(null);
      }
      if (
        evaluationAvailable
        && !evidenceLease
        && ["prepared", "unchanged"].includes(result.status)
        && result.evaluation
        && typeof result.evaluation.capture_proof === "string"
        && Array.isArray(result.attempts)
      ) {
        currentEvaluation = {
          sourceText: originalText,
          providerOutput: result.prepared_text,
          provider: result.provider,
          model: result.model,
          attempts: result.attempts.map((attempt) => {
            const safeAttempt = { ...attempt };
            delete safeAttempt.quota_group_id;
            return safeAttempt;
          }),
          context: result.evaluation,
        };
        elements.saveEvaluationCase.disabled = false;
      }
      restoreOriginalSelection(selection);
    } catch (error) {
      if (sequence !== requestSequence) return;
      elements.prepared.value = originalText;
      setStatus("error");
      if (error.name !== "AbortError") {
        setCleanupError(error?.code ? error : networkError("Cleanup"));
        if (explicitSmart) setExplicitSmartState("retry", "Smart correction failed.");
      }
      restoreOriginalSelection(selection);
    } finally {
      if (sequence === requestSequence) {
        activeRequest = null;
        schedulePublication();
      }
    }
  }

  function scheduleCleanup() {
    window.clearTimeout(cleanupTimer);
    setExplicitSmartState("hidden");
    setCleanupError(null);
    invalidateSmartRepairReview();
    invalidateEvaluationCapture();
    if (evidenceLease && evidenceReceipt?.originalText !== elements.original.value) {
      abortActiveRequest();
      setStatus("waiting");
      schedulePublication();
      return;
    }
    if (!elements.cleanupEnabled.checked) {
      elements.prepared.value = elements.original.value;
      setStatus("disabled");
      schedulePublication();
      return;
    }
    abortActiveRequest();
    setStatus("waiting");
    schedulePublication();
    cleanupTimer = window.setTimeout(runCleanup, CLEANUP_DEBOUNCE_MS);
  }

  function originalIsFullySelected() {
    return elements.original.value.length > 0
      && elements.original.selectionStart === 0
      && elements.original.selectionEnd === elements.original.value.length;
  }

  function handleOriginalInput(event) {
    cancelEvidenceJudgment();
    const startsNewOriginal = replaceAllPending
      || (!currentOriginalText && Boolean(elements.original.value));
    if (startsNewOriginal) {
      elements.cleanupEnabled.checked = defaultPreparationMode !== "off";
      draftCorrectionMode = defaultPreparationMode === "smart" ? "smart" : "conservative";
      elements.prepared.value = "";
      elements.smartTaskContext.value = "";
    } else if (!elements.original.value) {
      draftCorrectionMode = null;
    }
    replaceAllPending = false;
    currentOriginalText = elements.original.value;
    setExplicitSmartState("hidden");
    renderCorrectionMode();
    const followsSyntheticPaste = syntheticPastePending && event.isTrusted;
    if (followsSyntheticPaste) {
      window.clearTimeout(syntheticPasteTimer);
      syntheticPastePending = false;
      const caret = elements.original.selectionEnd;
      window.requestAnimationFrame(() => {
        elements.original.focus({ preventScroll: true });
        elements.original.setSelectionRange(caret, caret);
      });
    }
    scheduleCleanup();
  }

  // Compatibility path for dictation tools that precede trusted input with a synthetic paste.
  elements.original.addEventListener("beforeinput", () => {
    replaceAllPending = originalIsFullySelected();
  });
  elements.original.addEventListener("paste", (event) => {
    replaceAllPending = originalIsFullySelected();
    if (!event.isTrusted) {
      syntheticPastePending = true;
      window.clearTimeout(syntheticPasteTimer);
      syntheticPasteTimer = window.setTimeout(() => {
        syntheticPastePending = false;
      }, 1_000);
    }
  });
  elements.original.addEventListener("input", handleOriginalInput);

  elements.cleanupEnabled.addEventListener("change", () => {
    invalidateSmartRepairReview();
    invalidateEvaluationCapture();
    if (!elements.cleanupEnabled.checked) {
      window.clearTimeout(cleanupTimer);
      abortActiveRequest();
      setCleanupError(null);
      elements.prepared.value = elements.original.value;
      setStatus("disabled");
      publishNow();
    } else {
      scheduleCleanup();
    }
  });

  elements.defaultPreparationMode.addEventListener("change", async () => {
    const previousMode = defaultPreparationMode;
    const nextMode = elements.defaultPreparationMode.value;
    elements.defaultPreparationMode.disabled = true;
    elements.modeSaveState.textContent = "Saving preparation default…";
    try {
      const response = await fetch("/api/preferences/preparation-default", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preparation_default: nextMode }),
      });
      if (!response.ok) throw await safeHttpError(response, "Preparation default");
      const result = await readJson(response, "Preparation default");
      if (!result || result.preparation_default !== nextMode) {
        throw malformedResponseError("Preparation default", response.status);
      }
      defaultPreparationMode = nextMode;
      elements.modeSaveState.textContent = `${titleCaseState(nextMode)} saved for the next Original.`;
      renderCorrectionMode();
    } catch (error) {
      defaultPreparationMode = previousMode;
      elements.modeSaveState.textContent = `${error.message} ${error.retryAction}`;
      renderCorrectionMode();
    } finally {
      elements.defaultPreparationMode.disabled = false;
    }
  });

  elements.smartTaskContext.addEventListener("input", () => {
    if (effectiveCorrectionMode() === "smart" && elements.original.value) scheduleCleanup();
  });

  elements.layoutStacked.addEventListener("click", () => setLayoutPreference("stacked"));
  elements.layoutSideBySide.addEventListener("click", () => {
    if (!narrowWorkspace.matches) setLayoutPreference("side-by-side");
  });
  elements.maximizeOriginal.addEventListener("click", () => toggleMaximizedPane("original"));
  elements.maximizePrepared.addEventListener("click", () => toggleMaximizedPane("prepared"));
  elements.toggleSidebar.addEventListener("click", () => {
    sidebarCollapsed = !sidebarCollapsed;
    renderSidebar();
    saveWorkspacePreferences();
  });
  elements.runCleanup.addEventListener("click", () => runCleanup());
  elements.retryCleanup.addEventListener("click", () => runCleanup());
  elements.runSmartCorrection.addEventListener("click", () => runCleanup("smart"));
  elements.selectOriginal.addEventListener("click", () => {
    originalOutgoingOverride = true;
    publishNow();
  });
  elements.selectPrepared.addEventListener("click", () => {
    if (!preparedIsCurrent()) return;
    originalOutgoingOverride = false;
    publishNow();
  });
  elements.copyOutgoing.addEventListener("click", copyOutgoing);
  elements.clear.addEventListener("click", () => {
    window.clearTimeout(cleanupTimer);
    window.clearTimeout(publicationTimer);
    abortActiveRequest();
    replaceAllPending = false;
    cancelEvidenceJudgment();
    originalOutgoingOverride = false;
    draftCorrectionMode = null;
    currentOriginalText = "";
    setExplicitSmartState("hidden");
    invalidateSmartRepairReview();
    invalidateEvaluationCapture();
    elements.original.value = "";
    elements.prepared.value = "";
    elements.prepared.dataset.repairCount = "0";
    elements.smartTaskContext.value = "";
    setCleanupError(null);
    setStatus("unchanged");
    renderCorrectionMode();
    renderCountsAndSelection();
    clearPublishedState();
    elements.original.focus();
  });

  elements.cleanupStatus.addEventListener("click", () => openErrorDetails("cleanup"));
  elements.publication.addEventListener("click", () => openErrorDetails("publication"));
  elements.closeErrorDialog.addEventListener("click", () => elements.errorDialog.close());
  elements.errorDialog.addEventListener("click", (event) => {
    if (event.target === elements.errorDialog) elements.errorDialog.close();
  });
  elements.errorDialog.addEventListener("close", () => {
    elements.errorDialog.dataset.kind = "";
  });
  elements.copyError.addEventListener("click", copyError);

  function renderEvidenceCollection() {
    const armed = Boolean(evidenceLease);
    elements.evidenceCollectionControl.classList.toggle("is-armed", armed);
    elements.evidenceCollectionToggle.disabled = !evidenceReady;
    elements.evidenceCollectionToggle.textContent = armed
      ? "Stop Evidence Collection"
      : evidenceReady ? "Arm Evidence Collection" : "Evidence Collection unavailable";
    elements.evidenceCollectionState.textContent = armed
      ? "Armed · Voiceitt source attested for this session"
      : evidenceReady ? "Approved package ready · attestation required" : "Package not ready";
    elements.withdrawEvidence.hidden = !(
      armed && evidenceReceipt?.artifactType === "eligible_observation"
    );
  }

  function closeEvidenceAttestation() {
    if (elements.evidenceAttestationDialog.open) elements.evidenceAttestationDialog.close();
    elements.evidenceSourceAttestation.checked = false;
    elements.evidenceAttestationStatus.textContent = "";
  }

  function closeEvidenceJudgment() {
    const explicitSmart = frozenEvidence?.explicitSmart === true;
    frozenEvidence = null;
    elements.evidenceJudgmentStatus.textContent = "";
    elements.evidenceJudgmentTitle.textContent = "Confirm Intended wording";
    elements.evidenceIntendedText.value = "";
    elements.evidenceIntendedField.hidden = false;
    if (elements.evidenceJudgmentDialog.open) elements.evidenceJudgmentDialog.close();
    if (explicitSmart) setExplicitSmartState("available");
  }

  async function cancelEvidenceJudgment() {
    const leaseToken = evidenceLease;
    closeEvidenceJudgment();
    evidenceReceipt = null;
    renderEvidenceCollection();
    schedulePublication();
    if (!leaseToken) return;
    evidenceCancellation = evidenceCancellation.then(async () => {
      try {
        await fetch("/api/evidence-collection/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lease_token: leaseToken }),
        });
      } catch (_error) { /* The stale receipt remains blocked by the published lease token. */ }
    });
    await evidenceCancellation;
  }

  function showEvidenceFailure(error, recovery) {
    blockedEvidenceLease = evidenceLease || blockedEvidenceLease;
    evidenceLease = null;
    evidenceReceipt = null;
    window.clearTimeout(evidenceLeaseTimer);
    closeEvidenceJudgment();
    evidenceRecovery = recovery;
    elements.evidenceFailureMessage.textContent = `${error.message} ${error.retryAction}`;
    if (!elements.evidenceFailureDialog.open) elements.evidenceFailureDialog.showModal();
    setStatus("error");
    setCleanupError(error);
    renderEvidenceCollection();
    publishNow();
  }

  function startEvidenceLeaseTimer(expiresAt) {
    window.clearTimeout(evidenceLeaseTimer);
    const expiry = Date.parse(expiresAt);
    if (!Number.isFinite(expiry)) return;
    const delay = Math.max(0, expiry - Date.now());
    evidenceLeaseTimer = window.setTimeout(() => {
      if (!evidenceLease) return;
      showEvidenceFailure(makeError({
        operation: "Evidence Collection",
        summary: "The collection lease expired.",
        code: "evidence_lease_expired",
        message: "The Evidence Collection session expired.",
        retryAction: "Retry collection, use ordinary uncollected preparation, or cancel.",
      }), null);
    }, delay);
    evidenceLeaseTimer?.unref?.();
  }

  async function requestEvidenceJudgment(
    originalText,
    taskContext,
    explicitSmart = false,
    correctionMode = "smart",
  ) {
    if (!originalText.trim()) return;
    const recovery = { originalText, taskContext, explicitSmart, correctionMode };
    elements.prepared.value = "";
    originalOutgoingOverride = true;
    invalidateSmartRepairReview();
    invalidateEvaluationCapture();
    setCleanupError(null);
    setStatus("waiting");
    schedulePublication();
    try {
      await evidenceCancellation;
      const response = await fetch("/api/evidence-collection/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lease_token: evidenceLease,
          original_text: originalText,
          task_context: taskContext || null,
          correction_mode: correctionMode,
        }),
      });
      if (!response.ok) throw await safeHttpError(response, "Evidence trigger");
      const result = await readJson(response, "Evidence trigger");
      if (typeof result?.observation_id !== "string") {
        throw malformedResponseError("Evidence trigger", response.status);
      }
      if (
        originalText !== elements.original.value
        || taskContext !== (correctionMode === "smart" ? elements.smartTaskContext.value : "")
      ) return;
      frozenEvidence = {
        observationId: result.observation_id,
        originalText,
        taskContext,
        explicitSmart,
        correctionMode,
      };
      elements.evidenceIntendedText.value = originalText;
      elements.evidenceIntendedText.readOnly = true;
      elements.evidenceIntendedText.required = true;
      elements.evidenceIntendedField.hidden = false;
      elements.evidenceDisposition.value = "";
      elements.evidenceJudgmentDialog.showModal();
    } catch (error) {
      const safe = error?.code ? error : networkError("Evidence trigger");
      if (explicitSmart) setExplicitSmartState("retry", "Smart correction failed.");
      showEvidenceFailure(safe, recovery);
    }
  }

  async function stopEvidenceLease(leaseToken) {
    const response = await fetch(
      `/api/evidence-collection/arm?lease_token=${encodeURIComponent(leaseToken)}`,
      { method: "DELETE" },
    );
    if (!response.ok) throw await safeHttpError(response, "Evidence stop");
  }

  elements.evidenceCollectionToggle.addEventListener("click", async () => {
    if (!evidenceLease) {
      elements.evidenceAttestationDialog.showModal();
      return;
    }
    try {
      await stopEvidenceLease(evidenceLease);
    } catch (error) {
      showEvidenceFailure(error?.code ? error : networkError("Evidence stop"), null);
      return;
    }
    window.clearTimeout(evidenceLeaseTimer);
    evidenceLease = null;
    blockedEvidenceLease = null;
    evidenceReceipt = null;
    storeEvidenceLease(null);
    closeEvidenceJudgment();
    renderEvidenceCollection();
    schedulePublication();
  });
  elements.cancelEvidenceAttestation.addEventListener("click", closeEvidenceAttestation);
  elements.cancelEvidenceAttestationSecondary.addEventListener("click", closeEvidenceAttestation);
  elements.evidenceAttestationForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!elements.evidenceAttestationForm.reportValidity()) return;
    elements.evidenceAttestationStatus.textContent = "Arming…";
    try {
      const response = await fetch("/api/evidence-collection/arm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          browser_session_id: browserSessionId,
          source_attestation_confirmed: true,
        }),
      });
      if (!response.ok) throw await safeHttpError(response, "Evidence arming");
      const result = await readJson(response, "Evidence arming");
      if (typeof result?.lease_token !== "string") {
        throw malformedResponseError("Evidence arming", response.status);
      }
      evidenceLease = result.lease_token;
      storeEvidenceLease(evidenceLease);
      blockedEvidenceLease = null;
      evidenceReceipt = null;
      startEvidenceLeaseTimer(result.expires_at);
      elements.prepared.value = "";
      originalOutgoingOverride = true;
      invalidateSmartRepairReview();
      if (elements.original.value) setStatus("waiting");
      closeEvidenceAttestation();
      invalidateEvaluationCapture();
      renderEvidenceCollection();
      schedulePublication();
      const retry = evidenceRecovery;
      evidenceRecovery = null;
      if (retry && retry.originalText === elements.original.value) {
        await requestEvidenceJudgment(
          retry.originalText,
          retry.taskContext,
          retry.explicitSmart,
          retry.correctionMode,
        );
      }
    } catch (error) {
      const safe = error?.code ? error : networkError("Evidence arming");
      elements.evidenceAttestationStatus.textContent = `${safe.message} ${safe.retryAction}`;
    }
  });
  elements.cancelEvidenceJudgment.addEventListener("click", cancelEvidenceJudgment);
  elements.cancelEvidenceJudgmentSecondary.addEventListener("click", cancelEvidenceJudgment);
  elements.evidenceJudgmentDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    cancelEvidenceJudgment();
  });
  elements.evidenceJudgmentForm.addEventListener("change", (event) => {
    if (event.target.name !== "evidence-disposition" || !frozenEvidence) return;
    const editable = event.target.value === "edit_intended";
    const excluded = isEvidenceExclusion(event.target.value);
    elements.evidenceJudgmentTitle.textContent = excluded
      ? "Confirm exclusion"
      : "Confirm Intended wording";
    elements.evidenceIntendedField.hidden = excluded;
    elements.evidenceIntendedText.required = !excluded;
    elements.evidenceIntendedText.readOnly = !editable;
    elements.evidenceIntendedText.value = frozenEvidence.originalText;
    if (editable) {
      elements.evidenceIntendedText.focus();
      elements.evidenceIntendedText.select();
    }
  });
  elements.evidenceJudgmentForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!frozenEvidence || !elements.evidenceJudgmentForm.reportValidity()) return;
    const disposition = elements.evidenceDisposition.value;
    if (!disposition) return;
    const snapshot = frozenEvidence;
    const excluded = isEvidenceExclusion(disposition);
    const intendedText = excluded
      ? null
      : disposition === "edit_intended" ? elements.evidenceIntendedText.value : snapshot.originalText;
    elements.evidenceJudgmentStatus.textContent = "Writing and verifying observation…";
    try {
      const response = await fetch("/api/evidence-collection/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lease_token: evidenceLease,
          observation_id: snapshot.observationId,
          disposition,
          intended_text: intendedText,
        }),
      });
      if (!response.ok) throw await safeHttpError(response, "Evidence confirmation");
      const result = await readJson(response, "Evidence confirmation");
      if (
        elements.original.value !== snapshot.originalText
        || (snapshot.correctionMode === "smart" ? elements.smartTaskContext.value : "")
          !== snapshot.taskContext
      ) return;
      const successful = ["prepared", "unchanged"].includes(result?.status);
      const failed = ["timeout", "provider_error"].includes(result?.status);
      if (
        typeof result?.prepared_text !== "string"
        || typeof result?.evidence_receipt !== "string"
        || result?.observation_id !== snapshot.observationId
        || !["eligible_observation", "exclusion"].includes(result?.artifact_type)
        || !Array.isArray(result?.exact_repeat_suggestions)
        || (!successful && !failed)
        || (snapshot.correctionMode === "smart" && successful && !validateSmartRepairs(
          result.lexical_repairs, snapshot.originalText, result.prepared_text,
        ))
      ) throw malformedResponseError("Evidence confirmation", response.status);
      evidenceReceipt = {
        token: result.evidence_receipt,
        observationId: result.observation_id,
        originalText: snapshot.originalText,
        artifactType: result.artifact_type,
      };
      closeEvidenceJudgment();
      renderEvidenceCollection();
      originalOutgoingOverride = false;
      if (failed) {
        elements.prepared.value = snapshot.originalText;
        setStatus(result.status === "timeout" ? "timeout" : "error");
        const safe = result.error;
        const correctionLabel = snapshot.correctionMode === "smart"
          ? "Smart correction"
          : "Conservative preparation";
        setCleanupError(makeError({
          operation: correctionLabel,
          summary: result.status === "timeout"
            ? `${correctionLabel} timed out after the observation was saved; Outgoing is using Original.`
            : `${correctionLabel} failed after the observation was saved; Outgoing is using Original.`,
          model: typeof result.model === "string" ? result.model : null,
          httpStatus: Number.isInteger(safe?.http_status) ? safe.http_status : null,
          code: typeof safe?.code === "string" ? safe.code : "cleanup_unavailable",
          message: typeof safe?.message === "string"
            ? safe.message
            : "No additional safe detail is available.",
          retryAction: typeof safe?.retry_action === "string"
            ? safe.retry_action
            : "Retry Smart correction or continue with Original.",
        }));
        if (snapshot.explicitSmart) setExplicitSmartState("retry", "Smart correction failed.");
        else if (snapshot.correctionMode === "conservative") setExplicitSmartState("available");
        await publishNow();
        return;
      }
      elements.prepared.value = result.prepared_text;
      setStatus(result.status);
      setCleanupError(null);
      if (snapshot.correctionMode === "smart") {
        showSmartRepairResult(result.lexical_repairs);
      } else {
        invalidateSmartRepairReview();
      }
      if (result.exact_repeat_suggestions.length) {
        elements.evidenceCollectionState.textContent =
          `Armed · ${result.exact_repeat_suggestions.length} provisional exact repeat suggestion`;
      }
      if (snapshot.explicitSmart) {
        setExplicitSmartState(
          "success",
          result.status === "prepared" ? "Smart correction applied." : "Smart correction unchanged.",
        );
      } else if (snapshot.correctionMode === "conservative") {
        setExplicitSmartState("available");
      }
      await publishNow();
    } catch (error) {
      const safe = error?.code ? error : networkError("Evidence confirmation");
      if (snapshot.explicitSmart) setExplicitSmartState("retry", "Smart correction failed.");
      showEvidenceFailure(safe, snapshot);
    }
  });

  elements.retryEvidenceCollection.addEventListener("click", () => {
    elements.evidenceFailureDialog.close();
    elements.evidenceAttestationDialog.showModal();
  });
  elements.continueWithoutEvidence.addEventListener("click", async () => {
    const recovery = evidenceRecovery;
    const leaseToken = blockedEvidenceLease;
    if (leaseToken) {
      try {
        await stopEvidenceLease(leaseToken);
      } catch (error) {
        elements.evidenceFailureMessage.textContent = `${
          error?.message || "Evidence Collection could not be stopped."
        } Retry collection, use ordinary uncollected preparation, or cancel.`;
        return;
      }
    }
    evidenceRecovery = null;
    blockedEvidenceLease = null;
    storeEvidenceLease(null);
    elements.evidenceFailureDialog.close();
    renderEvidenceCollection();
    schedulePublication();
    if (recovery) {
      runCleanup(recovery.explicitSmart ? "smart" : null, true);
    }
  });
  elements.cancelEvidenceRecovery.addEventListener("click", () => {
    evidenceRecovery = null;
    elements.evidenceFailureDialog.close();
  });
  elements.withdrawEvidence.addEventListener("click", async () => {
    if (!evidenceLease || evidenceReceipt?.artifactType !== "eligible_observation") return;
    try {
      const response = await fetch(
        `/api/evidence-collection/observations/${evidenceReceipt.observationId}`,
        { method: "DELETE" },
      );
      if (!response.ok) throw await safeHttpError(response, "Evidence withdrawal");
      evidenceReceipt = null;
      elements.prepared.value = "";
      originalOutgoingOverride = true;
      setStatus("waiting");
      renderEvidenceCollection();
      schedulePublication();
    } catch (error) {
      showEvidenceFailure(
        error?.code ? error : networkError("Evidence withdrawal"),
        null,
      );
    }
  });

  elements.workspaceResizer.addEventListener("pointerdown", (event) => {
    activeResizePointer = event.pointerId;
    elements.workspaceResizer.setPointerCapture(event.pointerId);
    elements.workspaceResizer.classList.add("is-resizing");
    resizeFromPointer(event);
  });
  elements.workspaceResizer.addEventListener("pointermove", (event) => {
    if (event.pointerId === activeResizePointer) resizeFromPointer(event);
  });
  function finishResize(event) {
    if (event.pointerId !== activeResizePointer) return;
    activeResizePointer = null;
    elements.workspaceResizer.classList.remove("is-resizing");
    saveWorkspacePreferences();
  }
  elements.workspaceResizer.addEventListener("pointerup", finishResize);
  elements.workspaceResizer.addEventListener("pointercancel", finishResize);
  elements.workspaceResizer.addEventListener("dblclick", () => {
    setWorkspaceShare(
      effectiveLayout() === "side-by-side" ? DEFAULT_SIDE_BY_SIDE_SHARE : DEFAULT_STACKED_SHARE,
      true,
    );
  });
  elements.workspaceResizer.addEventListener("keydown", (event) => {
    const currentShare = Number(elements.workspaceResizer.getAttribute("aria-valuenow"));
    const sideBySide = effectiveLayout() === "side-by-side";
    const nextShare = {
      ArrowUp: sideBySide ? undefined : currentShare - 2,
      ArrowDown: sideBySide ? undefined : currentShare + 2,
      ArrowLeft: sideBySide ? currentShare - 2 : undefined,
      ArrowRight: sideBySide ? currentShare + 2 : undefined,
      Home: MINIMUM_ORIGINAL_SHARE,
      End: MAXIMUM_ORIGINAL_SHARE,
    }[event.key];
    if (nextShare === undefined) return;
    event.preventDefault();
    setWorkspaceShare(nextShare, true);
  });

  narrowWorkspace.addEventListener("change", renderWorkspaceLayout);

  async function evaluationRequest(operation, url, options = {}) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (_error) {
      throw networkError(operation);
    }
    if (!response.ok) throw await safeHttpError(response, operation);
    return readJson(response, operation);
  }

  function fillDefinitionList(list, fields) {
    list.textContent = "";
    fields.forEach(([label, value]) => {
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = label;
      description.textContent = value;
      list.append(term, description);
    });
  }

  function clearEvaluationCaptureDialog() {
    elements.evaluationSourceCategory.value = "";
    elements.evaluationSourceText.value = "";
    elements.evaluationProviderOutput.value = "";
    elements.evaluationExpectedCleanup.value = "";
    elements.evaluationProviderContext.textContent = "";
    elements.evaluationPromptContext.textContent = "";
    elements.evaluationCaptureStatus.textContent = "";
  }

  function closeEvaluationCapture() {
    if (elements.evaluationCaptureDialog.open) elements.evaluationCaptureDialog.close();
    clearEvaluationCaptureDialog();
  }

  function openEvaluationCapture() {
    if (
      !currentEvaluation
      || currentEvaluation.sourceText !== elements.original.value
      || currentEvaluation.providerOutput !== elements.prepared.value
    ) {
      invalidateEvaluationCapture();
      return;
    }
    elements.evaluationSourceText.value = currentEvaluation.sourceText;
    elements.evaluationProviderOutput.value = currentEvaluation.providerOutput;
    elements.evaluationExpectedCleanup.value = currentEvaluation.providerOutput;
    elements.evaluationProviderContext.textContent = `${currentEvaluation.provider} · ${currentEvaluation.model}`;
    elements.evaluationPromptContext.textContent = `Prompt ${currentEvaluation.context.prompt_version_id} · ${currentEvaluation.context.prompt_content_sha256}`;
    elements.evaluationCaptureDialog.showModal();
    elements.evaluationSourceCategory.focus();
  }

  elements.saveEvaluationCase.addEventListener("click", openEvaluationCapture);
  elements.cancelEvaluationCapture.addEventListener("click", closeEvaluationCapture);
  elements.cancelEvaluationCaptureSecondary.addEventListener("click", closeEvaluationCapture);
  elements.evaluationCaptureDialog.addEventListener("close", clearEvaluationCaptureDialog);
  elements.evaluationCaptureForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!currentEvaluation || !elements.evaluationCaptureForm.reportValidity()) return;
    elements.evaluationCaptureStatus.textContent = "Saving confirmed case…";
    const context = currentEvaluation.context;
    const payload = {
      contract_version: "cleanup-evaluation-corpus-v1",
      capture_proof: context.capture_proof,
      consent: {
        version: "cleanup-evaluation-consent-v1",
        scope: "polished-cleanup-evaluation-only",
        confirmed: true,
      },
      source_category: elements.evaluationSourceCategory.value,
      source_text: currentEvaluation.sourceText,
      provider_output: currentEvaluation.providerOutput,
      expected_cleanup: elements.evaluationExpectedCleanup.value,
      cleanup: {
        completed_at: context.completed_at,
        provider: currentEvaluation.provider,
        model: currentEvaluation.model,
        attempts: currentEvaluation.attempts,
        prompt_version_id: context.prompt_version_id,
        prompt_content_sha256: context.prompt_content_sha256,
        prompt_text: context.prompt_text,
        cleanup_schema_version: context.cleanup_schema_version,
      },
    };
    try {
      const saved = await evaluationRequest("Evaluation save", "/api/evaluation/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      invalidateEvaluationCapture();
      closeEvaluationCapture();
      elements.evaluationStatus.textContent = `Saved case ${saved.case_id}. Expires ${new Date(saved.expires_at).toLocaleString()}.`;
      evaluationCases = [];
    } catch (error) {
      elements.evaluationCaptureStatus.textContent = `${error.message} ${error.retryAction}`;
    }
  });

  function selectedEvaluationCases() {
    return [...elements.evaluationCaseList.querySelectorAll("input[type=checkbox]:checked")]
      .map((checkbox) => evaluationCases.find((item) => item.case_id === checkbox.value))
      .filter(Boolean)
      .map((item) => ({ case_id: item.case_id, revision: item.revision }));
  }

  function renderEvaluationCases() {
    elements.evaluationCaseList.textContent = "";
    if (evaluationCases.length === 0) {
      const empty = document.createElement("p");
      empty.className = "target-list-empty";
      empty.textContent = "No confirmed evaluation cases are available.";
      elements.evaluationCaseList.append(empty);
    }
    evaluationCases.forEach((item) => {
      const card = document.createElement("article");
      const checkbox = document.createElement("input");
      const review = document.createElement("button");
      const identity = document.createElement("strong");
      const context = document.createElement("span");
      const expiry = document.createElement("span");
      card.className = `evaluation-case-card${item.upcoming_expiry ? " is-upcoming" : ""}`;
      card.setAttribute("role", "listitem");
      checkbox.type = "checkbox";
      checkbox.value = item.case_id;
      checkbox.setAttribute("aria-label", `Select case ${item.case_id} for export`);
      checkbox.addEventListener("change", () => {
        elements.previewEvaluationExport.disabled = selectedEvaluationCases().length === 0;
      });
      review.type = "button";
      review.setAttribute("aria-label", `Review evaluation case ${item.case_id}`);
      identity.textContent = item.case_id;
      context.textContent = `${titleCaseState(item.source_category)} · ${item.provider} · ${item.model}`;
      expiry.textContent = item.hold
        ? `Held for ${item.hold.benchmark_id} until ${new Date(item.hold.release_at).toLocaleString()}`
        : `Expires ${new Date(item.expires_at).toLocaleString()}`;
      review.append(identity, context, expiry);
      review.addEventListener("click", () => reviewEvaluationCase(item.case_id));
      card.append(checkbox, review);
      elements.evaluationCaseList.append(card);
    });
    elements.previewEvaluationExport.disabled = true;
  }

  async function loadEvaluationCases() {
    if (!evaluationAvailable) {
      evaluationCases = [];
      renderEvaluationCases();
      elements.evaluationStatus.textContent = "Evaluation storage is not configured and current.";
      return;
    }
    elements.evaluationStatus.textContent = "Loading evaluation metadata…";
    try {
      const result = await evaluationRequest("Evaluation case loading", "/api/evaluation/cases");
      if (!result || !Array.isArray(result.cases)) {
        throw malformedResponseError("Evaluation case loading", 200);
      }
      evaluationCases = result.cases;
      renderEvaluationCases();
      elements.evaluationStatus.textContent = `${evaluationCases.length} confirmed case${evaluationCases.length === 1 ? "" : "s"}.`;
    } catch (error) {
      elements.evaluationStatus.textContent = `${error.message} ${error.retryAction}`;
    }
  }

  async function reviewEvaluationCase(caseId) {
    elements.evaluationReviewStatus.textContent = "Loading explicit review…";
    try {
      reviewedEvaluationCase = await evaluationRequest(
        "Evaluation case review",
        `/api/evaluation/cases/${caseId}`,
      );
      fillDefinitionList(elements.evaluationReviewMetadata, [
        ["Case ID", reviewedEvaluationCase.case_id],
        ["Purpose", reviewedEvaluationCase.purpose],
        ["Provider and model", `${reviewedEvaluationCase.provider} · ${reviewedEvaluationCase.model}`],
        ["Captured", new Date(reviewedEvaluationCase.captured_at).toLocaleString()],
        ["Expires", new Date(reviewedEvaluationCase.expires_at).toLocaleString()],
        ["Hold", reviewedEvaluationCase.hold
          ? `${reviewedEvaluationCase.hold.benchmark_id} until ${new Date(reviewedEvaluationCase.hold.release_at).toLocaleString()}`
          : "None"],
      ]);
      elements.evaluationReviewSource.value = reviewedEvaluationCase.source_text;
      elements.evaluationReviewProviderOutput.value = reviewedEvaluationCase.provider_output;
      elements.evaluationReviewExpected.value = reviewedEvaluationCase.expected_cleanup;
      elements.evaluationReviewStatus.textContent = "";
      elements.evaluationReviewDialog.showModal();
    } catch (error) {
      elements.evaluationStatus.textContent = `${error.message} ${error.retryAction}`;
    }
  }

  function closeEvaluationReview() {
    reviewedEvaluationCase = null;
    elements.evaluationReviewSource.value = "";
    elements.evaluationReviewProviderOutput.value = "";
    elements.evaluationReviewExpected.value = "";
    elements.evaluationReviewStatus.textContent = "";
    if (elements.evaluationReviewDialog.open) elements.evaluationReviewDialog.close();
  }

  elements.closeEvaluationReview.addEventListener("click", closeEvaluationReview);
  elements.evaluationReviewDialog.addEventListener("close", () => {
    reviewedEvaluationCase = null;
    elements.evaluationReviewSource.value = "";
    elements.evaluationReviewProviderOutput.value = "";
    elements.evaluationReviewExpected.value = "";
  });

  async function changeReviewedRetention(payload) {
    if (!reviewedEvaluationCase) return;
    elements.evaluationReviewStatus.textContent = "Updating retention…";
    try {
      const updated = await evaluationRequest(
        "Evaluation retention",
        `/api/evaluation/cases/${reviewedEvaluationCase.case_id}/retention`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ revision: reviewedEvaluationCase.revision, ...payload }),
        },
      );
      reviewedEvaluationCase.revision = updated.revision;
      reviewedEvaluationCase.expires_at = updated.expires_at;
      reviewedEvaluationCase.hold = updated.hold;
      elements.evaluationReviewStatus.textContent = "Retention updated.";
      evaluationCases = [];
    } catch (error) {
      elements.evaluationReviewStatus.textContent = `${error.message} ${error.retryAction}`;
    }
  }

  elements.evaluationExpiryForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!elements.evaluationExpiryForm.reportValidity()) return;
    changeReviewedRetention({ expires_at: `${elements.evaluationEarlierExpiry.value}:00Z` });
  });
  elements.evaluationHoldForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!elements.evaluationHoldForm.reportValidity()) return;
    changeReviewedRetention({
      benchmark_id: elements.evaluationBenchmarkId.value,
      release_at: `${elements.evaluationBenchmarkRelease.value}:00Z`,
    });
  });
  elements.deleteEvaluationCase.addEventListener("click", async () => {
    if (!reviewedEvaluationCase || !window.confirm(
      `Delete evaluation case ${reviewedEvaluationCase.case_id} now? All text, consent, attempts, annotations, and holds will be deleted immediately.`,
    )) return;
    try {
      await evaluationRequest(
        "Evaluation deletion",
        `/api/evaluation/cases/${reviewedEvaluationCase.case_id}`,
        {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ revision: reviewedEvaluationCase.revision, confirmed: true }),
        },
      );
      closeEvaluationReview();
      await loadEvaluationCases();
    } catch (error) {
      elements.evaluationReviewStatus.textContent = `${error.message} ${error.retryAction}`;
    }
  });

  function closeEvaluationExport() {
    evaluationExportPreview = null;
    elements.evaluationExportWarning.textContent = "";
    elements.evaluationExportMetadata.textContent = "";
    elements.evaluationExportStatus.textContent = "";
    if (elements.evaluationExportDialog.open) elements.evaluationExportDialog.close();
  }

  elements.previewEvaluationExport.addEventListener("click", async () => {
    const cases = selectedEvaluationCases();
    if (cases.length === 0) return;
    elements.evaluationStatus.textContent = "Preparing export preview…";
    try {
      evaluationExportPreview = await evaluationRequest(
        "Evaluation export preview",
        "/api/evaluation/exports/preview",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cases }),
        },
      );
      elements.evaluationExportWarning.textContent = evaluationExportPreview.warning;
      fillDefinitionList(elements.evaluationExportMetadata, [
        ["Cases", String(evaluationExportPreview.case_count)],
        ["Fields", evaluationExportPreview.field_names.join(", ")],
        ["Estimated UTF-8 bytes", String(evaluationExportPreview.total_bytes)],
        ["Expiry range", `${new Date(evaluationExportPreview.minimum_expiry).toLocaleString()} — ${new Date(evaluationExportPreview.maximum_expiry).toLocaleString()}`],
      ]);
      elements.evaluationStatus.textContent = "";
      elements.evaluationExportDialog.showModal();
    } catch (error) {
      elements.evaluationStatus.textContent = `${error.message} ${error.retryAction}`;
    }
  });

  elements.cancelEvaluationExport.addEventListener("click", closeEvaluationExport);
  elements.cancelEvaluationExportSecondary.addEventListener("click", closeEvaluationExport);
  elements.evaluationExportDialog.addEventListener("close", () => {
    evaluationExportPreview = null;
    elements.evaluationExportWarning.textContent = "";
    elements.evaluationExportMetadata.textContent = "";
  });
  elements.confirmEvaluationExport.addEventListener("click", async () => {
    if (!evaluationExportPreview) return;
    if (typeof window.showSaveFilePicker !== "function") {
      elements.evaluationExportStatus.textContent = "This browser cannot require an explicit save destination. Export was not confirmed.";
      return;
    }
    let destination;
    try {
      destination = await window.showSaveFilePicker({
        suggestedName: "cleanup-evaluation.jsonl",
        types: [{
          description: "UTF-8 JSON Lines",
          accept: { "application/x-ndjson": [".jsonl"] },
        }],
      });
    } catch (error) {
      if (error.name !== "AbortError") {
        elements.evaluationExportStatus.textContent = "A private local destination could not be selected. Export was not confirmed.";
      }
      return;
    }
    elements.evaluationExportStatus.textContent = "Exporting to the selected private destination…";
    try {
      const response = await fetch("/api/evaluation/exports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preview_token: evaluationExportPreview.preview_token,
          confirmed: true,
        }),
      });
      if (!response.ok) throw await safeHttpError(response, "Evaluation export");
      const writable = await destination.createWritable();
      await writable.write(await response.arrayBuffer());
      await writable.close();
      closeEvaluationExport();
      elements.evaluationStatus.textContent = "Export written to the selected private destination.";
    } catch (error) {
      elements.evaluationExportStatus.textContent = `${error.message || "The export could not be written."} ${error.retryAction || "Preview and retry the export."}`;
    }
  });
  elements.refreshEvaluation.addEventListener("click", loadEvaluationCases);

  function titleCaseState(value) {
    return String(value || "not_verified")
      .replaceAll("_", " ")
      .replace(/^./, (letter) => letter.toUpperCase());
  }

  function targetDefinitionFromForm() {
    return {
      display_name: elements.targetDisplayName.value,
      application_name: elements.targetApplicationName.value,
      application_bundle_id: elements.targetBundleId.value,
      icon: elements.targetIcon.value,
      send_strategy: elements.targetStrategy.value,
    };
  }

  function renderTargetErrors(target) {
    elements.targetErrors.textContent = "";
    const operationErrors = [...(target?.errors || [])];
    if (targetLocalError) operationErrors.push(targetLocalError);
    elements.targetErrors.hidden = operationErrors.length === 0;
    operationErrors.forEach((error) => {
      const record = document.createElement("article");
      const heading = document.createElement("strong");
      const message = document.createElement("p");
      const recovery = document.createElement("p");
      heading.textContent = `${titleCaseState(error.operation)} failed · ${error.code}`;
      message.textContent = error.message;
      recovery.textContent = error.retry_action;
      record.append(heading, message, recovery);
      elements.targetErrors.append(record);
    });
  }

  function renderTargetList() {
    elements.targetList.textContent = "";
    if (targetRecords.length === 0) {
      const empty = document.createElement("p");
      empty.className = "target-list-empty";
      empty.textContent = "No targets are configured. Create one from a common preset or manually.";
      elements.targetList.append(empty);
    }
    targetRecords.forEach((target) => {
      const item = document.createElement("div");
      const row = document.createElement("button");
      const identity = document.createElement("span");
      const state = document.createElement("span");
      item.className = "target-grid-item";
      item.setAttribute("role", "listitem");
      row.type = "button";
      row.className = "target-row";
      row.dataset.targetId = target.id;
      row.setAttribute("aria-label", `Edit ${target.display_name}, ${titleCaseState(target.state)}`);
      identity.textContent = `${target.icon} ${target.display_name}`;
      state.textContent = `${target.application_name} · ${titleCaseState(target.state)}`;
      row.append(identity, state);
      row.addEventListener("click", () => selectTarget(target.id));
      item.append(row);
      elements.targetList.append(item);
    });
    elements.targetList.append(elements.targetAddItem);
  }

  function populateTargetForm(target) {
    selectedTargetId = target?.id || null;
    targetDraftIsNew = !target;
    targetLocalError = null;
    elements.targetDetailTitle.textContent = target?.display_name || "New target";
    elements.targetDisplayName.value = target?.display_name || "";
    elements.targetApplicationName.value = target?.application_name || "";
    elements.targetBundleId.value = target?.application_bundle_id || "";
    elements.targetIcon.value = target?.icon || "🧵";
    elements.targetStrategy.value = target?.send_strategy || "synthetic_paste";
    elements.targetPreset.value = "manual";
    elements.targetPreview.value = target?.preview || "Save definition to generate a command preview.";
    elements.targetPrimaryState.textContent = titleCaseState(target?.state || "not_installed");
    elements.targetInstallationState.textContent = titleCaseState(target?.installation || "not_installed");
    elements.targetAvailability.textContent = titleCaseState(target?.availability || "not_verified");
    elements.targetPermission.textContent = titleCaseState(target?.permission || "not_verified");
    elements.targetReadinessAction.textContent = target
      ? `${target.availability_action} ${target.permission_action}`
      : "Save the definition before checking readiness.";
    elements.installTarget.disabled = !target || !target.enabled;
    elements.installTarget.textContent = !target || target.installation === "not_installed"
      ? "Install command"
      : "Regenerate command";
    elements.toggleTargetEnabled.disabled = !target;
    elements.toggleTargetEnabled.textContent = target?.enabled === false
      ? "Enable target"
      : "Disable target";
    elements.removeTarget.disabled = !target;
    targetDirty = false;
    elements.targetSaveState.textContent = target ? "Saved" : "Not saved";
    renderTargetErrors(target);
    renderTargetList();
    if (!elements.targetDialog.open) elements.targetDialog.showModal();
  }

  function confirmDiscardTargetDraft() {
    return !targetDirty || window.confirm("Discard unsaved target definition changes?");
  }

  function selectTarget(targetId) {
    if (!confirmDiscardTargetDraft()) return;
    const target = targetRecords.find((candidate) => candidate.id === targetId);
    if (target) populateTargetForm(target);
  }

  async function loadTargets(preferredId = selectedTargetId) {
    const response = await fetch("/api/targets");
    if (!response.ok) throw await safeHttpError(response, "Target loading");
    const result = await readJson(response, "Target loading");
    if (!result || !Array.isArray(result.targets)) {
      throw malformedResponseError("Target loading", response.status);
    }
    targetRecords = result.targets;
    const selected = targetRecords.find((target) => target.id === preferredId)
      || null;
    renderTargetList();
    if (selected) populateTargetForm(selected);
  }

  async function targetRequest(operation, url, options = {}) {
    targetLocalError = null;
    const response = await fetch(url, options);
    if (!response.ok) {
      const error = await safeHttpError(response, operation);
      targetLocalError = {
        operation,
        code: error.code,
        message: error.message,
        retry_action: error.retryAction,
      };
      renderTargetErrors(targetRecords.find((target) => target.id === selectedTargetId));
      throw error;
    }
    if (response.status === 204) return null;
    return readJson(response, operation);
  }

  function showDestination(destination) {
    const settingsVisible = destination === "settings";
    const evaluationVisible = destination === "evaluation";
    const workspaceVisible = !settingsVisible && !evaluationVisible;
    elements.workspace.hidden = !workspaceVisible;
    elements.workspaceControls.hidden = !workspaceVisible;
    elements.workspaceOutgoing.hidden = !workspaceVisible;
    elements.settingsManager.hidden = !settingsVisible;
    elements.evaluationManager.hidden = !evaluationVisible;
    elements.navWorkspace.classList.toggle("is-active", workspaceVisible);
    elements.navSettings.classList.toggle("is-active", settingsVisible);
    elements.navEvaluation.classList.toggle("is-active", evaluationVisible);
    elements.navWorkspace.toggleAttribute("aria-current", workspaceVisible);
    elements.navSettings.toggleAttribute("aria-current", settingsVisible);
    elements.navEvaluation.toggleAttribute("aria-current", evaluationVisible);
    if (!settingsVisible && elements.targetDialog.open) elements.targetDialog.close();
    if (settingsVisible && targetRecords.length === 0) {
      loadTargets().catch((error) => {
        targetLocalError = {
          operation: "target loading",
          code: error.code || "network_unavailable",
          message: error.message || "Targets could not be loaded.",
          retry_action: error.retryAction || "Retry loading targets.",
        };
        renderTargetErrors(null);
      });
    }
    if (evaluationVisible) loadEvaluationCases();
  }

  elements.navWorkspace.addEventListener("click", () => {
    if (!confirmDiscardTargetDraft()) return;
    targetDirty = false;
    showDestination("workspace");
  });
  elements.navSettings.addEventListener("click", () => showDestination("settings"));
  elements.navEvaluation.addEventListener("click", () => {
    if (!confirmDiscardTargetDraft()) return;
    targetDirty = false;
    showDestination("evaluation");
  });
  elements.newTarget.addEventListener("click", () => {
    if (confirmDiscardTargetDraft()) populateTargetForm(null);
  });
  elements.targetListBack.addEventListener("click", () => {
    if (!confirmDiscardTargetDraft()) return;
    targetDirty = false;
    elements.targetDialog.close();
  });
  elements.targetDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    if (!confirmDiscardTargetDraft()) return;
    targetDirty = false;
    elements.targetDialog.close();
  });
  elements.targetDialog.addEventListener("click", (event) => {
    if (event.target !== elements.targetDialog || !confirmDiscardTargetDraft()) return;
    targetDirty = false;
    elements.targetDialog.close();
  });
  elements.targetPreset.addEventListener("change", () => {
    const preset = targetPresets[elements.targetPreset.value];
    if (!preset) return;
    [
      elements.targetDisplayName.value,
      elements.targetApplicationName.value,
      elements.targetBundleId.value,
      elements.targetStrategy.value,
    ] = preset;
    targetDirty = true;
    elements.targetSaveState.textContent = "Unsaved changes";
  });
  [
    elements.targetDisplayName,
    elements.targetApplicationName,
    elements.targetBundleId,
    elements.targetIcon,
    elements.targetStrategy,
  ].forEach((field) => field.addEventListener("input", () => {
    targetDirty = true;
    elements.targetSaveState.textContent = "Unsaved changes";
  }));
  elements.targetDetail.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!elements.targetDetail.reportValidity()) return;
    elements.targetSaveState.textContent = "Saving…";
    const url = targetDraftIsNew ? "/api/targets" : `/api/targets/${selectedTargetId}`;
    try {
      const saved = await targetRequest("save definition", url, {
        method: targetDraftIsNew ? "POST" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(targetDefinitionFromForm()),
      });
      selectedTargetId = saved.id;
      await loadTargets(saved.id);
    } catch (_error) {
      elements.targetSaveState.textContent = "Save failed";
    }
  });
  elements.installTarget.addEventListener("click", async () => {
    if (targetDirty) {
      elements.targetSaveState.textContent = "Save changes before installing";
      return;
    }
    elements.installTarget.disabled = true;
    elements.installTarget.textContent = "Installing…";
    try {
      await targetRequest("install", `/api/targets/${selectedTargetId}/install`, { method: "POST" });
      await loadTargets(selectedTargetId);
    } catch (_error) {
      elements.installTarget.disabled = false;
      elements.installTarget.textContent = "Retry installation";
    }
  });
  elements.checkTarget.addEventListener("click", () => loadTargets(selectedTargetId));
  elements.toggleTargetEnabled.addEventListener("click", async () => {
    const target = targetRecords.find((candidate) => candidate.id === selectedTargetId);
    if (!target || !confirmDiscardTargetDraft()) return;
    const operation = target.enabled ? "disable" : "enable";
    const consequence = target.enabled
      ? "Disable this target? Its recognized Sayloom-owned command will be removed. Outgoing will not change."
      : "Enable this target? It will remain uninstalled until you explicitly install it.";
    if (!window.confirm(consequence)) return;
    try {
      await targetRequest(operation, `/api/targets/${target.id}/${operation}`, { method: "POST" });
      await loadTargets(target.id);
    } catch (_error) { /* Persistent target error is rendered above. */ }
  });
  elements.removeTarget.addEventListener("click", async () => {
    const target = targetRecords.find((candidate) => candidate.id === selectedTargetId);
    if (!target || !confirmDiscardTargetDraft()) return;
    if (!window.confirm(
      `Remove ${target.display_name}? Its recognized Sayloom-owned command and definition will be deleted. Outgoing will not change.`,
    )) return;
    try {
      await targetRequest("remove", `/api/targets/${target.id}`, { method: "DELETE" });
      selectedTargetId = null;
      targetDirty = false;
      elements.targetDialog.close();
      await loadTargets();
    } catch (_error) { /* Persistent target error is rendered above. */ }
  });

  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      runCleanup();
    }
  });

  window.addEventListener("blur", () => {
    returnSelectionPending = true;
  });
  window.addEventListener("beforeunload", (event) => {
    if (!targetDirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
  window.addEventListener("pagehide", () => {
    if (!evidenceLease) return;
    fetch(
      `/api/evidence-collection/arm?lease_token=${encodeURIComponent(evidenceLease)}`,
      { method: "DELETE", keepalive: true },
    )
      .catch(() => {});
  });
  window.addEventListener("focus", () => {
    if (!returnSelectionPending || !elements.original.value) return;
    returnSelectionPending = false;
    window.requestAnimationFrame(() => {
      elements.original.focus({ preventScroll: true });
      elements.original.setSelectionRange(0, elements.original.value.length);
    });
  });

  async function initialize() {
    try {
      readWorkspacePreferences();
      renderSidebar();
      renderMaximizedPane();
      renderWorkspaceLayout();
      const evidenceHeaders = { "X-Evidence-Browser-Session": browserSessionId };
      const previousEvidenceLease = storedEvidenceLease();
      if (previousEvidenceLease) {
        evidenceHeaders["X-Evidence-Previous-Lease"] = previousEvidenceLease;
      }
      const [configResponse] = await Promise.all([
        fetch("/api/config", {
          headers: evidenceHeaders,
        }),
        clearPublishedState(),
      ]);
      if (!configResponse.ok) throw await safeHttpError(configResponse, "Workspace configuration");
      const config = await readJson(configResponse, "Workspace configuration");
      storeEvidenceLease(null);

      defaultPreparationMode = ["off", "conservative", "smart"].includes(config.preparation_default)
        ? config.preparation_default
        : "conservative";
      elements.cleanupEnabled.checked = defaultPreparationMode !== "off";
      currentOriginalText = elements.original.value;
      draftCorrectionMode = currentOriginalText
        ? defaultPreparationMode === "smart" ? "smart" : "conservative"
        : null;
      elements.modeSaveState.textContent = `${titleCaseState(defaultPreparationMode)} is the saved default.`;
      renderCorrectionMode();
      renderCleanupConfiguration(config.cleanup_configuration);
      evidenceReady = config.evidence_collection?.ready === true;
      evidenceLease = null;
      blockedEvidenceLease = null;
      evidenceReceipt = null;
      renderEvidenceCollection();
      evaluationAvailable = config.evaluation_configuration?.available === true;
      elements.evaluationStatus.textContent = evaluationAvailable
        ? "Evaluation storage is configured and current."
        : "Evaluation storage is not configured and current.";

      elements.prepared.value = "";
      invalidateSmartRepairReview();
      invalidateEvaluationCapture();
      originalOutgoingOverride = false;
      setStatus(elements.cleanupEnabled.checked ? "unchanged" : "disabled");
      renderCountsAndSelection();
      if (!elements.original.value) elements.original.focus({ preventScroll: true });
    } catch (error) {
      const safe = error?.code ? error : networkError("Workspace configuration");
      setStatus("error");
      setCleanupError(safe);
    }
  }

  initialize();
})();
