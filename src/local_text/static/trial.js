/* Trial state is deliberately not stored in browser storage. Only inclusion is durable. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const tints = ["#edf1f3", "#f3efe5", "#eeedf4", "#f3ece8"];
  let enabled = false, state = null, passage = null, excluded = false;
  let requested = false, edited = false, assigning = false, pendingEdit = null, undo = [], savedText = "";
  let changed = () => {};
  let queue = Promise.resolve();
  let cleanup = null, recordFailed = false;
  const message = (text) => {
    $("trial-message").textContent = text;
    $("trial-message").hidden = !text;
  };
  const feedbackMessage = (text) => {
    $("trial-feedback-status").textContent = text;
    $("trial-feedback-status").hidden = !text;
  };
  async function api(path = "", body, method = "POST") {
    const response = await fetch(`/api/trial${path}`, {
      method, headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string"
      ? result.detail : "Trial record could not be saved. Copying remains available.");
    return result;
  }
  const activeWeek = () => state?.status === "active" && Date.now() < state.ends_at * 1000;
  const capturing = () => enabled && !excluded && (Boolean(passage)
    || $("trial-include").checked);
  function record(action, extra = {}) {
    if (!passage?.id) return Promise.resolve();
    const id = passage.id;
    // Steps commit on explicit apply, blur, copy or leaving the passage; not keystrokes.
    queue = queue.then(() => api(`/passages/${id}/events`, { action, ...extra }))
      .catch((error) => { recordFailed = true; message(error.message); });
    return queue;
  }
  function flush(action = "edit", selection = {}) {
    if (!passage) return;
    const text = $("trial-passage").value;
    if (action !== "edit" || text !== savedText) {
      savedText = text;
      record(action, { final_text: text, ...selection });
    }
  }
  function renderState() {
    if (!enabled) return;
    const trialMode = capturing();
    document.querySelector(".prepared-panel").hidden = trialMode;
    document.querySelector(".workspace").classList.toggle("has-phrase-trial", trialMode);
    $("trial-panel").hidden = !trialMode;
    $("trial-waiting").hidden = Boolean(passage);
    $("trial-state").textContent = state
      ? `${state.status.replaceAll("_", " ")} · ${state.charged_usd !== undefined
        ? `$${state.charged_usd} / $5` : "US$5 combined ceiling"}${
        state.ends_at ? ` · ends ${new Date(state.ends_at * 1000).toLocaleString()}` : ""}` : "";
    $("trial-include").disabled = Boolean(passage) || assigning;
    $("trial-begin").disabled = !activeWeek() || !$("trial-include").checked
      || Boolean(passage) || assigning || !$("original-text").value.trim();
    $("trial-working").hidden = !passage;
    $("trial-undo").disabled = !undo.length;
    $("trial-switch").hidden = !passage || requested;
    $("trial-passage").readOnly = Boolean(cleanup);
    document.querySelectorAll("#trial-choices button, #trial-choices input, #trial-feedback select, #trial-feedback textarea, #trial-feedback button").forEach((control) => {
      control.disabled = Boolean(cleanup);
    });
    if (cleanup) $("trial-undo").disabled = $("trial-switch").disabled = true;
    else $("trial-switch").disabled = false;
    $("trial-clean").disabled = !passage || cleanup?.status === "cleaning";
    $("trial-clean").textContent = cleanup ? "Run Conservative cleanup again" : "Finish repairs & clean";
    $("trial-cleaned-review").hidden = !cleanup;
    $("trial-cleaned").value = cleanup?.text || "";
    $("trial-cleanup-state").textContent = cleanup?.status === "prepared"
      ? "Review this outgoing text, then use your existing Send to target command. Nothing is sent automatically."
      : cleanup?.status === "cleaning" ? "Conservative cleanup in progress. Target delivery is unavailable."
        : "Cleanup unavailable. Retry cleanup; no outgoing text is available. Your repairs are preserved above.";
    // Normal controls cannot silently trigger correction or change trial outgoing text.
    if (capturing()) for (const id of ["draft-preparation-mode", "run-cleanup", "select-original", "select-prepared"]) {
      $(id).disabled = true;
    }
    $("draft-preparation-mode").disabled = capturing();
    $("run-cleanup").disabled = capturing();
  }
  function highlights() {
    const mirror = $("trial-highlights");
    mirror.replaceChildren();
    let offset = 0;
    for (const [index, phrase] of (passage?.suggestions || []).entries()) {
      if (phrase.state === "unavailable") continue;
      mirror.append(document.createTextNode(passage.final_text.slice(offset, phrase.start)));
      const mark = document.createElement("mark");
      mark.style.background = tints[index % tints.length];
      mark.textContent = passage.final_text.slice(phrase.start, phrase.end);
      mirror.append(mark); offset = phrase.end;
    }
    mirror.append(document.createTextNode((passage?.final_text || "").slice(offset) + "\n"));
    mirror.style.width = `${$("trial-passage").clientWidth + 2}px`;
    mirror.scrollTop = $("trial-passage").scrollTop;
    mirror.scrollLeft = $("trial-passage").scrollLeft;
  }
  function updateText(text, start, end, insertedLength) {
    const delta = insertedLength - (end - start);
    for (const phrase of passage.suggestions) {
      if (phrase.state === "unavailable") continue;
      if (start >= phrase.start && end <= phrase.end) {
        phrase.end += delta; phrase.state = "Edited manually";
      } else if (end <= phrase.start) {
        phrase.start += delta; phrase.end += delta;
      } else if (start < phrase.end) phrase.state = "unavailable";
    }
    passage.final_text = text;
  }
  function snapshot() {
    undo.push({ text: passage.final_text, suggestions: structuredClone(passage.suggestions) });
  }
  function beginEditing() {
    if (!edited) {
      edited = true;
      record("edit_started");
      if (requested && passage.generation === "pending") {
        message("Editing began. Pending suggestions will be discarded; no replacement request.");
      }
    }
  }
  function apply(phrase, wording, action) {
    const index = passage.suggestions.indexOf(phrase);
    snapshot(); beginEditing();
    updateText(passage.final_text.slice(0, phrase.start) + wording
      + passage.final_text.slice(phrase.end), phrase.start, phrase.end, wording.length);
    phrase.state = action === "apply" ? "Selected replacement" : "Edited manually";
    $("trial-passage").value = passage.final_text;
    flush(action, { phrase: phrase.phrase, occurrence: phrase.occurrence });
    choices(); changed(); renderState();
    message("Your wording is applied to this occurrence only. Check the whole passage before copying.");
    document.querySelector(`#trial-phrase-${index} .edit-phrase`)?.focus();
  }
  function choices() {
    const container = $("trial-choices"); container.replaceChildren();
    for (const [index, phrase] of passage.suggestions.entries()) {
      const row = document.createElement("section"); row.className = "trial-suggestion";
      row.id = `trial-phrase-${index}`;
      row.style.background = tints[index % tints.length];
      const title = document.createElement("strong");
      title.textContent = `${index + 1}. ${phrase.phrase} · occurrence ${phrase.occurrence}`;
      row.append(title);
      const wording = passage.final_text.slice(phrase.start, phrase.end);
      const note = document.createElement("p");
      note.textContent = phrase.state === "unavailable"
        ? "Edited across phrase boundary — continue in the passage editor."
        : `Current: “${wording}” · ${phrase.state || "used if unchanged"}`;
      row.append(note);
      const button = (label, action) => {
        const control = document.createElement("button"); control.type = "button";
        control.className = "button"; control.textContent = label; control.onclick = action;
        row.append(control); return control;
      };
      if (!phrase.state) for (const option of phrase.alternatives) {
        button(`Use “${option}”`, () => apply(phrase, option, "apply"));
      }
      if (phrase.state !== "unavailable") {
        const editButton = button(phrase.state ? `Edit “${wording || "(empty phrase)"}”` : "Find / edit", () => {
          row.querySelectorAll("button").forEach((control) => { control.hidden = true; });
          const form = document.createElement("form"); form.className = "trial-phrase-editor";
          const label = document.createElement("label"); label.textContent = "Edit this phrase only";
          const field = document.createElement("input"); field.value = wording;
          field.setAttribute("aria-label", "Edit this phrase only"); label.append(field);
          const use = document.createElement("button"); use.type = "submit";
          use.className = "button"; use.textContent = "Use wording";
          const cancel = document.createElement("button"); cancel.type = "button";
          cancel.className = "button"; cancel.textContent = "Cancel";
          const cancelEdit = () => {
            choices();
            document.querySelector(`#trial-phrase-${index} .edit-phrase`)?.focus();
          };
          cancel.onclick = cancelEdit;
          field.onkeydown = (event) => {
            if (event.key === "Escape") { event.preventDefault(); cancelEdit(); }
          };
          form.onsubmit = (event) => { event.preventDefault(); apply(phrase, field.value, "edit"); };
          form.append(label, use, cancel); row.append(form); field.focus(); field.select();
        });
        editButton.classList.add("edit-phrase");
        if (!phrase.state) button("Keep current wording", () => {
          record("keep", { phrase: phrase.phrase, occurrence: phrase.occurrence });
          phrase.state = "Kept current wording"; choices();
        });
      }
      container.append(row);
    }
    highlights();
  }
  async function generate() {
    if (!passage?.id || requested || (edited && passage.assignment !== "manual")) return;
    flush();
    requested = true; edited = false; passage.generation = "pending"; renderState();
    const id = passage.id;
    message("Requesting alternatives · edit or copy now; no need to wait.");
    try {
      await queue;
      const result = await api(`/passages/${id}/alternatives`);
      if (passage?.id !== id || edited) return;
      passage.suggestions = result.suggestions;
      passage.generation = result.generation;
      choices(); record("shown");
      message(result.generation === "completed"
        ? result.suggestions.length ? "Alternatives ready. Nothing has been replaced."
          : "No passage-supported alternatives returned. Continue manually."
        : `Alternatives ${result.generation}. Continue manually; no retry.`);
    } catch (error) {
      if (passage?.id === id && !edited) message(`${error.message} Continue manually; no retry.`);
    }
    try { state = await api("", undefined, "GET"); renderState(); }
    catch (_error) { /* Budget is still enforced by the server before every dispatch. */ }
  }
  $("trial-begin").onclick = async () => {
    if (assigning || passage) return;
    assigning = true;
    $("trial-begin").disabled = true;
    const text = $("original-text").value;
    try {
      passage = await api("/passages", { text });
      if ($("original-text").value !== text) {
        await api(`/passages/${passage.id}`, undefined, "DELETE"); passage = null;
        throw new Error("Original changed before assignment completed; begin again.");
      }
      edited = false; requested = false; undo = []; savedText = text;
      cleanup = null; recordFailed = false;
      $("trial-passage").value = text;
      $("trial-spoken").value = "unconfirmed"; $("trial-effort").value = ""; $("trial-note").value = "";
      feedbackMessage("");
      choices(); renderState(); changed();
      message("Manual editing and copying are available now.");
      if (passage.assignment === "alternatives") generate();
    } catch (error) { message(error.message); }
    finally { assigning = false; renderState(); }
  };
  $("trial-include").onchange = async () => {
    try {
      state = await api("/preference", { include: $("trial-include").checked }, "PUT");
      excluded = false; changed(); renderState();
      message($("trial-include").checked
        ? "Ordinary correction is bypassed. Finish dictating, then Begin included passage."
        : "Excluded passages use normal Sayloom without trial records.");
    } catch (error) { $("trial-include").checked = state.include; message(error.message); }
  };
  $("trial-controls-open").onclick = () => {
    $("trial-controls-error").textContent = "";
    $("trial-controls-dialog").showModal();
  };
  $("trial-controls-close").onclick = () => $("trial-controls-dialog").close();
  $("trial-controls-dialog").onclick = (event) => {
    if (event.target === $("trial-controls-dialog")) $("trial-controls-dialog").close();
  };
  document.querySelectorAll("[data-trial-control]").forEach((button) => {
    button.onclick = async () => {
      const action = button.dataset.trialControl;
      if (["start", "extend"].includes(action) && !window.confirm(action === "start"
        ? "Start the one-week calendar window now? Inclusion remains your choice per passage."
        : "Explicitly extend by one calendar week? The combined budget remains US$5.")) return;
      try {
        state = await api("/control", { action }); changed(); renderState();
        $("trial-controls-dialog").close();
      }
      catch (error) {
        $("trial-controls-error").textContent = error.message;
        message(error.message);
      }
    };
  });
  $("trial-switch").onclick = generate;
  $("trial-exit").onclick = async () => {
    const id = passage?.id;
    try {
      await queue;
      if (id) await api(`/passages/${id}`, undefined, "DELETE");
      const normalText = $("trial-passage").value;
      passage = null; cleanup = null; excluded = true; changed({ normalText }); renderState();
      message("This passage's saved content was deleted. Normal correction restored. Future inclusion is unchanged.");
    } catch (error) { message(error.message); }
  };
  $("trial-passage").addEventListener("beforeinput", (event) => {
    beginEditing();
    pendingEdit = event.inputType.startsWith("insert") ? {
      before: passage.final_text, start: $("trial-passage").selectionStart,
      end: $("trial-passage").selectionEnd,
    } : null;
  });
  $("trial-passage").oninput = () => {
    beginEditing();
    const before = passage.final_text, after = $("trial-passage").value;
    if (savedText === before) snapshot();
    let start = 0, end = before.length, afterEnd = after.length;
    while (start < end && start < afterEnd && before[start] === after[start]) start++;
    while (end > start && afterEnd > start && before[end - 1] === after[afterEnd - 1]) {
      end--; afterEnd--;
    }
    if (pendingEdit?.before === before) {
      const inserted = after.length - before.length + pendingEdit.end - pendingEdit.start;
      if (inserted >= 0 && after.slice(0, pendingEdit.start) === before.slice(0, pendingEdit.start)
        && after.slice(pendingEdit.start + inserted) === before.slice(pendingEdit.end)) {
        start = pendingEdit.start; end = pendingEdit.end; afterEnd = start + inserted;
      }
    }
    pendingEdit = null; updateText(after, start, end, afterEnd - start);
    choices(); changed(); renderState();
    if (passage.generation !== "pending") message("Manual edits are in the current passage. Check all wording before copying.");
  };
  $("trial-passage").onblur = () => flush();
  $("trial-passage").onscroll = highlights;
  new ResizeObserver(highlights).observe($("trial-passage"));
  $("trial-undo").onclick = () => {
    if (!undo.length) return;
    beginEditing(); const previous = undo.pop();
    passage.final_text = previous.text; passage.suggestions = previous.suggestions;
    $("trial-passage").value = previous.text; flush("reverse"); choices(); changed(); renderState();
    message("Last applied step reversed. Check the whole passage before copying.");
  };
  async function saveFeedback() {
    if (!passage?.id) return false;
    feedbackMessage("");
    flush();
    const current = passage;
    const spoken = $("trial-spoken").value;
    const result = await record("feedback", { spoken, effort: $("trial-effort").value, note: $("trial-note").value });
    if (passage !== current) return false;
    if (!result) {
      feedbackMessage("Feedback could not be saved. Try saving again.");
      return false;
    }
    if (["unsure", "revised"].includes(spoken)) {
      // Keep the editable draft but never save another event for this excluded record.
      passage.id = null; feedbackMessage("Saved content excluded and deleted. Your draft remains available to copy.");
    } else feedbackMessage("Optional feedback saved.");
    return true;
  }
  $("trial-feedback").oninput = () => feedbackMessage("");
  $("trial-feedback-save").onclick = saveFeedback;
  $("trial-clean").onclick = async () => {
    if (!passage || cleanup?.status === "cleaning") return;
    // Freeze the comparison before cleanup: neither feedback nor repair text can
    // subsequently be influenced by seeing the cleaned result.
    const attempt = { status: "cleaning", text: "", saved: cleanup?.saved || false };
    const current = passage;
    const text = $("trial-passage").value;
    cleanup = attempt;
    edited = true; // Discard any pending alternatives response.
    renderState();
    await changed(); // Clear the published payload before requesting cleanup.
    try {
      if (cleanup !== attempt || passage !== current) return;
      if (!attempt.saved) {
        await queue;
        if (cleanup !== attempt || passage !== current) return;
        recordFailed = false;
        // A previous flush may have failed after advancing its local text cache.
        // Always persist this frozen snapshot before allowing cleanup or a retry.
        record("edit", { final_text: text });
        if (passage.id && !await saveFeedback()) throw new Error("Trial feedback could not be saved.");
        await queue;
        if (recordFailed) throw new Error("Trial repairs could not be saved.");
        attempt.saved = true;
      }
      if (cleanup !== attempt || passage !== current) return;
      const response = await fetch("/api/cleanup", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ original_text: text, enabled: true, correction_mode: "conservative" }),
        signal: AbortSignal.timeout(30000),
      });
      const result = await response.json();
      if (!response.ok || !["prepared", "unchanged"].includes(result.status)
        || typeof result.prepared_text !== "string" || !result.prepared_text.trim()) {
        throw new Error("Conservative cleanup did not produce usable text.");
      }
      if (cleanup !== attempt || passage !== current) return;
      attempt.text = result.prepared_text;
      attempt.status = "prepared";
    } catch (_error) {
      if (cleanup !== attempt || passage !== current) return;
      attempt.status = "error";
    }
    renderState(); changed();
  };
  window.phraseTrial = {
    async initialize(available, callback) {
      enabled = available; changed = callback;
      if (!available) return;
      $("phrase-trial").hidden = false;
      $("trial-inclusion").hidden = false;
      $("trial-controls-open").hidden = false;
      try {
        state = await api("", undefined, "GET"); $("trial-include").checked = state.include;
        renderState(); changed();
      } catch (error) { message(error.message); }
    },
    capturing,
    outgoing() { return cleanup ? cleanup.text : passage ? $("trial-passage").value : null; },
    cleanupStatus() { return cleanup?.status; },
    refresh: renderState,
    copy() { if (!cleanup) flush("copy"); },
    reset() {
      if (!enabled) return;
      if (!cleanup) flush();
      passage = null; cleanup = null; excluded = false; undo = []; edited = false; requested = false;
      feedbackMessage("");
      renderState();
    },
  };
})();
