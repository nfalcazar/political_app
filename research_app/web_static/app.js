"use strict";

const landing = document.getElementById("landing");
const projectView = document.getElementById("project-view");
const projectMatch = window.location.pathname.match(/^\/projects\/([^/]+)$/);
const projectId = projectMatch ? decodeURIComponent(projectMatch[1]) : null;
let currentBrief = null;
let pollTimer = null;

function show(element, visible) { element.classList.toggle("hidden", !visible); }
function clear(element) { while (element.firstChild) element.removeChild(element.firstChild); }
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}
function safeUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch (_) { return null; }
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let payload = {};
  try { payload = await response.json(); } catch (_) { /* empty response */ }
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}
function prettyState(value) { return String(value || "not started").replaceAll("_", " "); }

async function submitClaim(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  const error = document.getElementById("claim-error");
  show(error, false);
  button.disabled = true;
  button.textContent = "Creating project…";
  try {
    const result = await api("/api/projects", {
      method: "POST",
      body: JSON.stringify({ claim: document.getElementById("claim").value }),
    });
    window.location.assign(result.url);
  } catch (reason) {
    error.textContent = reason.message;
    show(error, true);
    button.disabled = false;
    button.textContent = "Research this claim";
  }
}

function renderActions(actions) {
  show(document.getElementById("pause-button"), Boolean(actions.can_pause));
  show(document.getElementById("resume-button"), Boolean(actions.can_resume));
  show(document.getElementById("continue-button"), Boolean(actions.can_continue));
}

function renderScope(scope) {
  const container = document.getElementById("scope-list");
  clear(container);
  for (const item of scope) {
    const block = node("div", null, "scope-item");
    block.append(node("strong", item.text), node("span", `${item.kind} · ${item.origin.replaceAll("_", " ")}`));
    container.append(block);
  }
}

function renderStatus(payload) {
  const project = payload.project;
  const job = payload.job;
  document.getElementById("project-claim").textContent = project.thesis;
  const state = job ? job.state : project.status;
  const badge = document.getElementById("job-state");
  badge.textContent = prettyState(state);
  badge.className = `status-pill ${state}`;
  const funnel = project.research_funnel || {};
  document.getElementById("progress-text").textContent =
    `${funnel.leads_discovered || 0} leads → ${funnel.documents_retrieved || 0} retrieved → ` +
    `${funnel.relevant_documents || 0} relevant → ${funnel.evidence_sources || 0} evidence sources ` +
    `(${funnel.evidence_items || 0} evidence items)`;
  const error = document.getElementById("job-error");
  if (job && job.error) {
    error.textContent = job.error;
    show(error, true);
  } else show(error, false);
  renderScope(payload.scope || []);
  renderActions(payload.actions || {});
  return state;
}

function renderArguments(argumentsList) {
  const support = document.getElementById("supporting-arguments");
  const challenge = document.getElementById("challenging-arguments");
  clear(support); clear(challenge);
  const grouped = { supports: [], challenges: [] };
  for (const argument of argumentsList) {
    if (argument.stance === "supports") grouped.supports.push(argument);
    if (argument.stance === "challenges") grouped.challenges.push(argument);
    if (argument.stance === "mixed") {
      grouped.supports.push(argument);
      grouped.challenges.push(argument);
    }
  }
  for (const [container, items, emptyText] of [
    [support, grouped.supports, "No accepted supporting argument yet."],
    [challenge, grouped.challenges, "No accepted challenging argument yet."],
  ]) {
    if (!items.length) { container.append(node("p", emptyText, "empty-copy")); continue; }
    for (const item of items) {
      const block = node("div", null, "argument");
      block.append(node("h3", item.title), node("p", item.explanation));
      container.append(block);
    }
  }
}

function renderSources(sources) {
  const list = document.getElementById("source-list");
  clear(list);
  document.getElementById("source-count").textContent = `${sources.length} selected`;
  if (!sources.length) { list.append(node("p", "No qualifying evidence sources are available yet.", "empty-copy")); return; }
  for (const source of sources) {
    const card = node("article", null, "source-card");
    const meta = node("div", null, "source-meta");
    meta.append(node("span", source.publisher || "Publisher unknown"), node("span", source.source_type.replaceAll("_", " ")));
    if (source.publication_date) meta.append(node("span", source.publication_date));
    const heading = node("h3");
    const href = safeUrl(source.url);
    if (href) {
      const link = node("a", source.title);
      link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer";
      heading.append(link);
    } else heading.textContent = source.title;
    card.append(meta, heading, node("p", source.why_selected));
    const details = node("details", null, "evidence-detail");
    details.append(node("summary", `View ${source.evidence.length} evidence ${source.evidence.length === 1 ? "item" : "items"}`));
    for (const evidence of source.evidence) {
      const item = node("div", null, "evidence-item");
      item.dataset.evidenceId = evidence.evidence_id;
      item.append(node("p", evidence.finding), node("p", `“${evidence.excerpt}”`, "excerpt"), node("p", `${evidence.locator} · ${evidence.confidence} confidence`));
      details.append(item);
    }
    card.append(details); list.append(card);
  }
}

function renderBrief(brief) {
  currentBrief = brief;
  const assessment = brief.assessment;
  document.getElementById("assessment-label").textContent = prettyState(assessment.label);
  document.getElementById("assessment-summary").textContent = assessment.summary;
  document.getElementById("assessment-rationale").textContent = assessment.rationale;
  document.getElementById("coverage").textContent = `${brief.coverage.covered} of ${brief.coverage.total} empirical research claims currently have accepted evidence.`;
  renderArguments(brief.arguments || []);
  renderSources(brief.sources || []);
  const gaps = document.getElementById("gap-list"); clear(gaps);
  const values = brief.uncertainty_and_gaps || [];
  if (!values.length) gaps.append(node("li", "No additional gap was identified in the current synthesis."));
  else for (const value of values) gaps.append(node("li", value));
}

function renderMessages(messages) {
  const container = document.getElementById("messages"); clear(container);
  if (!messages.length) { container.append(node("p", "Ask for a source explanation, counterevidence, or a clearer account of uncertainty.", "empty-copy")); return; }
  for (const message of messages) {
    const bubble = node("div", message.content, `message ${message.role}`);
    if (message.citations && message.citations.length) bubble.append(node("span", `${message.citations.length} evidence citation${message.citations.length === 1 ? "" : "s"}`, "message-meta"));
    if (message.needs_additional_research) bubble.append(node("span", "Additional research may be needed", "message-meta"));
    container.append(bubble);
  }
  container.scrollTop = container.scrollHeight;
}

async function refreshProject() {
  try {
    const [status, brief, messages] = await Promise.all([
      api(`/api/projects/${encodeURIComponent(projectId)}`),
      api(`/api/projects/${encodeURIComponent(projectId)}/brief`),
      api(`/api/projects/${encodeURIComponent(projectId)}/messages`),
    ]);
    const state = renderStatus(status); renderBrief(brief); renderMessages(messages.messages);
    if (["pending", "running"].includes(state)) pollTimer = window.setTimeout(refreshProject, 2000);
  } catch (reason) {
    const error = document.getElementById("job-error"); error.textContent = reason.message; show(error, true);
  }
}

async function projectAction(action) {
  const error = document.getElementById("job-error"); show(error, false);
  try { await api(`/api/projects/${encodeURIComponent(projectId)}/${action}`, { method: "POST", body: "{}" }); await refreshProject(); }
  catch (reason) { error.textContent = reason.message; show(error, true); }
}

async function submitMessage(event) {
  event.preventDefault();
  const textarea = document.getElementById("message");
  const button = event.currentTarget.querySelector("button");
  const error = document.getElementById("message-error"); show(error, false); button.disabled = true;
  try {
    await api(`/api/projects/${encodeURIComponent(projectId)}/messages`, { method: "POST", body: JSON.stringify({ message: textarea.value }) });
    textarea.value = "";
    const result = await api(`/api/projects/${encodeURIComponent(projectId)}/messages`); renderMessages(result.messages);
  } catch (reason) { error.textContent = reason.message; show(error, true); }
  finally { button.disabled = false; }
}

if (projectId) {
  show(projectView, true);
  document.getElementById("message-form").addEventListener("submit", submitMessage);
  document.getElementById("pause-button").addEventListener("click", () => projectAction("pause"));
  document.getElementById("resume-button").addEventListener("click", () => projectAction("resume"));
  document.getElementById("continue-button").addEventListener("click", () => projectAction("continue"));
  refreshProject();
} else {
  show(landing, true);
  document.getElementById("claim-form").addEventListener("submit", submitClaim);
}
