(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { meta: null, repositories: [], meetings: [], jobs: [], job: null, jobId: null, repository: null, feedback: [], selectedFile: null, importMode: "path", creating: false, jobVersion: 0, repositoryVersion: 0, searchVersion: 0, pollBusy: false, feedbackBusy: false, listPoll: 0, booted: false };
  const terminal = new Set(["completed", "needs_review", "failed", "cancelled", "interrupted"]);
  const statusLabels = { queued: "排队中", running: "协作开发中", completed: "开发完成", needs_review: "待人工评审", failed: "开发失败", cancelled: "已停止", interrupted: "任务已中断" };
  const phaseLabels = { retrieve: "检索项目依据", code: "生成代码", validate: "静态检查", protocol_repair: "修复响应格式", failed: "任务失败", planning: "需求规划", plan: "需求规划", coding: "代码开发", generate: "代码生成", checks: "静态检查", validation: "静态检查", review: "代码评审", repair: "修复改进", learning: "经验候选", completed: "任务完成", queued: "等待调度", running: "开始开发", cancelled: "停止任务", error: "运行异常" };
  function el(tag, className = "", content) { const node = document.createElement(tag); if (className) node.className = className; if (content !== undefined && content !== null) node.textContent = String(content); return node; }
  function showError(id, error) { $(id).textContent = error?.message || String(error); $(id).hidden = false; }
  function notice(message, error = false) { $("notice-text").textContent = message; $("notice").classList.toggle("error", error); $("notice").hidden = false; $("live-status").textContent = message; }
  function shortDate(date) { if (!date) return ""; const parsed = new Date(date); return Number.isNaN(parsed.valueOf()) ? String(date) : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(parsed); }
  function bytes(value) { const n = Number(value || 0); return n >= 1048576 ? `${(n / 1048576).toFixed(1)} MiB` : `${Math.round(n / 1024)} KiB`; }
  function nameForRepository(id) { return state.repositories.find((repository) => repository.id === id)?.name || id || "未使用参考代码库"; }
  function detailText(value) { if (typeof value === "string") return value; if (value === undefined || value === null) return ""; return JSON.stringify(value, null, 2); }
  async function api(url, { method = "GET", body, raw = false, timeout = 30000 } = {}) {
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, { method, signal: controller.signal, credentials: "same-origin", headers: body === undefined ? {} : { "Content-Type": raw ? "application/zip" : "application/json" }, body: body === undefined ? undefined : raw ? body : JSON.stringify(body) });
      let data; try { data = await response.json(); } catch { data = null; }
      if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : typeof data?.error === "string" ? data.error : `请求失败（${response.status}），请查看本地服务是否可用。`);
      return data;
    } catch (error) { if (error.name === "AbortError") throw new Error("请求超时，请稍后刷新确认任务状态。"); throw error; }
    finally { clearTimeout(timer); }
  }
  function switchView(view) {
    for (const name of ["development", "knowledge", "roundtable"]) {
      $(name + "-view").hidden = name !== view;
      $("nav-" + name).classList.toggle("active", name === view);
      if (name === view) $("nav-" + name).setAttribute("aria-current", "page"); else $("nav-" + name).removeAttribute("aria-current");
    }
    $("page-name").textContent = {development:"开发工作台", knowledge:"代码库与知识", roundtable:"协作圆桌"}[view];
    if (view === "roundtable") history.replaceState(null, "", "#roundtable");
    else if (location.hash === "#roundtable") history.replaceState(null, "", location.pathname);
  }
  $("nav-roundtable").addEventListener("click", () => switchView("roundtable"));
  window.addEventListener("sparkcraft:develop", async (event) => { state.meetings = await api("/api/meetings"); renderMeetings(); newJob(); $("job-meeting").value = event.detail.id; $("task").value = event.detail.topic; $("task").dispatchEvent(new Event("input")); });
  if (location.hash === "#roundtable") switchView("roundtable");
  function modeLabel(mode) { return mode === "simulation" ? "规则模拟 · 非 AI" : mode === "openclaw" ? "OpenClaw · AI 开发" : mode || "模式未知"; }
  function renderMeta() {
    const provider = state.meta?.provider; const simulation = provider?.mode === "simulation";
    $("provider-label").textContent = modeLabel(provider?.mode); $("provider-badge").classList.toggle("simulation", simulation); $("provider-badge").classList.remove("error");
    $("mode-hint").replaceChildren(el("span", "status-dot"), document.createTextNode(simulation ? "规则模拟仅验证流程，不进行 AI 编码" : "通过 OpenClaw 协作生成代码与评审"));
    $("create-job").disabled = state.creating || !provider;
  }
  function renderRepositoryOptions() {
    const selected = $("job-repository").value;
    const none = el("option", "", "不使用本地代码库 · 可直接开始"); none.value = ""; $("job-repository").replaceChildren(none);
    for (const repository of state.repositories) { const option = el("option", "", repository.name); option.value = repository.id; $("job-repository").append(option); }
    if (state.repositories.some((repository) => repository.id === selected)) $("job-repository").value = selected;
    $("repo-count").textContent = state.repositories.length; updateContext();
  }
  function updateContext() {
    const repository = state.repositories.find((item) => item.id === $("job-repository").value);
    $("context-repository").textContent = repository ? `${repository.name} · ${repository.file_count} 个文件 · 版本 ${repository.revision}` : "导入为可选项。没有代码库，也可直接开始开发。";
  }
  function renderMeetings() {
    const selected = $("job-meeting").value; const none = el("option", "", "直接从需求开始"); none.value = ""; $("job-meeting").replaceChildren(none);
    for (const meeting of state.meetings.filter(x => x.status === "completed")) { const option = el("option", "", `${meeting.provider_mode === "simulation" ? "[模拟] " : ""}${meeting.topic?.slice(0, 70) || meeting.id} · ${statusLabels[meeting.status] || meeting.status}`); option.value = meeting.id; $("job-meeting").append(option); }
    if (state.meetings.some((meeting) => meeting.id === selected)) $("job-meeting").value = selected;
  }
  let jobsTrash = false;
  $("job-trash").addEventListener("click", async () => { try { jobsTrash = !jobsTrash; $("job-trash").textContent = jobsTrash ? "返回任务记录" : "回收站"; state.jobs = await api(`/api/development/jobs?deleted=${jobsTrash}`); renderJobs(); } catch(e) { notice(e.message, true); } });
  function renderJobs() {
    $("job-list").replaceChildren();
    if (!state.jobs.length) $("job-list").append(el("p", "empty-small", "从一个开发需求开始。任务记录会保存在这里。"));
    for (const job of state.jobs) {
      const button = el("button", `job-history-item${job.id === state.jobId ? " selected" : ""}`); button.type = "button"; button.title = job.task || job.id; button.setAttribute("aria-pressed", String(job.id === state.jobId));
      button.append(el("strong", "", job.task || "开发任务")); const meta = el("span", "job-history-meta"); meta.append(el("span", "status-dot"), document.createTextNode(`${statusLabels[job.status] || job.status}${job.provider_mode === "simulation" ? " · 模拟" : ""}`)); button.append(meta); button.addEventListener("click", () => selectJob(job.id)); const row = el("div", "history-row"); row.append(button);
      const remove = el("button", "history-remove", jobsTrash ? "恢复" : "删除"); remove.type = "button"; remove.disabled = !terminal.has(job.status); remove.title = remove.disabled ? "请先停止任务" : "仅移入回收站，保留工程文件";
      remove.addEventListener("click", async () => { remove.disabled = true; try { await api(`/api/development/jobs/${job.id}/visibility?deleted=${!jobsTrash}`, {method:"POST"}); if (state.jobId === job.id) newJob(); state.jobs = await api(`/api/development/jobs?deleted=${jobsTrash}`); renderJobs(); } catch(e) { notice(e.message, true); remove.disabled = false; } }); row.append(remove); $("job-list").append(row);
    }
    const picker = $("job-picker"); if (picker) { const empty = el("option", "", "任务记录"); empty.value = ""; picker.replaceChildren(empty); for (const job of state.jobs) { const option = el("option", "", `${statusLabels[job.status] || job.status} · ${(job.task || job.id).slice(0, 42)}`); option.value = job.id; picker.append(option); } picker.value = state.jobId || ""; }
  }
  function updateHistory(job) { const index = state.jobs.findIndex((item) => item.id === job.id); if (index < 0) state.jobs.unshift(job); else state.jobs[index] = job; renderJobs(); }
  function selectTab(name) {
    for (const tab of ["code", "review", "events"]) { const active = tab === name; $("tab-" + tab).classList.toggle("active", active); $("tab-" + tab).setAttribute("aria-selected", String(active)); $("tab-" + tab).tabIndex = active ? 0 : -1; $("panel-" + tab).hidden = !active; }
  }
  function filesOf(job) { return Array.isArray(job?.files) ? job.files : []; }
  function renderFiles(job) {
    const files = filesOf(job); $("file-count").textContent = files.length; $("code-empty").hidden = files.length > 0; $("code-browser").hidden = files.length === 0; $("file-list").replaceChildren();
    if (!files.some((file) => file.path === state.selectedFile)) state.selectedFile = files[0]?.path || null;
    for (const file of files) {
      const button = el("button", "file-item" + (file.path === state.selectedFile ? " active" : ""), file.path); button.type = "button"; button.title = file.path; button.setAttribute("aria-pressed", String(file.path === state.selectedFile)); button.addEventListener("click", () => { state.selectedFile = file.path; renderFiles(state.job); }); $("file-list").append(button);
    }
    const file = files.find((item) => item.path === state.selectedFile); $("current-file").textContent = file?.path || ""; $("code-content").textContent = file?.content || "";
  }
  function renderReview(job) {
    const review = job.review; $("review-summary").replaceChildren();
    if (review) { $("review-summary").append(el("strong", "", review.approved ? "评审通过" : "需要开发者确认"), el("p", "", review.summary || "暂无评审摘要。")); } else $("review-summary").append(el("p", "muted", "评审结果尚未生成。"));
    $("review-issues").replaceChildren();
    for (const issue of review?.issues || []) { const row = el("li", "warning"); row.textContent = typeof issue === "string" ? issue : [issue.path, issue.message || issue.description || issue.title || detailText(issue)].filter(Boolean).join("\n"); $("review-issues").append(row); }
    const checks = Array.isArray(job.checks) ? job.checks : []; $("check-count").textContent = checks.length + (review?.issues?.length || 0); $("checks").replaceChildren();
    if (!checks.length) $("checks").append(el("li", "", "暂无静态检查记录。"));
    for (const check of checks) { const level = ["error", "warning"].includes(check.level) ? check.level : ""; const row = el("li", level); if (check.path) row.append(el("span", "check-path", check.path)); row.append(document.createTextNode(check.message || detailText(check))); $("checks").append(row); }
  }
  function renderEvents(job) {
    const events = Array.isArray(job.events) ? job.events : []; $("event-count").textContent = events.length; $("event-list").replaceChildren();
    if (!events.length) $("event-list").append(el("li", "muted", "任务已提交，等待运行记录。"));
    for (const event of events) { const item = el("li"); const time = el("time", "", shortDate(event.created_at)); if (event.created_at) time.dateTime = event.created_at; item.append(el("strong", "", phaseLabels[event.phase] || event.phase || "运行记录"), time, el("p", "", event.message || "")); $("event-list").append(item); }
  }
  function renderJob(job) {
    const oldStatus = state.job?.status; state.job = job; $("job-output").hidden = false; $("job-output").classList.remove("loading"); $("job-task").textContent = job.task;
    $("job-status").textContent = statusLabels[job.status] || job.status; $("job-status").className = "pill" + (["needs_review", "interrupted", "cancelled"].includes(job.status) ? " warning" : job.status === "failed" ? " error" : "");
    $("job-mode-warning").hidden = job.provider_mode !== "simulation"; $("job-mode-warning").textContent = "这是规则模拟生成的示例工程，仅用于验证工作流程，不是 AI 编码成果，也不代表已经通过中国版游戏环境验证。";
    $("job-meta").replaceChildren(...[modeLabel(job.provider_mode), job.runtime === "python3" ? "Python 3" : "Python 2.7", nameForRepository(job.repository_id), shortDate(job.created_at)].filter(Boolean).map((value) => el("span", "", value)));
    $("job-error").hidden = !job.error; $("job-error").textContent = job.error || "";
    const hasFiles = filesOf(job).length > 0 && terminal.has(job.status); $("download-job").hidden = !hasFiles; $("download-job").href = `/api/development/jobs/${encodeURIComponent(job.id)}/download`; $("open-vscode").hidden = !job.workspace_path || !hasFiles; $("cancel-job").hidden = terminal.has(job.status); $("cancel-job").disabled = false;
    $("review-learning").hidden = !job.repository_id || !job.learning_candidate_id;
    renderFiles(job); renderReview(job); renderEvents(job); updateHistory(job);
    let extra = document.getElementById("job-evidence"); if (!extra) { extra = el("details", "search-result"); extra.id = "job-evidence"; $("job-output").append(extra); } extra.replaceChildren(el("summary", "", "变更差异、假设与调用统计"), el("p", "", job.summary || "等待代码摘要"), el("p", "field-help", `模型调用 ${job.metrics?.model_calls ?? 0} 次 · 耗时 ${((job.metrics?.elapsed_ms || 0)/1000).toFixed(1)} 秒`), el("pre", "", job.diff || "暂无文件差异")); for (const text of [...(job.assumptions || []), ...(job.api_evidence || [])]) extra.append(el("p", "field-help", text));
    if (oldStatus && oldStatus !== job.status) $("live-status").textContent = `当前任务：${statusLabels[job.status] || job.status}`;
  }
  async function selectJob(id, scroll = true) {
    const version = ++state.jobVersion; state.jobId = id; state.job = null; state.selectedFile = null; switchView("development"); renderJobs(); $("job-output").hidden = false; $("job-output").classList.add("loading"); $("job-error").hidden = true;
    try { const job = await api(`/api/development/jobs/${encodeURIComponent(id)}`); if (version !== state.jobVersion) return; renderJob(job); history.replaceState(null, "", `#job=${encodeURIComponent(id)}`); if (scroll) $("job-output").scrollIntoView({ behavior: "smooth", block: "start" }); }
    catch (error) { if (version === state.jobVersion) { $("job-output").classList.remove("loading"); showError("job-error", error); notice(error.message, true); } }
  }
  function newJob() { ++state.jobVersion; state.jobId = null; state.job = null; state.selectedFile = null; $("job-output").hidden = true; $("job-form-error").hidden = true; history.replaceState(null, "", location.pathname); switchView("development"); renderJobs(); $("task").focus(); $("job-form").scrollIntoView({ behavior: "smooth", block: "start" }); }
  function renderRepositories() {
    renderRepositoryOptions(); $("repository-list").replaceChildren();
    if (!state.repositories.length) $("repository-list").append(el("p", "empty-small", "还没有参考代码库。你可以直接在开发工作台编写需求，之后再导入工程。"));
    for (const repository of state.repositories) { const button = el("button", "repository-row" + (repository.id === state.repository?.id ? " selected" : "")); button.type = "button"; button.setAttribute("aria-pressed", String(repository.id === state.repository?.id)); button.append(el("strong", "", repository.name), el("small", "", repository.source_type === "local" ? repository.source_path : "ZIP 本地快照"), el("span", "repository-row-meta", `${repository.file_count} 个文件 · ${repository.chunk_count} 个片段 · 版本 ${repository.revision}`)); button.addEventListener("click", () => selectRepository(repository.id)); $("repository-list").append(button); }
  }
  async function refreshRepositories() { state.repositories = await api("/api/repositories"); renderRepositories(); }
  function enableRepositoryInputs(enabled) { for (const id of ["search-query", "search-submit", "feedback-title", "feedback-content", "feedback-evidence", "feedback-accepted", "feedback-submit"]) $(id).disabled = !enabled; }
  function renderRepository(repository) {
    state.repository = repository; $("repository-title").textContent = repository.name; $("repository-description").textContent = repository.source_type === "local" ? repository.source_path : "已上传的 ZIP 源码快照。更新源码后，重新上传可创建新的参考代码库。"; $("repository-metrics").replaceChildren();
    for (const [value, label] of [[repository.file_count, "源文件"], [repository.chunk_count, "检索片段"], [repository.revision, "索引版本"], [bytes(repository.total_bytes), "文本大小"]]) { const metric = el("span"); metric.append(el("strong", "", value), document.createTextNode(label)); $("repository-metrics").append(metric); }
    $("reindex").hidden = false; enableRepositoryInputs(true); renderRepositories();
  }
  function renderFeedback() {
    $("feedback-count").textContent = state.feedback.length; $("feedback-list").replaceChildren();
    if (!state.feedback.length) $("feedback-list").append(el("p", "empty-small", "暂无经验记录。真实修正与验证结论都可以成为下一次开发的依据。"));
    for (const feedback of state.feedback) { const details = el("details", "feedback-entry" + (feedback.accepted ? " accepted" : "")); const summary = el("summary"); summary.append(el("strong", "", feedback.title), el("small", "", feedback.accepted ? "已采纳" : "待验证")); details.append(summary, el("p", "", feedback.content)); if (feedback.evidence) details.append(el("p", "evidence", `依据：${detailText(feedback.evidence)}`)); details.append(el("p", "evidence", `版本 ${feedback.revision} · ${shortDate(feedback.created_at)}`)); if (!feedback.accepted) { const use = el("button", "text-button", "载入并验证此经验 ↗"); use.type = "button"; use.addEventListener("click", () => loadCandidate(feedback)); details.append(use); } const toggle = el("button", "text-button", feedback.accepted ? "撤销采纳" : "采纳此经验"); toggle.type = "button"; toggle.addEventListener("click", async () => { toggle.disabled = true; try { const evidence = $("feedback-evidence").value.trim() || feedback.evidence; if (!feedback.accepted && !evidence) throw new Error("请先在验证依据中填写实际检查结果。"); await api(`/api/repositories/${state.repository.id}/feedback/${feedback.id}`, {method:"PATCH",body:{accepted:!feedback.accepted,evidence}}); state.feedback = await api(`/api/repositories/${state.repository.id}/feedback`); renderFeedback(); notice(feedback.accepted ? "已撤销，后续检索不再使用此条目。" : "已采纳，后续任务可检索此经验。"); } catch(error) {notice(error.message,true); toggle.disabled=false;} }); details.append(toggle); $("feedback-list").append(details); }
  }
  function loadCandidate(feedback) { $("feedback-title").value = feedback.title || ""; $("feedback-content").value = feedback.content || ""; $("feedback-evidence").value = detailText(feedback.evidence); $("feedback-accepted").checked = false; $("learning-candidate").textContent = `已载入候选经验 ${feedback.id}。请补充实际验证依据，并主动勾选采纳后保存为新版本记录。`; $("learning-candidate").hidden = false; $("feedback-title").focus(); }
  async function selectRepository(id) {
    const version = ++state.repositoryVersion; ++state.searchVersion; $("repository-detail").classList.add("loading"); $("feedback-form").classList.add("loading"); enableRepositoryInputs(false); $("search-results").replaceChildren(); $("feedback-form").reset(); $("feedback-error").hidden = true; $("learning-candidate").hidden = true;
    try { const [repository, feedback] = await Promise.all([api(`/api/repositories/${encodeURIComponent(id)}`), api(`/api/repositories/${encodeURIComponent(id)}/feedback`)]); if (version !== state.repositoryVersion) return; state.feedback = feedback; renderRepository(repository); renderFeedback(); }
    catch (error) { if (version === state.repositoryVersion) notice(error.message, true); }
    finally { if (version === state.repositoryVersion) { $("repository-detail").classList.remove("loading"); $("feedback-form").classList.remove("loading"); } }
  }
  function updateImportMode(mode) { state.importMode = mode; const zip = mode === "zip"; $("import-path-tab").classList.toggle("active", !zip); $("import-zip-tab").classList.toggle("active", zip); $("import-path-tab").setAttribute("aria-pressed", String(!zip)); $("import-zip-tab").setAttribute("aria-pressed", String(zip)); $("path-input-group").hidden = zip; $("zip-input-group").hidden = !zip; $("repository-path").disabled = zip; $("repository-path").required = !zip; $("repository-zip").disabled = !zip; $("repository-zip").required = zip; $("import-error").hidden = true; }
  function setImportBusy(busy) { $("import-submit").disabled = busy; $("import-path-tab").disabled = busy; $("import-zip-tab").disabled = busy; $("import-submit").textContent = busy ? "正在导入与索引…" : "导入并索引 ↗"; }
  async function bootstrap() {
    const results = await Promise.allSettled([api("/api/meta"), api(`/api/development/jobs?deleted=${jobsTrash}`), api("/api/repositories"), api("/api/meetings")]);
    if (results[0].status === "fulfilled") { state.meta = results[0].value; renderMeta(); } else { $("provider-label").textContent = "本地服务连接失败"; $("provider-badge").classList.add("error"); }
    if (results[1].status === "fulfilled") { state.jobs = results[1].value; renderJobs(); } else $("job-list").replaceChildren(el("p", "empty-small", "任务列表加载失败，可稍后刷新页面重试。"));
    if (results[2].status === "fulfilled") { state.repositories = results[2].value; renderRepositories(); }
    if (results[3].status === "fulfilled") { state.meetings = results[3].value; renderMeetings(); }
    const failures = results.filter((result) => result.status === "rejected"); if (failures.length) notice(`部分数据未能读取：${failures.map((result) => result.reason.message).join("；")}`, true);
    state.booted = true; const match = location.hash.match(/^#job=([a-zA-Z0-9_-]+)$/); if (match && !state.jobId) await selectJob(match[1], false);
  }
  async function poll() {
    if (!state.booted || state.pollBusy || document.hidden) return; state.pollBusy = true;
    try {
      if (state.jobId && (!state.job || !terminal.has(state.job.status))) { const id = state.jobId; const version = state.jobVersion; const job = await api(`/api/development/jobs/${encodeURIComponent(id)}`); if (id === state.jobId && version === state.jobVersion) renderJob(job); }
      if (++state.listPoll % 4 === 0) { state.jobs = await api(`/api/development/jobs?deleted=${jobsTrash}`); renderJobs(); }
    } catch (error) { notice(`自动刷新暂时失败，稍后会重试。${error.message}`, true); }
    finally { state.pollBusy = false; }
  }
  $("nav-development").addEventListener("click", () => switchView("development")); $("nav-knowledge").addEventListener("click", () => switchView("knowledge")); $("manage-repositories").addEventListener("click", () => { switchView("knowledge"); const id = $("job-repository").value; if (id) selectRepository(id); }); $("new-job").addEventListener("click", newJob); $("notice-close").addEventListener("click", () => { $("notice").hidden = true; }); $("job-repository").addEventListener("change", updateContext);
  $("task").addEventListener("input", () => { $("task-count").textContent = `${$("task").value.length} / 20000`; });
  for (const id of ["runtime", "max-repairs"]) $(id).addEventListener("change", () => { $("runtime-summary").textContent = `${$("runtime").value === "python2" ? "Python 2.7" : "Python 3"} · 最多修复 ${$("max-repairs").value} 次`; });
  $("job-form").addEventListener("submit", async (event) => {
    if ($("job-meeting").value) { event.preventDefault(); switchView("roundtable"); window.dispatchEvent(new CustomEvent("sparkcraft:open-meeting", {detail:{id:$("job-meeting").value}})); return; }
    event.preventDefault(); if (state.creating) return; const task = $("task").value.trim(); if (!task) { $("task").focus(); return; } state.creating = true; $("create-job").disabled = true; $("create-job").textContent = "正在提交…"; $("job-form-error").hidden = true;
    try { const meeting = await api("/api/meetings", {method:"POST",body:{topic:task,constraints:$("brief-mode").value === "design" ? "用户已提供完整策划，请在保留原意的前提下核对实现与数值，未经人工确认不得制作。" : "用户仅有想法，请先完善玩法、数值和制作范围，未经人工确认不得制作。",max_rounds:Number($("rt-rounds").value)}}); switchView("roundtable"); window.dispatchEvent(new CustomEvent("sparkcraft:select-meeting",{detail:{id:meeting.id}})); notice("已进入策划圆桌，讨论结果由你审核。"); }
    catch (error) { showError("job-form-error", error); } finally { state.creating=false; $("create-job").textContent="进入策划圆桌 ↗"; $("create-job").disabled=!state.meta?.provider; }
  });
  for (const name of ["code", "review", "events"]) {
    $("tab-" + name).addEventListener("click", () => selectTab(name));
    $("tab-" + name).addEventListener("keydown", (event) => { const names = ["code", "review", "events"]; let index = names.indexOf(name); if (event.key === "ArrowRight") index = (index + 1) % names.length; else if (event.key === "ArrowLeft") index = (index + names.length - 1) % names.length; else if (event.key === "Home") index = 0; else if (event.key === "End") index = 2; else return; event.preventDefault(); selectTab(names[index]); $("tab-" + names[index]).focus(); });
  }
  $("cancel-job").addEventListener("click", async () => { const id = state.jobId; const version = state.jobVersion; if (!id) return; $("cancel-job").disabled = true; try { const job = await api(`/api/development/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }); if (version === state.jobVersion) renderJob(job); } catch (error) { notice(error.message, true); } finally { $("cancel-job").disabled = false; } });
  $("open-vscode").addEventListener("click", async () => { const id = state.jobId; if (!id) return; $("open-vscode").disabled = true; try { const result = await api(`/api/development/jobs/${encodeURIComponent(id)}/open-vscode`, { method: "POST" }); notice(result.message || "已请求在 Spark 本机 VS Code 中打开生成工程。"); } catch (error) { notice(error.message, true); } finally { $("open-vscode").disabled = false; } });
  $("copy-code").addEventListener("click", async () => { const content = $("code-content").textContent; try { if (!navigator.clipboard?.writeText) throw new Error("当前浏览器不支持复制，请选中代码后手动复制。"); await navigator.clipboard.writeText(content); notice("当前文件代码已复制。"); } catch (error) { notice(error.message || "复制失败，请选中代码后手动复制。", true); } });
  $("import-path-tab").addEventListener("click", () => updateImportMode("path")); $("import-zip-tab").addEventListener("click", () => updateImportMode("zip")); $("repository-zip").addEventListener("change", () => { $("zip-label").textContent = $("repository-zip").files[0]?.name || "选择本地代码库 ZIP"; });
  $("import-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const name = $("repository-name").value.trim(); $("import-error").hidden = true; setImportBusy(true);
    try { let repository; if (state.importMode === "zip") { const file = $("repository-zip").files[0]; if (!file) throw new Error("请选择代码库 ZIP 文件。"); if (file.size > 20 * 1024 * 1024) throw new Error("ZIP 文件超过 20 MiB，请移除构建产物与依赖后重试。"); repository = await api(`/api/repositories/upload?name=${encodeURIComponent(name || file.name.replace(/\.zip$/i, ""))}`, { method: "POST", body: file, raw: true, timeout: 120000 }); } else { const path = $("repository-path").value.trim(); if (!path.startsWith("/")) throw new Error("请填写 Spark 本机上的绝对目录路径。"); repository = await api("/api/repositories/import", { method: "POST", body: { path, name: name || null }, timeout: 120000 }); } await refreshRepositories(); await selectRepository(repository.id); $("job-repository").value = repository.id; updateContext(); notice(`已导入 ${repository.name}，索引 ${repository.file_count} 个文件。`); }
    catch (error) { showError("import-error", error); } finally { setImportBusy(false); }
  });
  $("refresh-repositories").addEventListener("click", async () => { $("refresh-repositories").disabled = true; try { await refreshRepositories(); notice("代码库列表已刷新。"); } catch (error) { notice(error.message, true); } finally { $("refresh-repositories").disabled = false; } });
  $("reindex").addEventListener("click", async () => { const repository = state.repository; const version = state.repositoryVersion; if (!repository) return; $("reindex").disabled = true; $("reindex").textContent = "索引中…"; try { const updated = await api(`/api/repositories/${encodeURIComponent(repository.id)}/reindex`, { method: "POST", timeout: 120000 }); await refreshRepositories(); if (version === state.repositoryVersion) renderRepository(updated); notice(`索引已更新至版本 ${updated.revision}。`); } catch (error) { notice(error.message, true); } finally { $("reindex").disabled = false; $("reindex").textContent = "重新索引"; } });
  $("search-form").addEventListener("submit", async (event) => { event.preventDefault(); if (!state.repository) return; const query = $("search-query").value.trim(); if (!query) return; const version = ++state.searchVersion; const repositoryVersion = state.repositoryVersion; $("search-submit").disabled = true; $("search-submit").textContent = "检索中"; $("search-results").replaceChildren(el("p", "empty-small", "正在检索本地源码和已采纳经验…"));
    try { const hits = await api(`/api/repositories/${encodeURIComponent(state.repository.id)}/search?q=${encodeURIComponent(query)}`); if (version !== state.searchVersion || repositoryVersion !== state.repositoryVersion) return; $("search-results").replaceChildren(); if (!hits.length) $("search-results").append(el("p", "empty-small", "没有找到匹配内容。尝试更具体的 API、事件名或功能关键词。")); for (const hit of hits) { const details = el("details", "search-result"); const summary = el("summary", "", `${hit.path}${hit.start_line ? `:${hit.start_line}–${hit.end_line}` : ""}`); summary.append(el("span", "", hit.source === "feedback" ? "已采纳经验" : "工程源码")); details.append(summary, el("pre", "", hit.content)); if (hit.evidence) details.append(el("p", "field-help", `依据：${detailText(hit.evidence)}`)); $("search-results").append(details); } }
    catch (error) { if (version === state.searchVersion) $("search-results").replaceChildren(el("p", "form-error", error.message)); } finally { if (version === state.searchVersion) { $("search-submit").disabled = !state.repository; $("search-submit").textContent = "搜索"; } }
  });
  $("feedback-form").addEventListener("submit", async (event) => { event.preventDefault(); const repository = state.repository; const version = state.repositoryVersion; if (!repository || state.feedbackBusy) return; $("feedback-error").hidden = true; state.feedbackBusy = true; $("feedback-submit").disabled = true; $("feedback-submit").textContent = "正在保存…";
    try { await api(`/api/repositories/${encodeURIComponent(repository.id)}/feedback`, { method: "POST", body: { title: $("feedback-title").value.trim(), content: $("feedback-content").value.trim(), accepted: $("feedback-accepted").checked, evidence: $("feedback-evidence").value.trim() } }); const feedback = await api(`/api/repositories/${encodeURIComponent(repository.id)}/feedback`); if (version === state.repositoryVersion) { state.feedback = feedback; renderFeedback(); $("feedback-form").reset(); $("learning-candidate").hidden = true; } notice("开发经验已保存。已采纳条目会进入后续检索。"); }
    catch (error) { if (version === state.repositoryVersion) showError("feedback-error", error); } finally { state.feedbackBusy = false; $("feedback-submit").disabled = !state.repository; $("feedback-submit").textContent = "保存开发经验"; }
  });
  $("review-learning").addEventListener("click", async () => { const job = state.job; if (!job?.repository_id) return; switchView("knowledge"); await selectRepository(job.repository_id); if (state.repository?.id !== job.repository_id) return; const candidate = state.feedback.find((feedback) => feedback.id === job.learning_candidate_id); if (candidate) loadCandidate(candidate); else notice("请在经验列表中选择候选条目，补充验证依据后采纳。"); });
  $("job-picker").addEventListener("change", () => { if ($("job-picker").value) selectJob($("job-picker").value); });
  window.addEventListener("hashchange", () => { const match = location.hash.match(/^#job=([a-zA-Z0-9_-]+)$/); if (match && match[1] !== state.jobId) selectJob(match[1], false); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
  bootstrap(); setInterval(poll, 2500);
})();
