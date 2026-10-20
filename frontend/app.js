const caseForm = document.querySelector("#case-form");
const reportForm = document.querySelector("#report-form");
const caseList = document.querySelector("#case-list");
const message = document.querySelector("#message");
const reviewPanel = document.querySelector("#review-panel");
const reportPreview = document.querySelector("#report-preview");
const previewEmpty = document.querySelector("#preview-empty");
const urgencyCard = document.querySelector("#urgency-card");
let apiKey = "";
let activeCase = null;
let cases = [];

function showMessage(text, isError = false) {
  message.textContent = text;
  message.className = `message ${isError ? "error" : "success"}`;
}

function clearMessage() {
  message.textContent = "";
  message.className = "message hidden";
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers);
  if (apiKey) headers.set("Authorization", `Bearer ${apiKey}`);
  const response = await fetch(path, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "The request could not be completed.");
  }
  return payload;
}

function reportStatus(item) {
  return item.report ? item.report.status : "no draft";
}

function renderCases() {
  document.querySelector("#queue-count").textContent = cases.length;
  if (!cases.length) {
    caseList.innerHTML = '<p class="empty-state">No cases yet. Create a case to begin a supervised workflow demo.</p>';
    return;
  }
  caseList.replaceChildren(...cases.map((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `case-item${activeCase?.id === item.id ? " selected" : ""}`;
    button.addEventListener("click", () => selectCase(item.id));
    const icon = document.createElement("span");
    icon.className = "case-icon";
    icon.textContent = "⌁";
    const meta = document.createElement("span");
    meta.className = "case-meta";
    const title = document.createElement("strong");
    title.textContent = `${item.body_region} MRI`;
    const sub = document.createElement("small");
    sub.textContent = new Date(item.created_at).toLocaleString();
    meta.append(title, sub);
    const status = document.createElement("span");
    status.className = "case-status";
    status.textContent = reportStatus(item).replaceAll("_", " ").toUpperCase();
    button.append(icon, meta, status);
    return button;
  }));
}

function setActiveCase(item) {
  activeCase = item;
  caseForm.classList.add("disabled-form");
  document.querySelector("#body-region").value = item.body_region;
  document.querySelector("#scan-files").value = "";
  document.querySelector("#form-title").textContent = `${item.body_region} MRI case`;
  const status = reportStatus(item);
  const statusBadge = document.querySelector("#case-status");
  statusBadge.className = `pill ${item.report ? item.report.status : "neutral"}`;
  statusBadge.textContent = status.replaceAll("_", " ").toUpperCase();

  const editable = !item.report || item.report.status === "returned";
  reportForm.classList.toggle("disabled-form", !editable);
  document.querySelector("#indication").value = item.report?.indication === "Not provided" ? "" : item.report?.indication || "";
  document.querySelector("#findings").value = item.report?.findings || "";
  document.querySelector("#impression").value = item.report?.impression || "";
  document.querySelector("#reviewer").value = "";
  document.querySelector("#review-note").value = "";
  reviewPanel.classList.toggle("hidden", !item.report || item.report.status !== "pending_review");

  if (item.report_text) {
    reportPreview.textContent = item.report_text;
    reportPreview.classList.remove("hidden");
    previewEmpty.classList.add("hidden");
    urgencyCard.classList.remove("hidden");
  } else {
    reportPreview.textContent = "";
    reportPreview.classList.add("hidden");
    previewEmpty.classList.remove("hidden");
    urgencyCard.classList.add("hidden");
  }
  renderCases();
  clearMessage();
}

async function refreshCases() {
  cases = await request("/api/cases");
  renderCases();
}

async function selectCase(id) {
  try {
    setActiveCase(await request(`/api/cases/${id}`));
  } catch (error) {
    showMessage(error.message, true);
  }
}

caseForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
  const files = document.querySelector("#scan-files").files;
  if (!files.length) {
    showMessage("Choose at least one MRI image file.", true);
    return;
  }
  const button = document.querySelector("#create-case");
  button.disabled = true;
  try {
    const body = new FormData();
    body.append("body_region", document.querySelector("#body-region").value);
    for (const file of files) body.append("files", file);
    const item = await request("/api/cases", { method: "POST", body });
    await refreshCases();
    setActiveCase(item);
    showMessage("Case created. No image interpretation was performed; enter a draft for supervised review.");
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    button.disabled = false;
  }
});

reportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeCase) return;
  clearMessage();
  try {
    const item = await request(`/api/cases/${activeCase.id}/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        indication: document.querySelector("#indication").value,
        findings: document.querySelector("#findings").value,
        impression: document.querySelector("#impression").value,
      }),
    });
    setActiveCase(item);
    showMessage("Draft saved as pending review. The report contains only manually entered text.");
  } catch (error) {
    showMessage(error.message, true);
  }
});

async function submitReview(action) {
  if (!activeCase) return;
  clearMessage();
  try {
    const item = await request(`/api/cases/${activeCase.id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action,
        reviewer: document.querySelector("#reviewer").value,
        review_note: document.querySelector("#review-note").value,
      }),
    });
    setActiveCase(item);
    showMessage(action === "sign" ? "Review recorded in this session." : "Report returned for revision.");
  } catch (error) {
    showMessage(error.message, true);
  }
}

document.querySelector("#sign-report").addEventListener("click", () => submitReview("sign"));
document.querySelector("#return-report").addEventListener("click", () => submitReview("return"));
document.querySelector("#new-case").addEventListener("click", () => {
  activeCase = null;
  caseForm.reset();
  caseForm.classList.remove("disabled-form");
  reportForm.reset();
  reportForm.classList.add("disabled-form");
  reviewPanel.classList.add("hidden");
  document.querySelector("#form-title").textContent = "Start a review case";
  document.querySelector("#case-status").className = "pill neutral";
  document.querySelector("#case-status").textContent = "NEW CASE";
  reportPreview.classList.add("hidden");
  previewEmpty.classList.remove("hidden");
  urgencyCard.classList.add("hidden");
  renderCases();
  clearMessage();
});

document.querySelector("#api-auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  apiKey = document.querySelector("#api-key").value.trim();
  clearMessage();
  try {
    await refreshCases();
    showMessage("Connected. Case and review data is stored by the configured server database.");
  } catch (error) {
    apiKey = "";
    showMessage(error.message, true);
  }
});
