const $ = (id) => document.getElementById(id);
const STORAGE_KEY = "lesson-studio-v1";
const DRAFTS_KEY = "lesson-studio-drafts-v1";
let researchData = null;
let qcReports = null;
let currentDraftId = null;
let drafts = [];

function showError(message) {
  $("errorMessage").textContent = message || "";
}

function getInputs() {
  return { title: $("titleInput").value.trim(), objective: $("objectiveInput").value.trim() };
}

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  button.dataset.originalLabel ||= button.textContent;
  button.textContent = busy ? label : button.dataset.originalLabel;
}

function renderSources(sources) {
  populateSourceList("sourceList", sources);
  populateSourceList("reviewSourceList", sources);
  $("sourceCount").textContent = `${sources.length} links`;
  $("reviewSourceCount").textContent = `${sources.length} links`;
  $("dashboardSources").textContent = `${sources.length} links`;
  const warnings = researchData?.research_errors || [];
  $("researchWarning").textContent = warnings.join(" ");
  $("researchWarning").classList.toggle("hidden", warnings.length === 0);
  $("researchPanel").classList.remove("hidden");
}

function populateSourceList(listId, sources) {
  const list = $(listId);
  list.replaceChildren();
  for (const source of sources) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = `${source.kind} · ${source.title}`;
    item.append(link);
    list.append(item);
  }
}

async function findResearch() {
  showError("");
  const { title, objective } = getInputs();
  if (!title || !objective) return showError("Enter both a lesson title and a learning objective.");
  setBusy($("researchButton"), true, "Searching…");
  try {
    researchData = await post("/api/research", { title, objective });
    renderSources(researchData.sources);
    persist();
  } catch (error) {
    showError(`Research failed: ${error.message}. Your saved lesson is unchanged; retry when ready.`);
  } finally {
    setBusy($("researchButton"), false);
  }
}

async function generate() {
  showError("");
  const { title, objective } = getInputs();
  if (!title || !objective) return showError("Enter both a lesson title and a learning objective.");
  setBusy($("generateButton"), true, "Building lesson…");
  try {
    if (!researchData) researchData = await post("/api/research", { title, objective });
    const result = await post("/api/generate", { title, objective, research: researchData });
    $("lessonEditor").value = result.content;
    qcReports = { research: result.qc_research, instruction: result.qc_instruction };
    renderSources(result.sources);
    renderQc("researchQc", result.qc_research);
    renderQc("instructionQc", result.qc_instruction);
    $("workspace").classList.remove("hidden");
    setJourneyStep(3);
    persist();
    $("workspace").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showError(`Generation failed: ${error.message}. Your saved lesson is unchanged; retry when ready.`);
  } finally {
    setBusy($("generateButton"), false);
  }
}

async function runQc() {
  const { title, objective } = getInputs();
  const result = await post("/api/qc", {
    title,
    objective,
    content: $("lessonEditor").value,
    sources: researchData?.sources || [],
    research_notes: researchData?.research_notes || [],
  });
  qcReports = { research: result.qc_research, instruction: result.qc_instruction };
  renderQc("researchQc", result.qc_research);
  renderQc("instructionQc", result.qc_instruction);
  persist();
}

function renderQc(target, report) {
  const container = $(target);
  container.replaceChildren();
  const status = document.createElement("span");
  status.className = `qc-status${report.issues.length ? " review" : ""}`;
  status.textContent = report.status;
  container.append(status);
  for (const issue of report.issues) {
    const row = document.createElement("div");
    row.className = "qc-issue";
    const severity = document.createElement("span");
    severity.className = "severity";
    severity.textContent = issue.severity;
    const title = document.createElement("strong");
    title.textContent = issue.issue;
    const recommendation = document.createElement("p");
    recommendation.textContent = issue.recommendation;
    const button = document.createElement("button");
    button.className = "apply-button";
    button.type = "button";
    button.textContent = "Apply recommendation";
    button.addEventListener("click", () => {
      const editor = $("lessonEditor");
      editor.value += `\n\n## QC improvement\n${issue.recommendation}`;
      persist();
      updateWordCount();
    });
    row.append(severity, document.createElement("br"), title, recommendation, button);
    container.append(row);
  }
  const note = document.createElement("p");
  note.className = "qc-description";
  note.textContent = report.note;
  container.append(note);
}

function markQcStale(message) {
  qcReports = null;
  for (const id of ["researchQc", "instructionQc"]) {
    const container = $(id);
    container.replaceChildren();
    const status = document.createElement("span");
    status.className = "qc-status review";
    status.textContent = "Review needed";
    const note = document.createElement("p");
    note.className = "qc-description";
    note.textContent = message;
    container.append(status, note);
  }
}

function handleInputsChanged() {
  const { title, objective } = getInputs();
  if (researchData && researchData.query !== `${title} ${objective}`) {
    researchData = null;
    $("researchPanel").classList.add("hidden");
  }
  if (qcReports) markQcStale("The lesson inputs changed. Run both QC checks again.");
  persist();
}

function persist() {
  if (!currentDraftId) currentDraftId = createDraftId();
  const state = {
    id: currentDraftId,
    title: $("titleInput").value,
    objective: $("objectiveInput").value,
    content: $("lessonEditor").value,
    researchData,
    qcReports,
    updatedAt: new Date().toISOString(),
  };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    const hasWork = Boolean(
      state.title.trim() ||
      state.objective.trim() ||
      state.content.trim() ||
      state.researchData
    );
    if (hasWork) {
      drafts = [state, ...drafts.filter((draft) => draft.id !== currentDraftId)];
    } else {
      drafts = drafts.filter((draft) => draft.id !== currentDraftId);
    }
    localStorage.setItem(DRAFTS_KEY, JSON.stringify({ currentId: currentDraftId, drafts }));
    renderSavedDrafts();
    $("savedState").textContent = hasWork
      ? "Saved in this browser"
      : "New lesson · changes save automatically";
  } catch (error) {
    $("savedState").textContent = "Could not save in this browser";
    showError(`Save failed: ${error.message}. Export your work to keep a copy.`);
  }
}

function createDraftId() {
  return `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function renderSavedDrafts() {
  const list = $("savedLessonsList");
  if (!list) return;
  list.replaceChildren();
  $("savedLessonsCount").textContent = String(drafts.length);
  if (!drafts.length) {
    const empty = document.createElement("li");
    empty.className = "saved-lessons-empty";
    empty.textContent = "Your saved lessons will appear here.";
    list.append(empty);
    return;
  }
  for (const draft of drafts) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = `saved-lesson-button${draft.id === currentDraftId ? " current" : ""}`;
    const icon = document.createElement("span");
    icon.className = "saved-lesson-icon";
    icon.textContent = draft.content ? "▤" : "＋";
    const copy = document.createElement("span");
    copy.className = "saved-lesson-copy";
    const title = document.createElement("strong");
    title.textContent = draft.title?.trim() || "Untitled lesson";
    const detail = document.createElement("small");
    detail.textContent = draft.content ? "Lesson draft saved" : "In progress";
    copy.append(title, detail);
    button.append(icon, copy);
    button.addEventListener("click", () => loadDraft(draft.id));
    item.append(button);
    list.append(item);
  }
}

function applyDraft(state) {
  currentDraftId = state.id || createDraftId();
  $("titleInput").value = state.title || "";
  $("objectiveInput").value = state.objective || "";
  $("lessonEditor").value = state.content || "";
  researchData = state.researchData || null;
  qcReports = state.qcReports || null;
  $("workspace").classList.toggle("hidden", !state.content);
  $("preview").classList.add("hidden");
  $("researchPanel").classList.toggle("hidden", !researchData);
  if (researchData) renderSources(researchData.sources || []);
  else {
    $("sourceList").replaceChildren();
    $("reviewSourceList").replaceChildren();
    $("dashboardSources").textContent = "Books + web";
  }
  if (qcReports) {
    renderQc("researchQc", qcReports.research);
    renderQc("instructionQc", qcReports.instruction);
    setJourneyStep(3);
  } else {
    $("researchQc").replaceChildren();
    $("instructionQc").replaceChildren();
    setJourneyStep(state.content ? 3 : 1);
  }
  updateWordCount();
  renderSavedDrafts();
}

function loadDraft(id) {
  const draft = drafts.find((item) => item.id === id);
  if (!draft) {
    showError("That saved lesson could not be found.");
    return;
  }
  applyDraft(draft);
  persist();
  $("createPanel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function createNewLesson() {
  const { title, objective } = getInputs();
  const hasWork = Boolean(
    title ||
    objective ||
    $("lessonEditor").value.trim() ||
    researchData
  );
  if (hasWork) {
    persist();
    currentDraftId = createDraftId();
  }
  applyDraft({ id: currentDraftId, title: "", objective: "", content: "" });
  persist();
  showError("");
  $("titleInput").focus();
  $("createPanel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function restore() {
  try {
    const savedDrafts = JSON.parse(localStorage.getItem(DRAFTS_KEY) || "null");
    if (savedDrafts && Array.isArray(savedDrafts.drafts)) {
      drafts = savedDrafts.drafts;
      const current = drafts.find((draft) => draft.id === savedDrafts.currentId);
      if (current) applyDraft(current);
      else applyDraft({ id: createDraftId(), title: "", objective: "", content: "" });
      return;
    }

    const previousState = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (previousState) {
      previousState.id = createDraftId();
      currentDraftId = previousState.id;
      drafts = [previousState];
      applyDraft(previousState);
      persist();
      return;
    }
    currentDraftId = createDraftId();
    drafts = [];
    applyDraft({ id: currentDraftId, title: "", objective: "", content: "" });
    renderSavedDrafts();
  } catch (error) {
    showError(`Could not restore saved work: ${error.message}`);
  }
}

function updateWordCount() {
  const count = $("lessonEditor").value.trim().split(/\s+/).filter(Boolean).length;
  $("wordCount").textContent = `${count} words`;
}

function setJourneyStep(step) {
  document.querySelectorAll(".journey-list li").forEach((item, index) => {
    item.classList.toggle("journey-current", index + 1 === step);
    const indicator = item.querySelector(".journey-check");
    indicator.textContent = index + 1 < step ? "✓" : index + 1 === step ? "●" : "○";
  });
  const progress = document.querySelector(".workflow-progress span");
  if (progress) progress.style.width = `${Math.max(33, step * 33)}%`;
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function renderMarkdown(text) {
  const lines = escapeHtml(boldReferenceLinks(text)).split("\n");
  let html = "";
  let inList = false;
  for (const line of lines) {
    const heading = line.match(/^(#{1,3})\s+(.+)/);
    const list = line.match(/^\s*[-*]\s+(.+)/);
    if (inList && !list) { html += "</ul>"; inList = false; }
    if (heading) html += `<h${heading[1].length}>${heading[2]}</h${heading[1].length}>`;
    else if (list) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${formatInline(list[1])}</li>`;
    } else if (line.trim()) html += `<p>${formatInline(line)}</p>`;
  }
  if (inList) html += "</ul>";
  return html;
}

function boldReferenceLinks(text) {
  let inReferences = false;
  return text.split("\n").map((line) => {
    if (/^#{1,3}\s*(references|sources)\b/i.test(line)) inReferences = true;
    else if (inReferences && /^#{1,3}\s+/.test(line)) inReferences = false;
    if (inReferences && /^\s*[-*]\s+/.test(line)) {
      return line.replace(/(?<!\*)\[([^\]]+)\]\((https?:\/\/[^)]+)\)(?!\*)/g, "**[$1]($2)**");
    }
    return line;
  }).join("\n");
}

function formatInline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

$("researchButton").addEventListener("click", findResearch);
$("newLessonButton").addEventListener("click", createNewLesson);
$("createLessonNav").addEventListener("click", (event) => {
  event.preventDefault();
  createNewLesson();
});
$("generateButton").addEventListener("click", generate);
$("retryButton").addEventListener("click", generate);
$("qcButton").addEventListener("click", async () => {
  showError("");
  try { await runQc(); }
  catch (error) { showError(`QC failed: ${error.message}. Your current lesson is unchanged.`); }
});
$("sampleButton").addEventListener("click", () => {
  $("titleInput").value = "HTTP Requests and Responses";
  $("objectiveInput").value = "Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.";
  handleInputsChanged();
});
$("lessonEditor").addEventListener("input", () => {
  updateWordCount();
  if (qcReports) markQcStale("The lesson was edited. Run both QC checks again.");
  persist();
});
$("titleInput").addEventListener("input", handleInputsChanged);
$("objectiveInput").addEventListener("input", handleInputsChanged);
$("previewButton").addEventListener("click", () => {
  $("previewContent").innerHTML = renderMarkdown($("lessonEditor").value);
  $("preview").classList.remove("hidden");
  $("preview").scrollIntoView({ behavior: "smooth", block: "start" });
});
$("closePreview").addEventListener("click", () => $("preview").classList.add("hidden"));
$("researchNav").addEventListener("click", (event) => {
  if ($("researchPanel").classList.contains("hidden")) {
    event.preventDefault();
    $("createPanel").scrollIntoView({ behavior: "smooth", block: "start" });
    if (getInputs().title && getInputs().objective) findResearch();
  }
});
$("qualityNav").addEventListener("click", (event) => {
  if ($("workspace").classList.contains("hidden")) {
    event.preventDefault();
    $("createPanel").scrollIntoView({ behavior: "smooth", block: "start" });
    showError("Create a lesson first to review its quality checks.");
  }
});
document.querySelectorAll(".side-nav .nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".side-nav .nav-item").forEach((link) => link.classList.remove("active"));
    item.classList.add("active");
  });
});
$("exportButton").addEventListener("click", async () => {
  const content = boldReferenceLinks($("lessonEditor").value);
  if (!content.trim()) return showError("Generate a lesson before exporting.");
  showError("");
  try { await runQc(); }
  catch (error) { return showError(`QC failed; export cancelled so reports are not stale: ${error.message}`); }
  const output = [
    content,
    "\n\n---\n## QC report: Research and factual accuracy\n",
    JSON.stringify(qcReports?.research || { status: "Not run" }, null, 2),
    "\n\n## QC report: Instructional quality\n",
    JSON.stringify(qcReports?.instruction || { status: "Not run" }, null, 2),
  ].join("");
  const blob = new Blob([output], { type: "text/markdown;charset=utf-8" });
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(blob);
  anchor.download = `${getInputs().title.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "lesson"}.md`;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
});
restore();
