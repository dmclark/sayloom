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
    cancelCleanup: document.querySelector("#cancel-cleanup"),
    clear: document.querySelector("#clear-text"),
    status: document.querySelector("#cleanup-status"),
    statusText: document.querySelector("#cleanup-status-text"),
    originalCount: document.querySelector("#original-count"),
    cleanedCount: document.querySelector("#cleaned-count"),
    outgoingKind: document.querySelector("#outgoing-kind"),
    publication: document.querySelector("#publication-state"),
    modelLabel: document.querySelector("#model-label"),
    workspace: document.querySelector(".workspace"),
    workspaceResizer: document.querySelector("#workspace-resizer"),
    activePromptSelector: document.querySelector("#active-prompt-selector"),
    canvasNav: document.querySelector("#show-canvas"),
    promptsNav: document.querySelector("#show-prompts"),
    promptManager: document.querySelector("#prompt-manager"),
    closePromptManager: document.querySelector("#close-prompt-manager"),
    promptHistory: document.querySelector("#prompt-history"),
    promptVersionMeta: document.querySelector("#prompt-version-meta"),
    promptTitle: document.querySelector("#prompt-title"),
    promptText: document.querySelector("#prompt-text"),
    promptSaveStatus: document.querySelector("#prompt-save-status"),
    savePrompt: document.querySelector("#save-prompt"),
    activatePrompt: document.querySelector("#activate-prompt"),
  };

  const statusLabels = {
    unchanged: "Unchanged",
    waiting: "Waiting",
    cleaning: "Cleaning…",
    cleaned: "Cleaned",
    disabled: "Disabled · raw",
    timeout: "Timeout · raw",
    error: "Error · raw",
    stale: "Cancelled · raw",
    edited: "Edited",
  };

  let status = "unchanged";
  let cleanupTimer = null;
  let publicationTimer = null;
  let publicationChain = Promise.resolve();
  let publicationSequence = 0;
  let activeRequest = null;
  let requestSequence = 0;
  let cleanedWasEdited = false;
  let syntheticPastePending = false;
  let syntheticPasteTimer = null;
  let returnSelectionPending = false;
  let promptVersions = [];
  let activePromptVersionId = null;
  let activeResizePointer = null;

  function setStatus(nextStatus) {
    status = nextStatus;
    elements.status.dataset.state = nextStatus;
    elements.statusText.textContent = statusLabels[nextStatus] || nextStatus;
  }

  function setActiveSection(activeButton) {
    [elements.canvasNav, elements.promptsNav].forEach((button) => {
      const isActive = button === activeButton;
      button.classList.toggle("is-active", isActive);
      if (isActive) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
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

  function selectedOutgoingState() {
    const rawText = elements.original.value;
    const cleanedText = elements.cleaned.value;
    let outgoingText = elements.cleanupEnabled.checked ? cleanedText : rawText;
    let outgoingKind = elements.cleanupEnabled.checked
      ? (cleanedWasEdited ? "edited" : "cleaned")
      : "raw";

    if (!outgoingText && rawText) {
      outgoingText = rawText;
      outgoingKind = "raw";
    }
    if (!outgoingText) {
      outgoingKind = "empty";
    } else if (outgoingText === rawText && !cleanedWasEdited) {
      outgoingKind = "raw";
    }

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
    const outgoing = selectedOutgoingState();
    const labels = {
      empty: "Nothing yet",
      raw: "Original · raw fail-open",
      cleaned: "Cleaned result",
      edited: "Your edited cleanup",
    };
    elements.outgoingKind.textContent = labels[outgoing.outgoing_kind];
  }

  function setPublicationState(nextState, label) {
    elements.publication.dataset.state = nextState;
    elements.publication.lastElementChild.textContent = label;
  }

  function publishNow() {
    window.clearTimeout(publicationTimer);
    publicationTimer = null;
    renderCountsAndSelection();
    const snapshot = selectedOutgoingState();
    const sequence = ++publicationSequence;
    publicationChain = publicationChain.then(async () => {
      try {
        const response = await fetch("/api/outgoing-state", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(snapshot),
        });
        if (!response.ok) throw new Error(`Publication failed with ${response.status}`);
        if (sequence === publicationSequence) setPublicationState("ready", "State published");
      } catch (_error) {
        if (sequence === publicationSequence) setPublicationState("error", "State unavailable");
      }
    });
    return publicationChain;
  }

  function clearPublishedState() {
    const sequence = ++publicationSequence;
    publicationChain = publicationChain.then(async () => {
      try {
        const response = await fetch("/api/outgoing-state", { method: "DELETE" });
        if (!response.ok) throw new Error(`Clear failed with ${response.status}`);
        if (sequence === publicationSequence) setPublicationState("ready", "State cleared");
      } catch (_error) {
        if (sequence === publicationSequence) setPublicationState("error", "Clear not published");
      }
    });
    return publicationChain;
  }

  function schedulePublication() {
    renderCountsAndSelection();
    setPublicationState("pending", "Publishing…");
    window.clearTimeout(publicationTimer);
    publicationTimer = window.setTimeout(publishNow, PUBLICATION_DEBOUNCE_MS);
  }

  function abortActiveRequest({ markStale = true } = {}) {
    if (!activeRequest) return false;
    activeRequest.abort();
    activeRequest = null;
    requestSequence += 1;
    elements.cancelCleanup.disabled = true;
    if (markStale) {
      elements.cleaned.value = elements.original.value;
      cleanedWasEdited = false;
      setStatus("stale");
      schedulePublication();
    }
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
    abortActiveRequest({ markStale: false });

    const rawText = elements.original.value;
    if (!rawText.trim()) {
      elements.cleaned.value = rawText;
      cleanedWasEdited = false;
      setStatus("unchanged");
      schedulePublication();
      return;
    }
    if (!elements.cleanupEnabled.checked) {
      elements.cleaned.value = rawText;
      cleanedWasEdited = false;
      setStatus("disabled");
      schedulePublication();
      return;
    }

    elements.cleaned.value = "";
    cleanedWasEdited = false;
    const sequence = ++requestSequence;
    const controller = new AbortController();
    const selection = {
      wasFocused: document.activeElement === elements.original,
      start: elements.original.selectionStart,
      end: elements.original.selectionEnd,
    };
    activeRequest = controller;
    elements.cancelCleanup.disabled = false;
    setStatus("cleaning");
    schedulePublication();

    try {
      const response = await fetch("/api/cleanup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_text: rawText, enabled: true }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Cleanup failed with ${response.status}`);
      const result = await response.json();
      if (sequence !== requestSequence || rawText !== elements.original.value) return;

      elements.cleaned.value = typeof result.cleaned_text === "string"
        ? result.cleaned_text
        : rawText;
      cleanedWasEdited = false;
      const statusMap = {
        cleaned: "cleaned",
        unchanged: "unchanged",
        empty_input: "unchanged",
        disabled: "disabled",
        timeout: "timeout",
        provider_error: "error",
      };
      setStatus(statusMap[result.status] || "error");
      restoreOriginalSelection(selection);
    } catch (error) {
      if (sequence !== requestSequence) return;
      elements.cleaned.value = rawText;
      cleanedWasEdited = false;
      setStatus(error.name === "AbortError" ? "stale" : "error");
      restoreOriginalSelection(selection);
    } finally {
      if (sequence === requestSequence) {
        activeRequest = null;
        elements.cancelCleanup.disabled = true;
        schedulePublication();
      }
    }
  }

  function scheduleCleanup() {
    window.clearTimeout(cleanupTimer);
    if (!elements.cleanupEnabled.checked) {
      elements.cleaned.value = elements.original.value;
      cleanedWasEdited = false;
      setStatus("disabled");
      schedulePublication();
      return;
    }
    abortActiveRequest();
    elements.cleaned.value = "";
    cleanedWasEdited = false;
    setStatus("waiting");
    schedulePublication();
    cleanupTimer = window.setTimeout(runCleanup, CLEANUP_DEBOUNCE_MS);
  }

  function handleOriginalInput(event) {
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
  elements.original.addEventListener("paste", (event) => {
    if (!event.isTrusted) {
      syntheticPastePending = true;
      window.clearTimeout(syntheticPasteTimer);
      syntheticPasteTimer = window.setTimeout(() => {
        syntheticPastePending = false;
      }, 1_000);
    }
  });
  elements.original.addEventListener("input", handleOriginalInput);

  elements.cleaned.addEventListener("input", () => {
    cleanedWasEdited = true;
    setStatus("edited");
    schedulePublication();
  });

  elements.cleanupEnabled.addEventListener("change", () => {
    if (!elements.cleanupEnabled.checked) {
      window.clearTimeout(cleanupTimer);
      abortActiveRequest({ markStale: false });
      elements.cleaned.value = elements.original.value;
      cleanedWasEdited = false;
      setStatus("disabled");
      publishNow();
    } else {
      scheduleCleanup();
    }
  });

  elements.runCleanup.addEventListener("click", runCleanup);
  elements.cancelCleanup.addEventListener("click", () => abortActiveRequest());
  elements.clear.addEventListener("click", () => {
    window.clearTimeout(cleanupTimer);
    window.clearTimeout(publicationTimer);
    abortActiveRequest({ markStale: false });
    elements.original.value = "";
    elements.cleaned.value = "";
    cleanedWasEdited = false;
    setStatus("unchanged");
    renderCountsAndSelection();
    clearPublishedState();
    elements.original.focus();
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

  function selectedPrompt() {
    const selectedId = Number(elements.promptHistory.value);
    return promptVersions.find((prompt) => prompt.id === selectedId) || null;
  }

  function renderSelectedPrompt() {
    const prompt = selectedPrompt();
    if (!prompt) return;
    elements.promptTitle.value = prompt.title;
    elements.promptText.value = prompt.system_text;
    elements.promptVersionMeta.textContent = [
      `Version ${prompt.version}`,
      prompt.source,
      new Date(prompt.created_at).toLocaleString(),
    ].join(" · ");
    elements.activatePrompt.disabled = prompt.id === activePromptVersionId;
  }

  async function loadPromptHistory(selectId = null) {
    const response = await fetch("/api/prompts");
    if (!response.ok) throw new Error(`Prompt history failed with ${response.status}`);
    const result = await response.json();
    promptVersions = Array.isArray(result.versions) ? result.versions : [];
    activePromptVersionId = result.active_prompt_version_id;
    elements.activePromptSelector.textContent = "";
    elements.promptHistory.textContent = "";
    promptVersions.forEach((prompt) => {
      const activeOption = document.createElement("option");
      activeOption.value = String(prompt.id);
      activeOption.textContent = `v${prompt.version} · ${prompt.title}`;
      elements.activePromptSelector.append(activeOption);

      const historyOption = document.createElement("option");
      historyOption.value = String(prompt.id);
      historyOption.textContent = `v${prompt.version} · ${prompt.title}${prompt.active ? " — active" : ""}`;
      elements.promptHistory.append(historyOption);
    });
    elements.activePromptSelector.value = String(activePromptVersionId ?? "");
    elements.promptHistory.value = String(selectId ?? activePromptVersionId ?? "");
    renderSelectedPrompt();
  }

  async function activatePromptVersion(prompt, successMessage) {
    const response = await fetch(`/api/prompts/${prompt.id}/activate`, { method: "POST" });
    if (!response.ok) throw new Error(`Activation failed with ${response.status}`);
    await loadPromptHistory(prompt.id);
    elements.promptSaveStatus.textContent = successMessage;
    if (elements.original.value) scheduleCleanup();
  }

  elements.canvasNav.addEventListener("click", () => {
    setActiveSection(elements.canvasNav);
    elements.original.focus();
  });
  elements.promptsNav.addEventListener("click", () => {
    elements.promptHistory.value = String(activePromptVersionId ?? "");
    renderSelectedPrompt();
    elements.promptSaveStatus.textContent = "Ready to create an immutable version.";
    setActiveSection(elements.promptsNav);
    elements.promptManager.showModal();
  });
  elements.closePromptManager.addEventListener("click", () => elements.promptManager.close());
  elements.promptManager.addEventListener("click", (event) => {
    if (event.target === elements.promptManager) elements.promptManager.close();
  });
  elements.promptManager.addEventListener("close", () => {
    setActiveSection(elements.canvasNav);
  });
  elements.activePromptSelector.addEventListener("change", async () => {
    const prompt = promptVersions.find(
      (candidate) => candidate.id === Number(elements.activePromptSelector.value),
    );
    if (!prompt) return;
    elements.activePromptSelector.disabled = true;
    setPublicationState("pending", "Changing prompt…");
    try {
      await activatePromptVersion(prompt, `Version ${prompt.version} is active.`);
      setPublicationState("ready", `Prompt v${prompt.version} active`);
    } catch (_error) {
      elements.activePromptSelector.value = String(activePromptVersionId ?? "");
      setPublicationState("error", "Prompt unchanged");
    } finally {
      elements.activePromptSelector.disabled = false;
    }
  });
  elements.promptHistory.addEventListener("change", renderSelectedPrompt);
  elements.activatePrompt.addEventListener("click", async () => {
    const prompt = selectedPrompt();
    if (!prompt) return;
    elements.activatePrompt.disabled = true;
    elements.promptSaveStatus.textContent = "Activating selected version…";
    try {
      await activatePromptVersion(prompt, `Version ${prompt.version} is active.`);
    } catch (_error) {
      elements.activatePrompt.disabled = false;
      elements.promptSaveStatus.textContent = "Could not activate that version.";
    }
  });
  elements.savePrompt.addEventListener("click", async () => {
    const title = elements.promptTitle.value.trim();
    const systemText = elements.promptText.value.trim();
    if (!title || !systemText) {
      elements.promptSaveStatus.textContent = "A title and cleanup instruction are required.";
      return;
    }
    elements.savePrompt.disabled = true;
    elements.promptSaveStatus.textContent = "Saving immutable version…";
    try {
      const response = await fetch("/api/prompts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, system_text: systemText, activate: true }),
      });
      if (!response.ok) throw new Error(`Save failed with ${response.status}`);
      const prompt = await response.json();
      await loadPromptHistory(prompt.id);
      elements.promptSaveStatus.textContent = `Version ${prompt.version} saved and active.`;
      if (elements.original.value) scheduleCleanup();
    } catch (_error) {
      elements.promptSaveStatus.textContent = "Could not save the new version.";
    } finally {
      elements.savePrompt.disabled = false;
    }
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
      const [configResponse, stateResponse] = await Promise.all([
        fetch("/api/config"),
        fetch("/api/outgoing-state"),
      ]);
      const config = configResponse.ok ? await configResponse.json() : {};
      const published = stateResponse.ok ? await stateResponse.json() : null;

      elements.cleanupEnabled.checked = published?.cleanup_enabled
        ?? config.cleanup_enabled_by_default
        ?? true;
      elements.modelLabel.textContent = config.cleanup_available
        ? `Gemini · ${config.cleanup_model}`
        : "Gemini · configuration needed";

      if (published?.revision > 0) {
        elements.original.value = published.raw_text || "";
        elements.cleaned.value = published.cleaned_text || "";
        cleanedWasEdited = published.outgoing_kind === "edited";
        setStatus(published.status || "unchanged");
      } else if (!elements.cleanupEnabled.checked) {
        setStatus("disabled");
      }
      renderCountsAndSelection();
      setWorkspaceShare(DEFAULT_ORIGINAL_SHARE);
      await loadPromptHistory();
      publishNow();
    } catch (_error) {
      setPublicationState("error", "State unavailable");
    }
  }

  initialize();
})();
