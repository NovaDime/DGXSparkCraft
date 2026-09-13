"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const terminal = new Set(["completed", "needs_review", "cancelled", "failed", "interrupted"]);
  const labels = {queued: "等待入席", running: "讨论中", completed: "评审收敛", needs_review: "仍需评审", cancelled: "已停止", failed: "运行失败", interrupted: "运行中断"};
  const phases = {opening: "整理议题", review: "专业评审", synthesis: "主持汇总"};
  const palettes = {
    host: ["主", "#35462a", "#566d3e", "#c9e8a8"],
    planner: ["策", "#253c36", "#3c564b", "#a7d9c8"],
    balance: ["数", "#3c3423", "#625035", "#e1c794"],
    engineer: ["程", "#283b49", "#40566b", "#a9cce8"],
    reviewer: ["审", "#3a3046", "#5b456c", "#d0b8e9"],
  };
  const state = {meta: null, selected: null, meeting: null, history: [], selection: 0, selectionLoading: false, creating: false, historySignature: "", turnIds: new Set(), timelineRound: -1, detailBusy: false};

  function element(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }
  function icon(name, small = false) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", small ? "icon small" : "icon");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(svg.namespaceURI, "use");
    use.setAttribute("href", `#i-${name}`);
    svg.append(use);
    return svg;
  }
  function avatar(roleId) {
    const [letter, background, border, color] = palettes[roleId] || palettes.host;
    const node = element("span", "role-avatar", letter);
    node.setAttribute("aria-hidden", "true");
    node.style.setProperty("--role-bg", background);
    node.style.setProperty("--role-border", border);
    node.style.setProperty("--role-color", color);
    return node;
  }
  function roleName(id) { return state.meta?.roles.find((role) => role.id === id)?.name || id; }
  function timeLabel(value, date = false) {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "—";
    return new Intl.DateTimeFormat("zh-CN", date ? {month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false} : {hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false}).format(parsed);
  }
  function duration(ms) {
    if (typeof ms !== "number" || !Number.isFinite(ms)) return "未提供";
    return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
  }
  function statusLabel(meeting) {
    return meeting.status === "completed" && meeting.provider_mode === "simulation" ? "模拟收敛" : labels[meeting.status] || meeting.status;
  }
  function notice(message, retry = false) {
    $("notice-text").textContent = message;
    $("notice").hidden = false;
    $("notice-retry").hidden = !retry;
  }

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeout || 12000);
    try {
      const response = await fetch(path, {
        method: options.method || "GET", headers: {"Content-Type": "application/json"},
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal, cache: "no-store", credentials: "same-origin",
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = data?.detail;
        const message = Array.isArray(detail) ? detail.map((item) => `${item.loc?.slice(1).join(".") || "输入"}：${item.msg}`).join("；") : typeof detail === "string" ? detail : `服务返回错误（${response.status}）`;
        const error = new Error(message);
        error.status = response.status;
        throw error;
      }
      if (data === null) throw new Error("服务返回了无法识别的数据。");
      $("connection-label").textContent = "本地服务正常";
      $("connection-label").classList.remove("error");
      return data;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("请求超时。创建请求不会自动重发，请先检查会议记录。");
      if (error instanceof TypeError) throw new Error("无法连接本地服务，请确认 Python 圆桌程序仍在运行。");
      throw error;
    } finally { clearTimeout(timer); }
  }

  // All model-supplied text becomes text nodes. Markdown never becomes arbitrary HTML.
  function inline(node, text) {
    const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g;
    let cursor = 0;
    for (const match of text.matchAll(pattern)) {
      node.append(document.createTextNode(text.slice(cursor, match.index)));
      const code = match[0].startsWith("`");
      node.append(element(code ? "code" : "strong", "", match[0].slice(code ? 1 : 2, code ? -1 : -2)));
      cursor = match.index + match[0].length;
    }
    node.append(document.createTextNode(text.slice(cursor)));
  }
  function markdown(text) {
    const root = element("div", "markdown-body");
    const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
    let codeLines = null;
    let list = null;
    for (const line of lines) {
      if (line.trim().startsWith("```")) {
        if (codeLines !== null) {
          const pre = element("pre"); pre.append(element("code", "", codeLines.join("\n"))); root.append(pre); codeLines = null;
        } else { codeLines = []; }
        list = null; continue;
      }
      if (codeLines !== null) { codeLines.push(line); continue; }
      if (!line.trim()) { list = null; continue; }
      const heading = line.match(/^(#{1,4})\s+(.*)$/);
      const item = line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)$/);
      if (heading) { const node = element(`h${heading[1].length}`); inline(node, heading[2]); root.append(node); list = null; }
      else if (/^\s*---+\s*$/.test(line)) { root.append(element("hr")); list = null; }
      else if (item) {
        if (!list) { list = element("ul"); root.append(list); }
        const node = element("li"); inline(node, item[1]); list.append(node);
      } else {
        list = null;
        const quote = line.startsWith(">");
        const node = element(quote ? "blockquote" : "p");
        inline(node, quote ? line.replace(/^>\s?/, "") : line); root.append(node);
      }
    }
    if (codeLines !== null) { const pre = element("pre"); pre.append(element("code", "", codeLines.join("\n"))); root.append(pre); }
    return root;
  }

  function renderHistory() {
    const signature = JSON.stringify([state.selected, state.history]);
    if (signature === state.historySignature) return;
    state.historySignature = signature;
    $("history-count").textContent = state.history.length;
    const fragment = document.createDocumentFragment();
    for (const item of state.history) {
      const button = element("button", `history-item${item.id === state.selected ? " active" : ""}`);
      button.type = "button";
      button.title = item.topic;
      button.setAttribute("aria-current", item.id === state.selected ? "page" : "false");
      button.append(element("span", "history-title", item.topic));
      const meta = element("span", "history-meta");
      meta.append(element("span", `history-dot ${item.status}`), element("span", "", statusLabel(item)));
      if (item.provider_mode === "simulation") meta.append(element("span", "", "· 模拟"));
      const time = element("time", "", timeLabel(item.created_at, true)); time.dateTime = item.created_at;
      meta.append(time); button.append(meta);
      button.addEventListener("click", () => selectMeeting(item.id)); fragment.append(button);
    }
    if (!state.history.length) fragment.append(element("p", "sidebar-empty", "还没有会议。从一个具体玩法开始，记录会保存在这里。"));
    $("history-list").replaceChildren(fragment);
  }

  function renderRoles(meeting = null) {
    if (!state.meta) return;
    const includeReviewer = meeting ? meeting.include_reviewer : $("include-reviewer").checked;
    const roles = state.meta.roles.filter((role) => includeReviewer || role.id !== "reviewer");
    $("role-count").textContent = roles.length;
    const fragment = document.createDocumentFragment();
    for (const role of roles) {
      const button = element("button", `role-card${meeting?.active_role_id === role.id ? " speaking" : ""}`);
      button.type = "button"; button.title = `查看${role.name}的 Skill`;
      button.setAttribute("aria-label", `查看${role.name}的专业技能`);
      button.append(avatar(role.id));
      const copy = element("span", "role-copy");
      const name = element("span", "role-name-line"); name.append(element("strong", "role-name", role.name));
      if (meeting?.active_role_id === role.id) name.append(element("span", "status-dot"));
      copy.append(name, element("span", "role-title", role.title));
      button.append(copy, element("span", "role-skill-arrow", "↗"));
      button.addEventListener("click", () => showSkill(role.skill_id)); fragment.append(button);
    }
    $("roles").replaceChildren(fragment);
  }

  function makeTurn(turn) {
    const root = element("article", "turn"); root.dataset.turnId = turn.id;
    root.append(avatar(turn.role_id));
    const content = element("div", "turn-content");
    const heading = element("div", "turn-heading");
    heading.append(element("strong", "", turn.role_name), element("span", "phase-label", phases[turn.phase] || turn.phase), element("time", "turn-time", timeLabel(turn.created_at)));
    const card = element("div", "turn-card"); card.append(element("p", "turn-summary", turn.summary));
    const footer = element("div", "turn-footer");
    footer.append(element("span", `stance-badge ${turn.stance}`, turn.stance === "approve" ? "本轮认可" : "建议修订"), element("span", "turn-time", duration(turn.elapsed_ms)));
    const skill = turn.provided_skill_id || turn.skill_ids?.[0];
    if (skill) {
      const button = element("button", "skill-chip", `参考 Skill · ${skill}`); button.type = "button";
      button.addEventListener("click", () => showSkill(skill)); footer.append(button);
    }
    card.append(footer);
    const details = element("details", "turn-detail"); details.append(element("summary", "", "查看建议、分歧与依据"));
    const body = element("div", "turn-detail-body");
    if (turn.recommendations?.length) {
      body.append(element("h4", "", "修改建议"));
      const list = element("ul"); turn.recommendations.forEach((text) => list.append(element("li", "", text))); body.append(list);
    }
    for (const issue of turn.concerns || []) { body.append(element("h4", "", issue.title), element("p", "", issue.detail)); }
    if (turn.resolved_issue_ids?.length) body.append(element("p", "", `申请关闭：${turn.resolved_issue_ids.join("、")}。处理结果见分歧记录。`));
    if (turn.proposal && turn.role_id === "host") { body.append(element("h4", "", "本次方案"), markdown(turn.proposal)); }
    body.append(element("p", "", "Skill 引用表示向角色提供了专业指令，不等同于执行过外部工具。"));
    if (turn.skill_sha256) body.append(element("pre", "mono", `Skill SHA-256\n${turn.skill_sha256}`));
    details.append(body); card.append(details); content.append(heading, card); root.append(content); return root;
  }

  function issueCard(issue) {
    const card = element("div", `issue-card${issue.status === "resolved" ? " resolved" : ""}`);
    card.append(element("h3", "issue-title", `${issue.id} · ${issue.title}`), element("p", "issue-detail", issue.detail));
    card.append(element("p", "issue-owner", `${roleName(issue.owner_role_id)} · 第 ${issue.created_round} 轮 · ${ {blocker:"阻断", major:"重要", minor:"一般"}[issue.severity] || issue.severity}`));
    if (issue.resolution) card.append(element("p", "issue-resolution", `复核依据：${issue.resolution}`));
    return card;
  }

  function renderMeeting(meeting) {
    const previous = state.meeting;
    state.meeting = meeting;
    $("meeting-loading").hidden = true;
    $("welcome-view").hidden = true; $("meeting-view").hidden = false;
    $("principles-section").hidden = true; $("issues-section").hidden = false; $("output-section").hidden = false;
    $("breadcrumb-current").textContent = "圆桌评审";
    $("meeting-id").textContent = meeting.id.slice(0, 8);
    const topicChars = Array.from(meeting.topic);
    $("meeting-topic").textContent = topicChars.length > 48 ? `${topicChars.slice(0, 48).join("")}…` : meeting.topic;
    $("meeting-brief").hidden = topicChars.length <= 48;
    $("meeting-topic-full").textContent = meeting.topic;
    $("meeting-mode").textContent = meeting.provider_mode === "simulation" ? "规则模拟 · 非 AI" : "OpenClaw 模型评审";
    $("meeting-status").textContent = statusLabel(meeting);
    $("meeting-status").className = `session-status ${meeting.status}`;
    $("meeting-round").textContent = meeting.current_round ? `第 ${meeting.current_round} / ${meeting.max_rounds} 轮` : "开场准备";
    $("meeting-turns").textContent = `${meeting.turns.length} 次发言`;
    $("turn-tab-count").textContent = meeting.turns.length;
    $("meeting-constraints").hidden = !meeting.constraints; $("meeting-constraints").textContent = meeting.constraints;
    $("cancel-meeting").hidden = terminal.has(meeting.status); $("cancel-meeting").disabled = false;
    const warnings = [];
    if (meeting.provider_mode === "simulation") warnings.push("当前为预设规则模拟，用于验证讨论流程；不是 AI 推理或真实开发成果。");
    if (meeting.error) warnings.push(meeting.error);
    $("meeting-alert").textContent = warnings.join("\n"); $("meeting-alert").hidden = !warnings.length;
    $("report-warning").hidden = false;
    $("report-warning").textContent = meeting.provider_mode === "simulation" ? "模拟记录仅供验证流程，不能作为模型效果、Spark 性能或游戏验收证据。" : "当前内容为模型设计建议，SDK 和游戏行为仍须在实际开发环境验证。";
    if (!previous || previous.id !== meeting.id) {
      $("timeline").replaceChildren(); state.turnIds.clear(); state.timelineRound = -1;
      $("resolved-issues-details").open = false;
      $("meeting-brief").open = false;
    }
    for (const turn of meeting.turns) {
      if (state.turnIds.has(turn.id)) continue;
      if (turn.round !== state.timelineRound) {
        const divider = element("div", "round-divider");
        divider.append(element("span", "", turn.round === 0 ? "OPENING" : `ROUND ${String(turn.round).padStart(2, "0")}`), document.createTextNode(turn.round === 0 ? "主管整理议题" : `第 ${turn.round} 轮 · 专业评审`));
        $("timeline").append(divider); state.timelineRound = turn.round;
      }
      $("timeline").append(makeTurn(turn)); state.turnIds.add(turn.id);
    }
    $("timeline-empty").hidden = meeting.turns.length > 0 || terminal.has(meeting.status);
    $("active-turn").hidden = !meeting.active_role_id || meeting.status !== "running";
    $("active-turn-text").textContent = meeting.active_role_id ? `${roleName(meeting.active_role_id)}${meeting.provider_mode === "simulation" ? "正在运行模拟步骤…" : "正在评审当前方案…"}` : "";
    $("event-count").textContent = meeting.events.length;
    const events = document.createDocumentFragment();
    for (const item of meeting.events) { const line = element("li"); line.append(element("time", "", timeLabel(item.created_at)), element("span", "", item.message)); events.append(line); }
    $("events").replaceChildren(events);
    const open = meeting.issues.filter((item) => item.status === "open");
    const resolved = meeting.issues.filter((item) => item.status === "resolved");
    $("issue-count").textContent = open.length;
    $("issues").replaceChildren(...open.map(issueCard));
    if (!open.length) $("issues").append(element("p", "empty-issues", meeting.status === "completed" ? "已登记分歧全部复核关闭。" : "当前没有已登记的未解决分歧。"));
    $("resolved-issues-details").hidden = !resolved.length;
    $("resolved-issues-summary").textContent = `已处理分歧 · ${resolved.length}`;
    $("resolved-issues-list").replaceChildren(...resolved.map(issueCard));
    const report = meeting.final_report || meeting.proposal;
    $("report-content").replaceChildren(markdown(report)); $("report-empty").hidden = Boolean(report);
    $("report-title").textContent = meeting.status === "completed" ? "评审方案与总结" : terminal.has(meeting.status) ? "当前方案与保留意见" : "讨论中的方案";
    $("report-ready-dot").hidden = !meeting.final_report;
    $("export-md").href = `/api/meetings/${meeting.id}/export?format=markdown`;
    $("export-json").href = `/api/meetings/${meeting.id}/export?format=json`;
    $("output-description").textContent = meeting.status === "completed" ? "当前方案已在本次流程中收敛，完整意见与依据已保存。" : "每轮意见和方案均已保存；未解决问题会随记录一并导出。";
    const metrics = meeting.metrics || {};
    const stats = [[String(metrics.turn_count || 0), "发言次数"], [duration(metrics.total_elapsed_ms), "累计调用耗时"], [metrics.input_tokens == null || metrics.output_tokens == null ? "未报告" : (metrics.input_tokens + metrics.output_tokens).toLocaleString("zh-CN"), "Token 用量"]];
    $("session-metrics").replaceChildren(...stats.map(([value, label]) => { const node = element("span"); node.append(element("strong", "", value), document.createTextNode(label)); return node; }));
    renderRoles(meeting);
    if (!previous || previous.status !== meeting.status) $("screen-reader-status").textContent = statusLabel(meeting);
  }

  function setTab(name, focus = false) {
    for (const tabName of ["discussion", "proposal"]) {
      const active = name === tabName;
      $(`${tabName}-tab`).classList.toggle("active", active); $(`${tabName}-tab`).setAttribute("aria-selected", active ? "true" : "false");
      $(`${tabName}-tab`).tabIndex = active ? 0 : -1; $(`${tabName}-panel`).hidden = !active;
    }
    if (focus) $(`${name}-tab`).focus();
  }
  async function selectMeeting(id, updateHash = true) {
    if (!/^[a-f0-9]{32}$/.test(id)) return;
    const version = ++state.selection; state.selected = id; state.meeting = null; state.selectionLoading = true;
    $("welcome-view").hidden = true; $("meeting-view").hidden = true; $("meeting-loading").hidden = false;
    $("principles-section").hidden = true; $("issues-section").hidden = true; $("output-section").hidden = true;
    if (updateHash) history.replaceState(null, "", `#meeting=${id}`);
    renderHistory();
    $("breadcrumb-current").textContent = "读取会议…";
    try {
      const meeting = await api(`/api/meetings/${id}`);
      if (version !== state.selection) return;
      renderMeeting(meeting); setTab("discussion");
    } catch (error) { if (version === state.selection) { $("meeting-loading").hidden = true; notice(error.message, true); } }
    finally { if (version === state.selection) state.selectionLoading = false; }
  }
  function newMeeting(event) {
    event?.preventDefault(); ++state.selection; state.selected = null; state.meeting = null; state.selectionLoading = false;
    $("meeting-loading").hidden = true;
    history.replaceState(null, "", location.pathname);
    $("welcome-view").hidden = false; $("meeting-view").hidden = true;
    $("principles-section").hidden = false; $("issues-section").hidden = true; $("output-section").hidden = true;
    $("breadcrumb-current").textContent = "新建圆桌";
    renderRoles(); renderHistory(); $("topic").focus();
  }
  function updateCount() { $("topic-count").textContent = `${$("topic").value.length} / 4000`; }

  let dialogVersion = 0;
  function openDialog(title, eyebrow) {
    ++dialogVersion;
    $("dialog-title").textContent = title; $("dialog-eyebrow").textContent = eyebrow;
    $("dialog-content").replaceChildren();
    if (!$("detail-dialog").open) $("detail-dialog").showModal();
    return dialogVersion;
  }
  async function showSkill(id) {
    const version = openDialog("专业技能", "SKILL DETAIL");
    $("dialog-content").append(element("p", "", "正在读取技能…"));
    try {
      const skill = await api(`/api/skills/${encodeURIComponent(id)}`);
      if (version !== dialogVersion || !$("detail-dialog").open) return;
      $("dialog-title").textContent = roleName(state.meta.roles.find((role) => role.skill_id === id)?.id) || skill.name;
      $("dialog-content").replaceChildren(element("p", "", skill.description), markdown(skill.content));
      for (const [name, content] of Object.entries(skill.reference_contents || {})) {
        const details = element("details", "turn-detail"); details.append(element("summary", "", `参考资料 · ${name}`), markdown(content)); $("dialog-content").append(details);
      }
      if (skill.sha256) $("dialog-content").append(element("p", "mono", `SHA-256: ${skill.sha256}`));
    } catch (error) { if (version === dialogVersion) $("dialog-content").replaceChildren(element("p", "", error.message)); }
  }
  function showSettings() {
    const version = openDialog("运行配置", "LOCAL FIRST");
    const provider = state.meta?.provider;
    if (!provider) { $("dialog-content").append(element("p", "", "尚未连接本地服务，请重新连接。")); return; }
    const simulation = provider.mode === "simulation";
    $("dialog-content").append(element("p", "", simulation ? "当前使用预设规则模拟，不加载模型。它可以验证圆桌流程、界面和记录，不能验证真实模型质量。" : "当前选择 OpenClaw 模式。是否使用 Spark 本地模型，由目标 Gateway 的后端配置决定。"));
    const values = element("dl", "config-values");
    for (const [label, value] of [["运行模式", simulation ? "规则模拟" : "OpenClaw"], ["路由入口", provider.model], ["服务地址", provider.base_url], ["推理并发", "1 · 角色按顺序发言"]]) values.append(element("dt", "", label), element("dd", "", value));
    $("dialog-content").append(values);
    const check = element("button", "button button-quiet", "检查连接"); check.type = "button";
    const result = element("p", "config-check-result"); result.setAttribute("role", "status");
    check.addEventListener("click", async () => {
      check.disabled = true; check.textContent = "正在检查…";
      try { const data = await api("/api/provider/check", {method: "POST", timeout: 190000}); if (version === dialogVersion) result.textContent = data.message; }
      catch (error) { if (version === dialogVersion) result.textContent = error.message; }
      finally { check.disabled = false; check.textContent = "检查连接"; }
    });
    $("dialog-content").append(check, result, element("p", "config-hint", "Spark 可访问后，在服务端 .env 配置 Gateway 地址、认证和五个角色 ID，再重启 Python 服务。认证信息不会在网页中显示。连接检查只验证网关，真实角色能力还需单独验收。"));
  }

  async function bootstrap() {
    try {
      const [meta, meetings] = await Promise.all([api("/api/meta"), api("/api/meetings")]);
      state.meta = meta; state.history = meetings;
      $("notice").hidden = true;
      const simulation = meta.provider.mode === "simulation";
      $("mode-label").textContent = simulation ? "规则模拟 · 非 AI" : "OpenClaw 模式";
      $("mode-badge").classList.toggle("real", !simulation);
      $("create-mode-hint").replaceChildren(element("span", "status-dot"), document.createTextNode(simulation ? "预设流程演示，不进行 AI 推理" : "通过 OpenClaw 调用各专业角色"));
      $("max-rounds").replaceChildren();
      for (let number = 1; number <= meta.limits.max_rounds_max; number++) {
        const option = element("option", "", `${number} 轮`); option.value = number; option.selected = number === meta.limits.max_rounds_default; $("max-rounds").append(option);
      }
      $("examples").replaceChildren(...meta.examples.map((example) => {
        const button = element("button", "example-button", example.title); button.type = "button";
        button.addEventListener("click", () => { $("topic").value = example.topic; $("constraints").value = example.constraints; updateCount(); $("form-error").hidden = true; $("topic").focus(); }); return button;
      }));
      $("start-meeting").disabled = state.creating;
      renderRoles(state.meeting); renderHistory();
      const match = location.hash.match(/^#meeting=([a-f0-9]{32})$/);
      if (match && !state.selected) await selectMeeting(match[1], false);
    } catch (error) {
      $("connection-label").textContent = "服务连接失败"; $("connection-label").classList.add("error"); notice(error.message, true);
    }
  }
  async function pollDetails() {
    if (state.selected && !state.selectionLoading && (!state.meeting || !terminal.has(state.meeting.status)) && !state.detailBusy) {
      const id = state.selected; const version = state.selection; state.detailBusy = true;
      try {
        const meeting = await api(`/api/meetings/${id}`);
        if (id === state.selected && version === state.selection && meeting.updated_at !== state.meeting?.updated_at) renderMeeting(meeting);
      } catch (error) { if (id === state.selected) notice(error.message, true); }
      finally { state.detailBusy = false; }
    }
    setTimeout(pollDetails, document.hidden ? 3000 : 900);
  }
  async function pollHistory() {
    if (state.meta) {
      try { state.history = await api("/api/meetings"); renderHistory(); }
      catch (error) { $("connection-label").textContent = "连接已中断"; $("connection-label").classList.add("error"); }
    }
    setTimeout(pollHistory, document.hidden ? 8000 : 3500);
  }

  $("meeting-form").addEventListener("submit", async (event) => {
    event.preventDefault(); if (state.creating || !state.meta) return;
    const topic = $("topic").value.trim(); const constraints = $("constraints").value.trim();
    if (topic.length < 4 || topic.length > 4000 || constraints.length > 4000) { $("form-error").textContent = "请提供至少 4 字的具体议题，议题和约束分别不超过 4000 字。"; $("form-error").hidden = false; return; }
    state.creating = true; $("start-meeting").disabled = true; $("form-error").hidden = true;
    const version = state.selection;
    try {
      const meeting = await api("/api/meetings", {method: "POST", body: {topic, constraints, max_rounds: Number($("max-rounds").value), include_reviewer: $("include-reviewer").checked}});
      state.history = [meeting, ...state.history.filter((item) => item.id !== meeting.id)]; renderHistory();
      if (version === state.selection) { ++state.selection; state.selected = meeting.id; history.replaceState(null, "", `#meeting=${meeting.id}`); renderMeeting(meeting); renderHistory(); setTab("discussion"); }
    } catch (error) { $("form-error").textContent = error.message; $("form-error").hidden = false; }
    finally { state.creating = false; $("start-meeting").disabled = false; }
  });
  $("cancel-meeting").addEventListener("click", async () => {
    const id = state.selected; const version = state.selection; if (!id) return;
    $("cancel-meeting").disabled = true;
    try { const meeting = await api(`/api/meetings/${id}/cancel`, {method: "POST"}); if (id === state.selected && version === state.selection) renderMeeting(meeting); }
    catch (error) { notice(error.message, true); }
    finally { $("cancel-meeting").disabled = false; }
  });
  $("new-meeting").addEventListener("click", newMeeting);
  $("brand-home").addEventListener("click", newMeeting);
  $("topic").addEventListener("input", updateCount);
  $("include-reviewer").addEventListener("change", () => renderRoles());
  $("open-settings").addEventListener("click", showSettings);
  $("mode-badge").addEventListener("click", showSettings);
  $("close-dialog").addEventListener("click", () => $("detail-dialog").close());
  $("detail-dialog").addEventListener("close", () => ++dialogVersion);
  $("dismiss-notice").addEventListener("click", () => { $("notice").hidden = true; });
  $("notice-retry").addEventListener("click", bootstrap);
  $("discussion-tab").addEventListener("click", () => setTab("discussion"));
  $("proposal-tab").addEventListener("click", () => setTab("proposal"));
  $("view-report").addEventListener("click", () => { setTab("proposal", true); $("proposal-panel").scrollIntoView({block: "start", behavior: "smooth"}); });
  for (const name of ["discussion", "proposal"]) $(`${name}-tab`).addEventListener("keydown", (event) => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) { event.preventDefault(); setTab(event.key === "Home" ? "discussion" : event.key === "End" ? "proposal" : name === "discussion" ? "proposal" : "discussion", true); }
  });
  window.addEventListener("hashchange", () => { const match = location.hash.match(/^#meeting=([a-f0-9]{32})$/); if (match) selectMeeting(match[1], false); else newMeeting(); });
  updateCount(); bootstrap(); setTimeout(pollDetails, 900); setTimeout(pollHistory, 3500);
})();
