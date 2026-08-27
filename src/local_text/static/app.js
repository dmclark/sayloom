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
    workspace: document.querySelector(".workspace"),
    workspaceResizer: document.querySelector("#workspace-resizer"),
    activePromptSelector: document.querySelector("#active-prompt-selector"),
    errorDialog: document.querySelector("#error-details-dialog"),
    errorLedger: document.querySelector("#error-details-ledger"),
    closeErrorDialog: document.querySelector("#close-error-details"),
    copyError: document.querySelector("#copy-error-details"),
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
  const errors = { cleanup: null, publication: null };

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
    setCleanupError(null);
    if (elements.original.value) scheduleCleanup();
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
      elements.modelLabel.textContent = config.cleanup_available
        ? `Gemini · ${config.cleanup_model}`
        : "Gemini · configuration needed";

      elements.cleaned.value = "";
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
