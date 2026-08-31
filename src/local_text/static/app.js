(() => {
  "use strict";

  const CLEANUP_DEBOUNCE_MS = 700;
  const PUBLICATION_DEBOUNCE_MS = 150;
  const DEFAULT_ORIGINAL_SHARE = 65;
  const MINIMUM_ORIGINAL_SHARE = 45;
  const MAXIMUM_ORIGINAL_SHARE = 80;

  const elements = {
    original: document.querySelector("#original-text"),
    cleaned: document.querySelector("#cleaned-text"),
    cleanupEnabled: document.querySelector("#cleanup-enabled"),
    runCleanup: document.querySelector("#run-cleanup"),
    clear: document.querySelector("#clear-text"),
    toggleOriginal: document.querySelector("#toggle-original"),
    status: document.querySelector("#cleanup-status"),
    statusText: document.querySelector("#cleanup-status-text"),
    originalCount: document.querySelector("#original-count"),
    cleanedCount: document.querySelector("#cleaned-count"),
    outgoingKind: document.querySelector("#outgoing-kind"),
    selectCleaned: document.querySelector("#select-cleaned"),
    selectOriginal: document.querySelector("#select-original"),
    publication: document.querySelector("#publication-state"),
    modelLabel: document.querySelector("#model-label"),
    cleanupDisclosure: document.querySelector("#cleanup-disclosure"),
    cleanupDisclosureSummary: document.querySelector("#cleanup-disclosure-summary"),
    cleanupRouteList: document.querySelector("#cleanup-route-list"),
    cleanupProcessingDisclosure: document.querySelector("#cleanup-processing-disclosure"),
    cleanupFallbackDisclosure: document.querySelector("#cleanup-fallback-disclosure"),
    cleanupCorpusDisclosure: document.querySelector("#cleanup-corpus-disclosure"),
    cleanupValidationDetail: document.querySelector("#cleanup-validation-detail"),
    workspace: document.querySelector(".workspace"),
    workspaceResizer: document.querySelector("#workspace-resizer"),
    activePromptSelector: document.querySelector("#active-prompt-selector"),
    errorDialog: document.querySelector("#error-details-dialog"),
    errorLedger: document.querySelector("#error-details-ledger"),
    closeErrorDialog: document.querySelector("#close-error-details"),
    copyError: document.querySelector("#copy-error-details"),
    workspaceControls: document.querySelector("#workspace-controls"),
    workspaceOutgoing: document.querySelector("#workspace-outgoing"),
    navWorkspace: document.querySelector("#nav-workspace"),
    navTargets: document.querySelector("#nav-targets"),
    navEvaluation: document.querySelector("#nav-evaluation"),
    targetsManager: document.querySelector("#targets-manager"),
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

  const statusLabels = {
    unchanged: "Unchanged",
    waiting: "Waiting",
    cleaning: "Cleaning…",
    cleaned: "Cleaned",
    disabled: "Disabled · Original",
    timeout: "Timeout · Original",
    error: "Error · Original",
  };

  let status = "unchanged";
  let cleanupTimer = null;
  let publicationTimer = null;
  let publicationChain = Promise.resolve();
  let publicationSequence = 0;
  let activeRequest = null;
  let requestSequence = 0;
  let replaceAllPending = false;
  let syntheticPastePending = false;
  let syntheticPasteTimer = null;
  let returnSelectionPending = false;
  let promptVersions = [];
  let selectedPromptVersionId = null;
  let activeResizePointer = null;
  let originalOutgoingOverride = false;
  let targetRecords = [];
  let selectedTargetId = null;
  let targetDirty = false;
  let targetDraftIsNew = false;
  let targetLocalError = null;
  let evaluationAvailable = false;
  let currentEvaluation = null;
  let evaluationCases = [];
  let reviewedEvaluationCase = null;
  let evaluationExportPreview = null;
  const errors = { cleanup: null, publication: null };

  const targetPresets = {
    amp: ["Amp", "Amp", "com.google.Chrome.app.bpgpkfmeagdpdcenbogglipmfkalmple", "synthetic_paste"],
    iterm: ["iTerm", "iTerm", "com.googlecode.iterm2", "iterm_write"],
    supacode: ["Supacode", "Supacode", "app.supabit.supacode", "synthetic_paste"],
    "vs-code": ["VS Code", "Visual Studio Code", "com.microsoft.VSCode", "synthetic_paste"],
  };

  function setStatus(nextStatus) {
    status = nextStatus;
    elements.status.dataset.state = nextStatus;
    elements.statusText.textContent = statusLabels[nextStatus] || nextStatus;
  }

  function setOriginalCollapsed(collapsed) {
    const selectionStart = elements.original.selectionStart;
    const selectionEnd = elements.original.selectionEnd;
    elements.workspace.classList.toggle("is-original-collapsed", collapsed);
    elements.toggleOriginal.textContent = collapsed ? "Show input" : "Hide input";
    elements.toggleOriginal.setAttribute("aria-expanded", String(!collapsed));
    window.requestAnimationFrame(() => {
      elements.original.focus({ preventScroll: true });
      elements.original.setSelectionRange(selectionStart, selectionEnd);
    });
  }

  function setWorkspaceShare(value) {
    const originalShare = Math.min(
      MAXIMUM_ORIGINAL_SHARE,
      Math.max(MINIMUM_ORIGINAL_SHARE, Math.round(value)),
    );
    elements.workspace.style.setProperty("--original-share", `${originalShare}fr`);
    elements.workspace.style.setProperty("--cleaned-share", `${100 - originalShare}fr`);
    elements.workspaceResizer.setAttribute("aria-valuenow", String(originalShare));
    elements.workspaceResizer.setAttribute(
      "aria-valuetext",
      `Original ${originalShare} percent, Cleaned ${100 - originalShare} percent`,
    );
  }

  function resizeFromPointer(event) {
    const bounds = elements.workspace.getBoundingClientRect();
    setWorkspaceShare(((event.clientY - bounds.top) / bounds.height) * 100);
  }

  function cleanedIsCurrent() {
    return elements.cleanupEnabled.checked
      && Boolean(elements.original.value)
      && (status === "cleaned" || status === "unchanged")
      && Boolean(elements.cleaned.value);
  }

  function fallbackLabel() {
    if (!elements.original.value) return "Nothing yet";
    if (originalOutgoingOverride) return "Original selected for this draft";
    if (cleanedIsCurrent()) return status === "unchanged"
      ? "Cleaned selected · result unchanged"
      : "Cleaned selected · current result";
    return {
      waiting: "Original fallback · replacement Cleaned pending",
      cleaning: "Original fallback · cleanup in progress",
      disabled: "Original fallback · cleanup disabled",
      timeout: "Original fallback · cleanup timed out",
      error: "Original fallback · cleanup unavailable",
    }[status] || "Original fallback · Cleaned unavailable";
  }

  function selectedOutgoingState() {
    const rawText = elements.original.value;
    const cleanedText = elements.cleaned.value;
    const useCleaned = !originalOutgoingOverride && cleanedIsCurrent();
    const outgoingText = useCleaned ? cleanedText : rawText;
    const outgoingKind = outgoingText ? (useCleaned ? "cleaned" : "raw") : "empty";

    return {
      cleanup_enabled: elements.cleanupEnabled.checked,
      raw_text: rawText,
      cleaned_text: cleanedText,
      outgoing_text: outgoingText,
      outgoing_kind: outgoingKind,
      status,
    };
  }

  function renderCountsAndSelection() {
    elements.originalCount.textContent = String(elements.original.value.length);
    elements.cleanedCount.textContent = String(elements.cleaned.value.length);
    const useCleaned = selectedOutgoingState().outgoing_kind === "cleaned";
    elements.selectCleaned.disabled = !cleanedIsCurrent();
    elements.selectCleaned.setAttribute("aria-pressed", String(useCleaned));
    elements.selectOriginal.setAttribute("aria-pressed", String(!useCleaned));
    elements.outgoingKind.textContent = fallbackLabel();
  }

  function setPublicationState(nextState, label) {
    elements.publication.dataset.state = nextState;
    elements.publication.lastElementChild.textContent = label;
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
    return kind === "cleanup" ? elements.status : elements.publication;
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
    trigger.disabled = error === null;
    trigger.classList.toggle("has-error-details", error !== null);
    if (error === null) {
      trigger.removeAttribute("aria-label");
      if (elements.errorDialog.open && elements.errorDialog.dataset.kind === kind) {
        elements.errorDialog.close();
      }
      return;
    }
    const statusText = trigger.lastElementChild.textContent;
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

  async function runCleanup() {
    window.clearTimeout(cleanupTimer);
    cleanupTimer = null;
    abortActiveRequest();
    setCleanupError(null);
    invalidateEvaluationCapture();

    const rawText = elements.original.value;
    if (!rawText.trim()) {
      elements.cleaned.value = rawText;
      setStatus("unchanged");
      schedulePublication();
      return;
    }
    if (!elements.cleanupEnabled.checked) {
      elements.cleaned.value = rawText;
      setStatus("disabled");
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
          raw_text: rawText,
          enabled: true,
          prompt_version_id: selectedPromptVersionId,
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const error = await safeHttpError(response, "Cleanup");
        if (sequence !== requestSequence || rawText !== elements.original.value) return;
        elements.cleaned.value = rawText;
        setStatus("error");
        setCleanupError(error);
        restoreOriginalSelection(selection);
        return;
      }
      const result = await readJson(response, "Cleanup");
      if (sequence !== requestSequence || rawText !== elements.original.value) return;
      if (
        !result || typeof result.cleaned_text !== "string"
        || !["cleaned", "unchanged", "empty_input", "disabled", "timeout", "provider_error"].includes(result.status)
      ) {
        elements.cleaned.value = rawText;
        setStatus("error");
        setCleanupError(malformedResponseError("Cleanup", response.status));
        restoreOriginalSelection(selection);
        return;
      }

      elements.cleaned.value = result.cleaned_text;
      const statusMap = {
        cleaned: "cleaned",
        unchanged: "unchanged",
        empty_input: "unchanged",
        disabled: "disabled",
        timeout: "timeout",
        provider_error: "error",
      };
      setStatus(statusMap[result.status]);
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
        && ["cleaned", "unchanged"].includes(result.status)
        && result.evaluation
        && typeof result.evaluation.capture_proof === "string"
        && Array.isArray(result.attempts)
      ) {
        currentEvaluation = {
          sourceText: rawText,
          providerOutput: result.cleaned_text,
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
      elements.cleaned.value = rawText;
      setStatus("error");
      if (error.name !== "AbortError") {
        setCleanupError(error?.code ? error : networkError("Cleanup"));
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
    setCleanupError(null);
    invalidateEvaluationCapture();
    if (!elements.cleanupEnabled.checked) {
      elements.cleaned.value = elements.original.value;
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
    if (replaceAllPending) elements.cleaned.value = "";
    replaceAllPending = false;
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
    invalidateEvaluationCapture();
    if (!elements.cleanupEnabled.checked) {
      window.clearTimeout(cleanupTimer);
      abortActiveRequest();
      setCleanupError(null);
      elements.cleaned.value = elements.original.value;
      setStatus("disabled");
      publishNow();
    } else {
      scheduleCleanup();
    }
  });

  elements.toggleOriginal.addEventListener("click", () => {
    setOriginalCollapsed(!elements.workspace.classList.contains("is-original-collapsed"));
  });
  elements.runCleanup.addEventListener("click", runCleanup);
  elements.selectOriginal.addEventListener("click", () => {
    originalOutgoingOverride = true;
    publishNow();
  });
  elements.selectCleaned.addEventListener("click", () => {
    if (!cleanedIsCurrent()) return;
    originalOutgoingOverride = false;
    publishNow();
  });
  elements.clear.addEventListener("click", () => {
    window.clearTimeout(cleanupTimer);
    window.clearTimeout(publicationTimer);
    abortActiveRequest();
    replaceAllPending = false;
    originalOutgoingOverride = false;
    invalidateEvaluationCapture();
    elements.original.value = "";
    elements.cleaned.value = "";
    setCleanupError(null);
    setStatus("unchanged");
    renderCountsAndSelection();
    clearPublishedState();
    elements.original.focus();
  });

  elements.status.addEventListener("click", () => openErrorDetails("cleanup"));
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
  }
  elements.workspaceResizer.addEventListener("pointerup", finishResize);
  elements.workspaceResizer.addEventListener("pointercancel", finishResize);
  elements.workspaceResizer.addEventListener("dblclick", () => {
    setWorkspaceShare(DEFAULT_ORIGINAL_SHARE);
  });
  elements.workspaceResizer.addEventListener("keydown", (event) => {
    const currentShare = Number(elements.workspaceResizer.getAttribute("aria-valuenow"));
    const nextShare = {
      ArrowUp: currentShare - 2,
      ArrowDown: currentShare + 2,
      Home: MINIMUM_ORIGINAL_SHARE,
      End: MAXIMUM_ORIGINAL_SHARE,
    }[event.key];
    if (nextShare === undefined) return;
    event.preventDefault();
    setWorkspaceShare(nextShare);
  });

  async function loadPromptHistory() {
    const response = await fetch("/api/prompts");
    if (!response.ok) throw await safeHttpError(response, "Prompt version loading");
    const result = await readJson(response, "Prompt version loading");
    if (!result || !Array.isArray(result.versions)) {
      throw malformedResponseError("Prompt version loading", response.status);
    }
    promptVersions = result.versions;
    selectedPromptVersionId = result.active_prompt_version_id;
    elements.activePromptSelector.textContent = "";
    promptVersions.forEach((prompt) => {
      const option = document.createElement("option");
      option.value = String(prompt.id);
      option.textContent = `v${prompt.version} · ${prompt.title}`;
      elements.activePromptSelector.append(option);
    });
    elements.activePromptSelector.value = String(selectedPromptVersionId ?? "");
  }

  elements.activePromptSelector.addEventListener("change", () => {
    const prompt = promptVersions.find(
      (candidate) => candidate.id === Number(elements.activePromptSelector.value),
    );
    if (!prompt) return;
    selectedPromptVersionId = prompt.id;
    invalidateEvaluationCapture();
    setCleanupError(null);
    if (elements.original.value) scheduleCleanup();
  });

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
      || currentEvaluation.providerOutput !== elements.cleaned.value
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
    const targetsVisible = destination === "targets";
    const evaluationVisible = destination === "evaluation";
    const workspaceVisible = !targetsVisible && !evaluationVisible;
    elements.workspace.hidden = !workspaceVisible;
    elements.workspaceControls.hidden = !workspaceVisible;
    elements.workspaceOutgoing.hidden = !workspaceVisible;
    elements.targetsManager.hidden = !targetsVisible;
    elements.evaluationManager.hidden = !evaluationVisible;
    elements.navWorkspace.classList.toggle("is-active", workspaceVisible);
    elements.navTargets.classList.toggle("is-active", targetsVisible);
    elements.navEvaluation.classList.toggle("is-active", evaluationVisible);
    elements.navWorkspace.toggleAttribute("aria-current", workspaceVisible);
    elements.navTargets.toggleAttribute("aria-current", targetsVisible);
    elements.navEvaluation.toggleAttribute("aria-current", evaluationVisible);
    if (!targetsVisible && elements.targetDialog.open) elements.targetDialog.close();
    if (targetsVisible && targetRecords.length === 0) {
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
  elements.navTargets.addEventListener("click", () => showDestination("targets"));
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
      const [configResponse] = await Promise.all([
        fetch("/api/config"),
        clearPublishedState(),
      ]);
      if (!configResponse.ok) throw await safeHttpError(configResponse, "Workspace configuration");
      const config = await readJson(configResponse, "Workspace configuration");

      elements.cleanupEnabled.checked = config.cleanup_enabled_by_default ?? true;
      renderCleanupConfiguration(config.cleanup_configuration);
      evaluationAvailable = config.evaluation_configuration?.available === true;
      elements.evaluationStatus.textContent = evaluationAvailable
        ? "Evaluation storage is configured and current."
        : "Evaluation storage is not configured and current.";

      elements.cleaned.value = "";
      invalidateEvaluationCapture();
      originalOutgoingOverride = false;
      setStatus(elements.cleanupEnabled.checked ? "unchanged" : "disabled");
      renderCountsAndSelection();
      setWorkspaceShare(DEFAULT_ORIGINAL_SHARE);
      await loadPromptHistory();
      if (!elements.original.value) elements.original.focus({ preventScroll: true });
    } catch (error) {
      const safe = error?.code ? error : networkError("Workspace configuration");
      setStatus("error");
      setCleanupError(safe);
    }
  }

  initialize();
})();
