(() => {
  "use strict";

  const CLEANUP_DEBOUNCE_MS = 700;
  const PUBLICATION_DEBOUNCE_MS = 150;
  const WORKSPACE_PREFERENCES_KEY = "local-text.workspace-preferences.v1";
  const DEFAULT_STACKED_SHARE = 55;
  const DEFAULT_SIDE_BY_SIDE_SHARE = 50;
  const MINIMUM_ORIGINAL_SHARE = 25;
  const MAXIMUM_ORIGINAL_SHARE = 75;
  const narrowWorkspace = window.matchMedia
    ? window.matchMedia("(max-width: 980px)")
    : { matches: false, addEventListener() {} };

  const elements = {
    original: document.querySelector("#original-text"),
    prepared: document.querySelector("#prepared-text"),
    correctPrepared: document.querySelector("#correct-prepared"),
    preparedOrigin: document.querySelector("#prepared-origin"),
    preparedCorrectionDialog: document.querySelector("#prepared-correction-dialog"),
    preparedCorrectionForm: document.querySelector("#prepared-correction-form"),
    intendedPrepared: document.querySelector("#intended-prepared"),
    reviewPersonalCorrections: document.querySelector("#review-personal-corrections"),
    preparedCorrectionState: document.querySelector("#prepared-correction-state"),
    confirmPrepared: document.querySelector("#confirm-prepared"),
    cancelPreparedCorrection: document.querySelector("#cancel-prepared-correction"),
    draftPreparationMode: document.querySelector("#draft-preparation-mode"),
    smartModeDisclosure: document.querySelector("#smart-mode-disclosure"),
    defaultPreparationMode: document.querySelector("#default-preparation-mode"),
    modeSaveState: document.querySelector("#mode-save-state"),
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
    cleanupResult: document.querySelector("#cleanup-result"),
    cleanupResultStatus: document.querySelector("#cleanup-result-status"),
    cleanupAttemptDetails: document.querySelector("#cleanup-attempt-details"),
    cleanupAttemptList: document.querySelector("#cleanup-attempt-list"),
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
    settingsManager: document.querySelector("#settings-manager"),
    personalCorrectionsToggle: document.querySelector("#personal-corrections-toggle"),
    personalCorrectionsState: document.querySelector("#personal-corrections-state"),
    personalCorrectionForm: document.querySelector("#personal-correction-form"),
    personalCorrectionTerm: document.querySelector("#personal-correction-term"),
    personalCorrectionAliases: document.querySelector("#personal-correction-aliases"),
    personalCorrectionContext: document.querySelector("#personal-correction-context"),
    personalCorrectionsEmpty: document.querySelector("#personal-corrections-empty"),
    personalCorrectionList: document.querySelector("#personal-correction-list"),
    missedRepairDialog: document.querySelector("#missed-repair-dialog"),
    missedRepairForm: document.querySelector("#missed-repair-form"),
    closeMissedRepair: document.querySelector("#close-missed-repair"),
    dismissMissedRepair: document.querySelector("#dismiss-missed-repair"),
    missedRepairReviewState: document.querySelector("#missed-repair-review-state"),
    missedRepairSentences: document.querySelector("#missed-repair-sentences"),
    missedRepairCandidates: document.querySelector("#missed-repair-candidates"),
    missedRepairCandidateList: document.querySelector("#missed-repair-candidate-list"),
    retainObservedSentence: document.querySelector("#retain-observed-sentence"),
    observedSentence: document.querySelector("#observed-sentence"),
    observedSentenceCount: document.querySelector("#observed-sentence-count"),
    observedSentenceRemoved: document.querySelector("#observed-sentence-removed"),
    retainIntendedSentence: document.querySelector("#retain-intended-sentence"),
    intendedSentence: document.querySelector("#intended-sentence"),
    intendedSentenceCount: document.querySelector("#intended-sentence-count"),
    intendedSentenceRemoved: document.querySelector("#intended-sentence-removed"),
    missedRepairContextField: document.querySelector("#missed-repair-context-field"),
    missedRepairContext: document.querySelector("#missed-repair-context"),
    missedRepairApproval: document.querySelector("#missed-repair-approval"),
    missedRepairSavedResult: document.querySelector("#missed-repair-saved-result"),
    missedRepairSavedMappings: document.querySelector("#missed-repair-saved-mappings"),
    missedRepairSavedContext: document.querySelector("#missed-repair-saved-context"),
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
  let draftPreparationMode = "conservative";
  let draftRevision = 0;
  let preparedCorrectionRevision = null;
  let preparedCorrectionStartingText = null;
  let confirmedPreparedRevision = null;
  let draftModeOverridden = false;
  let currentOriginalText = elements.original.value;
  let failedCorrectionMode = null;
  let smartRepairs = [];
  let selectedSmartRepair = null;
  let smartRepairResultCurrent = false;
  let personalCorrectionProfile = { enabled: false, entries: [] };
  let activePromptVersionId = null;
  let missedRepairBinding = null;
  let targetRecords = [];
  let selectedTargetId = null;
  let targetDirty = false;
  let targetDraftIsNew = false;
  let targetLocalError = null;
  const errors = { cleanup: null, publication: null };

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
    return draftPreparationMode === "smart" ? "smart" : "conservative";
  }

  function renderExplicitSmartAction() {
    elements.retryCleanup.textContent = failedCorrectionMode === "smart"
      ? "Try Conservative"
      : "Retry cleanup";
  }

  function setExplicitSmartState() {
    renderExplicitSmartAction();
  }

  function clearCleanupAttempts() {
    elements.cleanupResult.hidden = true;
    elements.cleanupResultStatus.hidden = true;
    elements.cleanupResultStatus.textContent = "";
    elements.cleanupAttemptDetails.open = false;
    elements.cleanupAttemptList.textContent = "";
  }

  function renderCleanupAttempts(result) {
    const attempts = Array.isArray(result?.attempts)
      ? result.attempts.filter((attempt) => (
          typeof attempt?.provider === "string"
          && typeof attempt?.model === "string"
          && Number.isInteger(attempt?.route_index)
          && attempt.route_index >= 0
          && ["success", "failure"].includes(attempt?.outcome)
        ))
      : [];
    clearCleanupAttempts();
    if (!attempts.length) return;
    attempts.forEach((attempt) => {
      const item = document.createElement("li");
      const outcome = attempt.outcome === "success" ? "Succeeded" : "Failed";
      item.textContent = `Route ${attempt.route_index + 1}: ${attempt.provider} · ${attempt.model} — ${outcome}`;
      elements.cleanupAttemptList.append(item);
    });
    const backupSuccess = attempts.some(
      (attempt) => attempt.outcome === "success" && attempt.route_index > 0,
    );
    elements.cleanupResultStatus.hidden = !backupSuccess;
    elements.cleanupResultStatus.textContent = backupSuccess ? "Prepared with backup model" : "";
    elements.cleanupResult.hidden = false;
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

  function missedRepairIsCurrent(binding) {
    return binding
      && binding.postRevision === draftRevision
      && confirmedPreparedRevision === draftRevision
      && binding.postEdit === elements.prepared.value
      && preparedCorrectionRevision === null;
  }

  function markMissedRepairStale(reason) {
    if (!missedRepairBinding) return;
    if (["loading", "reviewing", "saving", "stale"].includes(missedRepairBinding.state)) {
      missedRepairBinding.state = "stale";
      elements.missedRepairReviewState.dataset.state = "stale";
      elements.missedRepairReviewState.textContent = reason;
      elements.missedRepairApproval.disabled = true;
    } else {
      missedRepairBinding = null;
    }
  }

  function updateSentenceLimitState() {
    const fields = [
      [elements.retainObservedSentence, elements.observedSentence, elements.observedSentenceCount,
        elements.observedSentenceRemoved],
      [elements.retainIntendedSentence, elements.intendedSentence, elements.intendedSentenceCount,
        elements.intendedSentenceRemoved],
    ];
    let overLimit = false;
    fields.forEach(([retained, field, count, removed]) => {
      const included = retained.dataset.included === "true";
      field.disabled = !included || Boolean(missedRepairBinding?.savePayload)
        || missedRepairBinding?.state === "stale";
      retained.textContent = included ? "Remove from saved episode" : "Include in saved episode";
      removed.hidden = included;
      const length = Array.from(field.value).length;
      const fieldOverLimit = included && length > 500;
      overLimit ||= fieldOverLimit;
      field.classList.toggle("is-over-limit", fieldOverLimit);
      count.textContent = included ? `${length} / 500 code points` : "";
      count.classList.toggle("is-over-limit", fieldOverLimit);
    });
    if (missedRepairBinding?.state === "reviewing") {
      elements.missedRepairReviewState.dataset.state = overLimit ? "error" : "ready";
      elements.missedRepairReviewState.textContent = overLimit
        ? "Shorten or remove each sentence over 500 code points before saving."
        : "Prepared is already confirmed. Select replacements to remember. Additions and removals cannot be saved in v1; they remain in Prepared.";
    }
    updateMissedRepairApprovalState();
  }

  function selectedMissedRepairMappings() {
    return Array.from(elements.missedRepairCandidateList.children)
      .filter((item) => item.children[0].checked)
      .map((item) => ({
        operation: "replacement",
        observed_text: item.children[1].children[1].value,
        intended_text: item.children[3].children[1].value,
      }));
  }

  function validPersonalCorrectionText(value, maximum) {
    const length = Array.from(value).length;
    return Boolean(value.trim()) && length <= maximum && !/[\u0000-\u001f\u007f-\u009f]/u.test(value);
  }

  function updateMissedRepairApprovalState() {
    const mappings = selectedMissedRepairMappings();
    const sentencesValid = [
      [elements.retainObservedSentence, elements.observedSentence],
      [elements.retainIntendedSentence, elements.intendedSentence],
    ].every(([toggle, field]) => (
      toggle.dataset.included !== "true" || validPersonalCorrectionText(field.value, 500)
    ));
    const contextValid = !elements.missedRepairContext.value
      || validPersonalCorrectionText(elements.missedRepairContext.value, 500);
    const mappingValid = mappings.length > 0 && mappings.every((mapping) => (
      validPersonalCorrectionText(mapping.observed_text, 200)
      && validPersonalCorrectionText(mapping.intended_text, 200)
    ));
    const ready = missedRepairBinding?.state === "reviewing"
      && missedRepairIsCurrent(missedRepairBinding)
      && sentencesValid && contextValid && mappingValid;
    elements.missedRepairApproval.disabled = !ready;
    if (missedRepairBinding?.state === "reviewing" && !missedRepairBinding.saveFailed) {
      elements.missedRepairApproval.textContent = "Save selected";
    }
  }

  function renderMissedRepairCandidates(candidates) {
    elements.missedRepairCandidateList.textContent = "";
    candidates.forEach((candidate) => {
      const item = document.createElement("li");
      const selected = document.createElement("input");
      const observedField = document.createElement("label");
      const observedLabel = document.createElement("span");
      const observed = document.createElement("input");
      const arrow = document.createElement("span");
      const intendedField = document.createElement("label");
      const intendedLabel = document.createElement("span");
      const intended = document.createElement("input");
      item.className = "missed-repair-candidate";
      selected.type = "checkbox";
      selected.checked = false;
      selected.setAttribute("aria-label", `Select ${candidate.operation} ${candidate.queue_position}`);
      observedField.className = "missed-repair-mapping-field";
      observedLabel.textContent = "Observed";
      observed.type = "text";
      observed.maxLength = 200;
      observed.value = candidate.original_span.text;
      observed.placeholder = "No observed text";
      observed.setAttribute("aria-label", `Observed text for ${candidate.operation} ${candidate.queue_position}`);
      arrow.textContent = "→";
      arrow.className = "missed-repair-mapping-arrow";
      arrow.setAttribute("aria-hidden", "true");
      intendedField.className = "missed-repair-mapping-field";
      intendedLabel.textContent = "Intended";
      intended.type = "text";
      intended.maxLength = 200;
      intended.value = candidate.prepared_span.text;
      intended.placeholder = "No intended text";
      intended.setAttribute("aria-label", `Intended text for ${candidate.operation} ${candidate.queue_position}`);
      observedField.append(observedLabel, observed);
      intendedField.append(intendedLabel, intended);
      item.dataset.operation = candidate.operation;
      item.append(selected, observedField, arrow, intendedField);
      selected.addEventListener("change", updateMissedRepairApprovalState);
      observed.addEventListener("input", updateMissedRepairApprovalState);
      intended.addEventListener("input", updateMissedRepairApprovalState);
      elements.missedRepairCandidateList.append(item);
    });
  }

  async function openMissedRepairReview() {
    if (!missedRepairIsCurrent(missedRepairBinding)) return;
    const binding = missedRepairBinding;
    binding.state = "loading";
    elements.missedRepairCandidateList.textContent = "";
    elements.missedRepairSentences.hidden = true;
    elements.missedRepairCandidates.hidden = true;
    elements.missedRepairContextField.hidden = true;
    elements.missedRepairSavedResult.hidden = true;
    elements.missedRepairApproval.hidden = false;
    elements.missedRepairApproval.disabled = true;
    elements.missedRepairApproval.textContent = "Save selected";
    elements.dismissMissedRepair.textContent = "Not now";
    elements.missedRepairReviewState.dataset.state = "loading";
    elements.missedRepairReviewState.textContent = "Deriving correction candidates…";
    elements.missedRepairDialog.showModal();
    try {
      const response = await fetch("/api/personal-corrections/candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          before_text: binding.preEdit,
          after_text: binding.postEdit,
          source_mode: "user_confirmed",
          prompt_version_id: null,
          correction_contract_version: "personal-correction-v1",
        }),
      });
      if (!response.ok) throw await safeHttpError(response, "Correction candidate review");
      const result = await readJson(response, "Correction candidate review");
      if (
        binding !== missedRepairBinding
        || binding.state !== "loading"
        || !missedRepairIsCurrent(binding)
      ) {
        if (binding === missedRepairBinding) markMissedRepairStale("This review is stale because the draft changed.");
        return;
      }
      if (
        !result || !validateSmartRepairs(result.candidates, binding.preEdit, binding.postEdit)
        || typeof result.observed_sentence !== "string"
        || typeof result.intended_sentence !== "string"
        || !["string", "object"].includes(typeof result.applicability_context)
      ) throw malformedResponseError("Correction candidate review", response.status);
      binding.state = "reviewing";
      binding.approvalId = crypto.randomUUID();
      binding.saveFailed = false;
      renderMissedRepairCandidates(result.candidates.filter((candidate) => (
        candidate.operation === "replacement"
        && candidate.original_span.text.trim() && candidate.prepared_span.text.trim()
      )));
      elements.retainObservedSentence.dataset.included = "true";
      elements.observedSentence.value = result.observed_sentence;
      elements.retainIntendedSentence.dataset.included = "true";
      elements.intendedSentence.value = result.intended_sentence;
      elements.missedRepairContext.value = result.applicability_context || "";
      elements.missedRepairContext.disabled = false;
      elements.retainObservedSentence.disabled = false;
      elements.retainIntendedSentence.disabled = false;
      elements.missedRepairSavedResult.hidden = true;
      elements.missedRepairSentences.hidden = false;
      elements.missedRepairCandidates.hidden = false;
      elements.missedRepairContextField.hidden = false;
      elements.missedRepairApproval.hidden = false;
      elements.dismissMissedRepair.textContent = "Not now";
      updateSentenceLimitState();
    } catch (error) {
      if (binding !== missedRepairBinding || binding.state === "stale") return;
      if (error?.code === "stale_personal_correction_result") {
        markMissedRepairStale("This review is stale because the prompt version changed.");
        return;
      }
      missedRepairBinding = null;
      elements.missedRepairReviewState.dataset.state = "error";
      elements.missedRepairReviewState.textContent = (
        "Correction candidates could not be derived. Your confirmed Prepared remains intact."
      );
      elements.missedRepairApproval.disabled = true;
    }
  }

  function dismissMissedRepairReview() {
    missedRepairBinding = null;
    elements.missedRepairDialog.close();
  }

  function toggleMissedRepairSentence(toggle) {
    if (!["reviewing"].includes(missedRepairBinding?.state)) return;
    toggle.dataset.included = String(toggle.dataset.included !== "true");
    updateSentenceLimitState();
  }

  async function saveMissedRepairReview() {
    const binding = missedRepairBinding;
    const mappings = selectedMissedRepairMappings();
    if (
      !binding || binding.state !== "reviewing" || !mappings.length
      || !missedRepairIsCurrent(binding)
      || elements.missedRepairApproval.disabled
    ) {
      markMissedRepairStale("This review is stale because the draft changed.");
      return;
    }
    binding.state = "saving";
    binding.saveFailed = false;
    elements.missedRepairReviewState.dataset.state = "saving";
    elements.missedRepairReviewState.textContent = "Saving Personal Correction…";
    elements.missedRepairApproval.disabled = true;
    elements.missedRepairApproval.textContent = "Saving…";
    // A retry must resubmit the exact approval, even if the first response was lost.
    binding.savePayload ||= JSON.stringify({
      approval_id: binding.approvalId,
      source_mode: "user_confirmed",
      prompt_version_id: null,
      correction_contract_version: "personal-correction-v1",
      observed_sentence: elements.retainObservedSentence.dataset.included === "true"
        ? elements.observedSentence.value : null,
      intended_sentence: elements.retainIntendedSentence.dataset.included === "true"
        ? elements.intendedSentence.value : null,
      applicability_context: elements.missedRepairContext.value || null,
      mappings,
    });
    elements.missedRepairForm.querySelectorAll("input, textarea").forEach((field) => {
      field.disabled = true;
    });
    elements.retainObservedSentence.disabled = true;
    elements.retainIntendedSentence.disabled = true;
    try {
      const response = await fetch("/api/personal-corrections/episodes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: binding.savePayload,
      });
      if (!response.ok) throw await safeHttpError(response, "Personal Correction approval");
      const result = await readJson(response, "Personal Correction approval");
      if (binding !== missedRepairBinding || binding.state === "stale") return;
      if (!missedRepairIsCurrent(binding)) {
        markMissedRepairStale("This review is stale because the draft changed.");
        return;
      }
      if (!Array.isArray(result?.mappings) || !result.mappings.length) {
        throw malformedResponseError("Personal Correction approval", response.status);
      }
      binding.state = "saved";
      elements.missedRepairReviewState.dataset.state = "saved";
      elements.missedRepairReviewState.textContent = "Selected Personal Corrections saved. Prepared is unchanged.";
      elements.missedRepairSavedMappings.replaceChildren(...result.mappings.map((mapping) => {
        const item = document.createElement("li");
        item.textContent = `${mapping.observed_text} → ${mapping.intended_text}`;
        return item;
      }));
      const savedContext = JSON.parse(binding.savePayload).applicability_context;
      elements.missedRepairSavedContext.textContent = savedContext
        ? `Applies when: ${savedContext}` : "No applicability context saved.";
      elements.missedRepairSentences.hidden = true;
      elements.missedRepairCandidates.hidden = true;
      elements.missedRepairContextField.hidden = true;
      elements.missedRepairSavedResult.hidden = false;
      elements.missedRepairApproval.hidden = true;
      elements.dismissMissedRepair.textContent = "Close";
    } catch (error) {
      if (binding !== missedRepairBinding || binding.state === "stale") return;
      if (error?.code === "stale_personal_correction_result") {
        markMissedRepairStale("This review is stale because the prompt version changed.");
        return;
      }
      binding.state = "reviewing";
      binding.saveFailed = true;
      elements.missedRepairReviewState.dataset.state = "error";
      elements.missedRepairReviewState.textContent = "Save could not be confirmed. Prepared is intact. Retry the same selected batch, or dismiss; no partial batch is saved.";
      elements.missedRepairApproval.textContent = "Retry Save selected";
      updateMissedRepairApprovalState();
    }
  }

  function renderCorrectionMode() {
    elements.defaultPreparationMode.value = defaultPreparationMode;
    elements.draftPreparationMode.value = draftPreparationMode;
    elements.smartModeDisclosure.hidden = draftPreparationMode !== "smart";
    elements.smartTaskContextField.hidden = draftPreparationMode !== "smart";
    elements.smartTaskContext.disabled = draftPreparationMode !== "smart";
    elements.runCleanup.disabled = draftPreparationMode === "off";
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
    return Boolean(elements.original.value)
      && (status === "prepared" || status === "unchanged")
      && Boolean(elements.prepared.value);
  }

  function manualPreparationProtected() {
    return preparedCorrectionRevision !== null || confirmedPreparedRevision === draftRevision;
  }

  function renderPreparedCorrection() {
    const stale = preparedCorrectionRevision !== draftRevision;
    const empty = !elements.intendedPrepared.value.trim();
    elements.confirmPrepared.disabled = stale || empty;
    elements.preparedCorrectionState.textContent = stale
      ? "Original changed. Cancel and reopen Correct Prepared for the current Original."
      : empty
        ? "Intended wording is required; empty or whitespace-only text cannot be confirmed."
        : "Confirmation preserves your exact wording. Copying or delivery is a separate action.";
  }

  function cancelPreparedCorrection() {
    preparedCorrectionRevision = null;
    preparedCorrectionStartingText = null;
    elements.preparedCorrectionDialog.close();
    elements.intendedPrepared.value = "";
    renderCountsAndSelection();
  }

  function openPreparedCorrection() {
    if (!preparedIsCurrent()) return;
    const startingText = elements.prepared.value;
    window.clearTimeout(cleanupTimer);
    cleanupTimer = null;
    abortActiveRequest();
    markMissedRepairStale("This review was superseded by a new correction.");
    preparedCorrectionRevision = draftRevision;
    preparedCorrectionStartingText = startingText;
    elements.reviewPersonalCorrections.checked = false;
    elements.intendedPrepared.value = startingText;
    if (["waiting", "cleaning"].includes(status)) setStatus("stale");
    setExplicitSmartState("hidden");
    renderPreparedCorrection();
    elements.preparedCorrectionDialog.showModal();
    elements.intendedPrepared.focus();
    schedulePublication();
  }

  function fallbackLabel() {
    if (!elements.original.value) return "Nothing yet";
    if (originalOutgoingOverride) return "Using Original — Selected for this draft";
    if (preparedIsCurrent() && confirmedPreparedRevision === draftRevision) {
      return "Using Prepared — User-confirmed";
    }
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
      cleanup_enabled: draftPreparationMode !== "off",
      original_text: originalText,
      prepared_text: preparedText,
      outgoing_text: outgoingText,
      outgoing_kind: outgoingKind,
      status,
      correction_mode: effectiveCorrectionMode(),
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
    elements.correctPrepared.hidden = !preparedIsCurrent();
    elements.correctPrepared.disabled = !preparedIsCurrent();
    elements.preparedOrigin.textContent = preparedIsCurrent()
      ? confirmedPreparedRevision === draftRevision ? "User-confirmed" : "Generated"
      : "No current Prepared";
  }

  function setPublicationState(nextState, label) {
    elements.publication.dataset.state = nextState;
    elements.publication.lastElementChild.textContent = label;
    elements.publication.hidden = nextState !== "error";
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
        : route.provider === "openrouter" ? "OpenRouter"
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
      ? routes.map((route) => route.provider === "openrouter" ? "OpenRouter"
        : route.provider === "openai" ? "OpenAI" : "Gemini").join(" → ")
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

  function setCleanupError(error, correctionMode = null) {
    failedCorrectionMode = error === null ? null : correctionMode;
    renderExplicitSmartAction();
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
    try {
      await navigator.clipboard.writeText(selectedOutgoingState().outgoing_text);
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

  async function runCleanup(
    requestedCorrectionMode = null,
    invocation = "manual",
  ) {
    if (invocation === "automatic" && manualPreparationProtected()) return;
    if (preparedCorrectionRevision !== null) cancelPreparedCorrection();
    confirmedPreparedRevision = null;
    window.clearTimeout(cleanupTimer);
    cleanupTimer = null;
    if (invocation !== "automatic") {
      markMissedRepairStale("This review is stale because cleanup was run again.");
    }
    abortActiveRequest();
    setCleanupError(null);
    clearCleanupAttempts();
    invalidateSmartRepairReview();

    const originalText = elements.original.value;
    const requestDraftRevision = draftRevision;
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
    if (draftPreparationMode === "off") {
      elements.prepared.value = "";
      setStatus("disabled");
      if (explicitSmart) setExplicitSmartState("retry", "Smart correction needs cleanup enabled.");
      schedulePublication();
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
          ...(Number.isInteger(activePromptVersionId)
            ? { prompt_version_id: activePromptVersionId }
            : {}),
          ...(taskContext.trim() ? { task_context: taskContext } : {}),
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const error = await safeHttpError(response, "Cleanup");
        if (
          sequence !== requestSequence
          || requestDraftRevision !== draftRevision
          || originalText !== elements.original.value
          || correctionMode !== effectiveCorrectionMode()
          || taskContext !== (correctionMode === "smart" ? elements.smartTaskContext.value : "")
        ) return;
        elements.prepared.value = originalText;
        setStatus("error");
        setCleanupError(error, correctionMode);
        if (explicitSmart) setExplicitSmartState("retry", "Smart correction failed.");
        restoreOriginalSelection(selection);
        return;
      }
      const result = await readJson(response, "Cleanup");
      if (
        sequence !== requestSequence
        || requestDraftRevision !== draftRevision
        || originalText !== elements.original.value
        || correctionMode !== effectiveCorrectionMode()
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
        setCleanupError(malformedResponseError("Cleanup", response.status), correctionMode);
        if (explicitSmart) setExplicitSmartState("retry", "Smart correction failed.");
        restoreOriginalSelection(selection);
        return;
      }

      elements.prepared.value = result.prepared_text;
      renderCleanupAttempts(result);
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
        }), correctionMode);
      } else {
        setCleanupError(null);
      }
      restoreOriginalSelection(selection);
    } catch (error) {
      if (
        sequence !== requestSequence
        || requestDraftRevision !== draftRevision
        || originalText !== elements.original.value
        || correctionMode !== effectiveCorrectionMode()
        || taskContext !== (correctionMode === "smart" ? elements.smartTaskContext.value : "")
      ) return;
      elements.prepared.value = originalText;
      setStatus("error");
      if (error.name !== "AbortError") {
        setCleanupError(error?.code ? error : networkError("Cleanup"), correctionMode);
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
    cleanupTimer = null;
    if (manualPreparationProtected()) return;
    setExplicitSmartState("hidden");
    setCleanupError(null);
    clearCleanupAttempts();
    invalidateSmartRepairReview();
    if (draftPreparationMode === "off") {
      elements.prepared.value = "";
      setStatus("disabled");
      schedulePublication();
      return;
    }
    abortActiveRequest();
    setStatus("waiting");
    schedulePublication();
    cleanupTimer = window.setTimeout(
      () => runCleanup(null, "automatic"),
      CLEANUP_DEBOUNCE_MS,
    );
  }

  function originalIsFullySelected() {
    return elements.original.value.length > 0
      && elements.original.selectionStart === 0
      && elements.original.selectionEnd === elements.original.value.length;
  }

  function handleOriginalInput(event) {
    const originalChanged = elements.original.value !== currentOriginalText;
    if (originalChanged) {
      draftRevision += 1;
      if (confirmedPreparedRevision !== null || preparedCorrectionRevision !== null) {
        confirmedPreparedRevision = null;
        elements.prepared.value = "";
        originalOutgoingOverride = false;
        setStatus("stale");
        invalidateSmartRepairReview();
        if (preparedCorrectionRevision !== null) renderPreparedCorrection();
        schedulePublication();
      }
    }
    const replacedAll = replaceAllPending && originalChanged;
    if (replacedAll) {
      draftPreparationMode = defaultPreparationMode;
      draftModeOverridden = false;
      elements.prepared.value = "";
      elements.smartTaskContext.value = "";
    } else if (!currentOriginalText && elements.original.value && !draftModeOverridden) {
      draftPreparationMode = defaultPreparationMode;
    }
    if (originalChanged) markMissedRepairStale("This review is stale because Original changed.");
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

  function applyDraftPreparationMode(nextMode) {
    draftPreparationMode = nextMode;
    elements.draftPreparationMode.value = nextMode;
    draftModeOverridden = true;
    renderCorrectionMode();
    if (manualPreparationProtected()) {
      schedulePublication();
      return;
    }
    draftRevision += 1;
    invalidateSmartRepairReview();
    elements.prepared.value = "";
    elements.prepared.dataset.repairCount = "0";
    originalOutgoingOverride = false;
    if (draftPreparationMode === "off") {
      window.clearTimeout(cleanupTimer);
      abortActiveRequest();
      setCleanupError(null);
      setStatus("disabled");
      publishNow();
    } else {
      runCleanup();
    }
  }

  elements.draftPreparationMode.addEventListener("change", () => {
    applyDraftPreparationMode(elements.draftPreparationMode.value);
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
    if (effectiveCorrectionMode() === "smart" && elements.original.value) {
      scheduleCleanup();
    }
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
  elements.correctPrepared.addEventListener("click", openPreparedCorrection);
  elements.intendedPrepared.addEventListener("input", renderPreparedCorrection);
  elements.cancelPreparedCorrection.addEventListener("click", cancelPreparedCorrection);
  elements.preparedCorrectionDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    cancelPreparedCorrection();
  });
  elements.preparedCorrectionForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (preparedCorrectionRevision === null
      || preparedCorrectionRevision !== draftRevision
      || !elements.intendedPrepared.value.trim()) return;
    const reviewRequested = elements.reviewPersonalCorrections.checked;
    const startingText = preparedCorrectionStartingText;
    elements.prepared.value = elements.intendedPrepared.value;
    confirmedPreparedRevision = draftRevision;
    originalOutgoingOverride = false;
    markMissedRepairStale("Prepared was replaced with user-confirmed wording.");
    invalidateSmartRepairReview();
    setCleanupError(null);
    clearCleanupAttempts();
    setStatus("prepared");
    cancelPreparedCorrection();
    publishNow();
    if (reviewRequested) {
      missedRepairBinding = {
        preEdit: startingText,
        postEdit: elements.prepared.value,
        postRevision: draftRevision,
      };
      openMissedRepairReview();
    }
  });
  elements.retryCleanup.addEventListener("click", () => {
    if (failedCorrectionMode === "smart") applyDraftPreparationMode("conservative");
    else runCleanup();
  });
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
  elements.missedRepairApproval.addEventListener("click", saveMissedRepairReview);
  elements.closeMissedRepair.addEventListener("click", dismissMissedRepairReview);
  elements.dismissMissedRepair.addEventListener("click", dismissMissedRepairReview);
  elements.missedRepairDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    dismissMissedRepairReview();
  });
  elements.missedRepairDialog.addEventListener("click", (event) => {
    if (event.target === elements.missedRepairDialog) dismissMissedRepairReview();
  });
  [elements.observedSentence, elements.intendedSentence].forEach(
    (field) => field.addEventListener("input", updateSentenceLimitState),
  );
  elements.retainObservedSentence.addEventListener(
    "click", () => toggleMissedRepairSentence(elements.retainObservedSentence),
  );
  elements.retainIntendedSentence.addEventListener(
    "click", () => toggleMissedRepairSentence(elements.retainIntendedSentence),
  );
  elements.missedRepairContext.addEventListener("input", updateMissedRepairApprovalState);
  elements.clear.addEventListener("click", () => {
    window.clearTimeout(cleanupTimer);
    window.clearTimeout(publicationTimer);
    abortActiveRequest();
    if (preparedCorrectionRevision !== null) cancelPreparedCorrection();
    confirmedPreparedRevision = null;
    markMissedRepairStale("This review is stale because the draft was cleared.");
    replaceAllPending = false;
    originalOutgoingOverride = false;
    draftPreparationMode = defaultPreparationMode;
    draftRevision += 1;
    draftModeOverridden = false;
    currentOriginalText = "";
    setExplicitSmartState("hidden");
    invalidateSmartRepairReview();
    elements.original.value = "";
    elements.prepared.value = "";
    elements.prepared.dataset.repairCount = "0";
    elements.smartTaskContext.value = "";
    setCleanupError(null);
    clearCleanupAttempts();
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

  function personalCorrectionAliases(value) {
    return value.split(/\r?\n/).map((alias) => alias.trim()).filter(Boolean);
  }

  function personalCorrectionField(labelText, value, maximum, multiline = false) {
    const label = document.createElement("label");
    const field = document.createElement(multiline ? "textarea" : "input");
    label.append(document.createTextNode(labelText));
    field.value = value || "";
    field.maxLength = maximum;
    field.required = labelText !== "Applicability context";
    label.append(field);
    return { label, field };
  }

  function renderPersonalCorrections() {
    const { enabled, entries } = personalCorrectionProfile;
    elements.personalCorrectionsToggle.textContent = enabled
      ? "Disable Personal corrections"
      : "Enable Personal corrections";
    elements.personalCorrectionForm.hidden = !enabled;
    elements.personalCorrectionsState.textContent = enabled
      ? "Enabled for this local profile."
      : entries.length
        ? "Disabled globally. Saved corrections are retained."
        : "Disabled. Nothing is saved until you explicitly enable it.";
    elements.personalCorrectionsEmpty.hidden = entries.length > 0;
    elements.personalCorrectionList.textContent = "";
    entries.forEach((entry) => {
      const form = document.createElement("form");
      const header = document.createElement("header");
      const title = document.createElement("h4");
      const enabledLabel = document.createElement("label");
      const enabledInput = document.createElement("input");
      const fields = document.createElement("div");
      const term = personalCorrectionField("Intended term", entry.intended_term, 200);
      const aliases = personalCorrectionField(
        "Misheard aliases",
        entry.aliases.map((alias) => alias.observed_alias).join("\n"),
        1000,
        true,
      );
      const context = personalCorrectionField(
        "Applicability context", entry.applicability_context || "", 500, true,
      );
      const footer = document.createElement("footer");
      const save = document.createElement("button");
      const state = document.createElement("span");
      form.className = `personal-correction-card${entry.enabled ? "" : " is-disabled"}`;
      title.textContent = entry.intended_term;
      enabledLabel.className = "personal-correction-enabled";
      enabledInput.type = "checkbox";
      enabledInput.checked = entry.enabled;
      enabledLabel.append(enabledInput, document.createTextNode("Enabled"));
      header.append(title, enabledLabel);
      fields.className = "personal-correction-fields";
      fields.append(term.label, aliases.label, context.label);
      entry.aliases.filter((alias) => alias.ambiguous).forEach(() => {
        const warning = document.createElement("span");
        warning.className = "personal-correction-alias-warning";
        warning.textContent = "This alias also appears under another intended term.";
        aliases.label.append(warning);
      });
      save.type = "submit";
      save.className = "button";
      save.textContent = "Save changes";
      state.textContent = `Revision ${entry.revision}`;
      state.setAttribute("role", "status");
      footer.append(save, state);
      form.append(header, fields, footer);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const aliasValues = personalCorrectionAliases(aliases.field.value);
        if (!term.field.value.trim() || aliasValues.length === 0) {
          state.textContent = "An intended term and at least one alias are required.";
          return;
        }
        save.disabled = true;
        state.textContent = "Saving…";
        try {
          const response = await fetch(`/api/personal-corrections/entries/${entry.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              expected_revision: entry.revision,
              intended_term: term.field.value,
              aliases: aliasValues,
              applicability_context: context.field.value || null,
              enabled: enabledInput.checked,
            }),
          });
          if (!response.ok) throw await safeHttpError(response, "Personal correction save");
          await loadPersonalCorrections();
        } catch (error) {
          state.textContent = error.code === "stale_personal_correction_revision"
            ? "Changed elsewhere. Reloading…"
            : "Save failed. Review the fields and retry.";
          if (error.code === "stale_personal_correction_revision") await loadPersonalCorrections();
        } finally {
          save.disabled = false;
        }
      });
      elements.personalCorrectionList.append(form);
    });
  }

  async function loadPersonalCorrections() {
    const response = await fetch("/api/personal-corrections");
    if (!response.ok) throw await safeHttpError(response, "Personal corrections loading");
    const profile = await readJson(response, "Personal corrections loading");
    if (!profile || typeof profile.enabled !== "boolean" || !Array.isArray(profile.entries)) {
      throw malformedResponseError("Personal corrections loading", response.status);
    }
    personalCorrectionProfile = profile;
    renderPersonalCorrections();
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
    const workspaceVisible = !settingsVisible;
    elements.workspace.hidden = !workspaceVisible;
    elements.workspaceControls.hidden = !workspaceVisible;
    elements.workspaceOutgoing.hidden = !workspaceVisible;
    elements.settingsManager.hidden = !settingsVisible;
    elements.navWorkspace.classList.toggle("is-active", workspaceVisible);
    elements.navSettings.classList.toggle("is-active", settingsVisible);
    elements.navWorkspace.toggleAttribute("aria-current", workspaceVisible);
    elements.navSettings.toggleAttribute("aria-current", settingsVisible);
    if (!settingsVisible && elements.targetDialog.open) elements.targetDialog.close();
    if (settingsVisible) {
      loadPersonalCorrections().catch(() => {
        elements.personalCorrectionsState.textContent = "Personal corrections could not be loaded.";
      });
    }
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
  }

  elements.navWorkspace.addEventListener("click", () => {
    if (!confirmDiscardTargetDraft()) return;
    targetDirty = false;
    showDestination("workspace");
  });
  elements.navSettings.addEventListener("click", () => showDestination("settings"));
  elements.personalCorrectionsToggle.addEventListener("click", async () => {
    elements.personalCorrectionsToggle.disabled = true;
    elements.personalCorrectionsState.textContent = "Saving…";
    try {
      const response = await fetch("/api/personal-corrections/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !personalCorrectionProfile.enabled }),
      });
      if (!response.ok) throw await safeHttpError(response, "Personal corrections profile");
      personalCorrectionProfile = await readJson(response, "Personal corrections profile");
      renderPersonalCorrections();
    } catch (_error) {
      elements.personalCorrectionsState.textContent = "Profile change failed. Retry when ready.";
    } finally {
      elements.personalCorrectionsToggle.disabled = false;
    }
  });
  elements.personalCorrectionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const aliasValues = personalCorrectionAliases(elements.personalCorrectionAliases.value);
    if (!elements.personalCorrectionTerm.value.trim() || aliasValues.length === 0) return;
    const submit = elements.personalCorrectionForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    elements.personalCorrectionsState.textContent = "Adding correction…";
    try {
      const response = await fetch("/api/personal-corrections/entries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          intended_term: elements.personalCorrectionTerm.value,
          aliases: aliasValues,
          applicability_context: elements.personalCorrectionContext.value || null,
        }),
      });
      if (!response.ok) throw await safeHttpError(response, "Personal correction create");
      elements.personalCorrectionForm.reset();
      await loadPersonalCorrections();
    } catch (_error) {
      elements.personalCorrectionsState.textContent = "Correction was not added. Review the fields and retry.";
    } finally {
      submit.disabled = false;
    }
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
      const [configResponse] = await Promise.all([
        fetch("/api/config"),
        clearPublishedState(),
      ]);
      if (!configResponse.ok) throw await safeHttpError(configResponse, "Workspace configuration");
      const config = await readJson(configResponse, "Workspace configuration");

      defaultPreparationMode = ["off", "conservative", "smart"].includes(config.preparation_default)
        ? config.preparation_default
        : "conservative";
      activePromptVersionId = Number.isInteger(config.active_prompt_version_id)
        ? config.active_prompt_version_id
        : null;
      missedRepairBinding = null;
      draftPreparationMode = defaultPreparationMode;
      draftModeOverridden = false;
      currentOriginalText = elements.original.value;
      elements.modeSaveState.textContent = `${titleCaseState(defaultPreparationMode)} is the saved default.`;
      renderCorrectionMode();
      renderCleanupConfiguration(config.cleanup_configuration);

      elements.prepared.value = "";
      invalidateSmartRepairReview();
      originalOutgoingOverride = false;
      setStatus(draftPreparationMode === "off" ? "disabled" : "unchanged");
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
