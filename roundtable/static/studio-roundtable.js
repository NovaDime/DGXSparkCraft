(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const labels = {queued:"排队中",running:"讨论中",completed:"达成共识",needs_review:"仍需评审",failed:"运行失败",cancelled:"已停止",interrupted:"已中断"};
  let roles = [], selected = null, meeting = null, busy = false, version = 0, modelCatalog = [], openedRole = null;
  const node = (tag, cls, text) => { const n = document.createElement(tag); n.className = cls; if (text != null) n.textContent = text; return n; };
  async function api(path, body) {
    const response = await fetch(path, {method:body === undefined ? "GET" : "POST", headers:body === undefined ? {} : {"Content-Type":"application/json"}, body:body === undefined ? undefined : JSON.stringify(body), signal:AbortSignal.timeout(30000)});
    const data = await response.json(); if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `请求失败 (${response.status})`); return data;
  }
  function error(e) { $("rt-form-error").textContent = e.message || "请求失败"; $("rt-form-error").hidden = false; }
  const cloudPanel = node("details", "cloud-panel");
  cloudPanel.innerHTML = '<summary>＋ 接入云端文本模型</summary><form id="cloud-form" autocomplete="off"><label for="cloud-name">服务名称</label><input id="cloud-name" required maxlength="80" placeholder="例如：阶跃星辰 / DeepSeek"><label for="cloud-url">API 基础地址（HTTPS）</label><input id="cloud-url" type="url" required placeholder="https://api.stepfun.com/v1"><label for="cloud-model">文本模型 ID</label><input id="cloud-model" required maxlength="200" placeholder="填写服务商提供的文本模型 ID"><label for="cloud-key">API Key</label><input id="cloud-key" type="password" required autocomplete="new-password" maxlength="4096" placeholder="仅保存至此设备的私密配置"><p class="field-help">支持 OpenAI 兼容 Chat Completions 接口。分配云端模型后，该角色的技能、议题及方案将发送至你填写的服务。连接测试会发送一条简短测试消息。</p><button class="button secondary" id="cloud-save">保存云端连接</button></form><p id="cloud-message" role="status"></p><button type="button" id="cloud-check" class="button secondary" hidden>测试新连接</button>';
  $("agent-dialog").append(cloudPanel);
  $("agent-dialog").setAttribute("aria-labelledby", "agent-name");
  let newCloudId = null;
  $("cloud-form").addEventListener("submit", async event => {
    event.preventDefault(); $("cloud-save").disabled = true; $("cloud-message").textContent = "正在保存…";
    const key = $("cloud-key").value; $("cloud-key").value = "";
    try {
      const data = await api("/api/cloud-models", {name:$("cloud-name").value, base_url:$("cloud-url").value, model:$("cloud-model").value, api_key:key});
      roles = data.roles; modelCatalog = data.models; newCloudId = data.id;
      const option = node("option", "", modelCatalog.find(m=>m.id===newCloudId).name); option.value = newCloudId; $("agent-model").append(option); $("agent-model").value = newCloudId;
      $("cloud-message").textContent = "已保存。可测试连接，再点击上方保存角色模型完成分配。"; $("cloud-check").hidden = false;
    } catch(e) { $("cloud-message").textContent = e.message; } finally { $("cloud-save").disabled = false; }
  });
  $("cloud-check").addEventListener("click", async () => { if (!newCloudId) return; $("cloud-check").disabled = true; try { const result = await api(`/api/cloud-models/${newCloudId.split("/")[1]}/check`, {}); $("cloud-message").textContent = result.message; } catch(e) { $("cloud-message").textContent = e.message; } finally { $("cloud-check").disabled = false; } });
  function renderRoles() {
    const signature = JSON.stringify([roles, meeting?.active_role_id || null]);
    if ($("rt-roles").dataset.animationSignature === signature) return;
    $("rt-roles").dataset.animationSignature = signature;
    $("rt-roles").replaceChildren();
    for (const role of roles) {
      const speaking = meeting?.active_role_id === role.id;
      const card = node("button", `rt-role workstation ${role.id}${speaking ? " speaking" : ""}`); card.type = "button";
      card.setAttribute("aria-label", `${role.name}，${role.title}，查看和更换模型`);
      const stage = node("div", "pixel-stage"); stage.setAttribute("aria-hidden", "true");
      stage.append(node("span", "desk-shadow"), node("span", "desk"), node("span", "monitor"), shrimp(role.id), node("span", "desk-cup"), node("span", "desk-keyboard"));
      const prop = node("span", `work-prop prop-${role.id}`);
      for (let i = 0; i < 3; i++) prop.append(node("i", ""));
      stage.append(prop, node("span", `work-spark spark-${role.id}`, {host:"…",planner:"✦",balance:"＋",engineer:"<> Core",audio:"♫",reviewer:"✓"}[role.id]));
      card.append(node("span", "agent-bubble", speaking ? "正在推敲…" : {host:"把好点子连起来",planner:"灵感正在萌芽",balance:"每个数值都有意义",engineer:"让逻辑运转起来",audio:"听见新的可能",reviewer:"再检查一个边界"}[role.id]), stage, node("strong", "", role.name), node("small", "", role.title), node("span", "agent-state", speaking ? "● 正在发言" : "◦ 查看模型"));
      card.addEventListener("click", () => openAgent(role)); $("rt-roles").append(card);
    }
    $("office-status").textContent = meeting?.active_role_id ? `${roles.find(r=>r.id===meeting.active_role_id)?.name || "成员"} 正在发言` : "点击伙伴，查看模型与职责";
  }
  function shrimp(id) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"); svg.setAttribute("viewBox", "0 0 64 64"); svg.setAttribute("class", "pixel-shrimp"); svg.setAttribute("shape-rendering", "crispEdges");
    const colors = {host:"#b5c6ed",planner:"#99dca8",balance:"#ebcf78",engineer:"#8ecbe2",audio:"#cdabed",reviewer:"#b6c9ae"};
    const outfits = {
      host:'<path fill="#273b56" d="M18 16h30v5H18zM24 7h19v10H24z"/><path fill="#ddc375" d="M24 13h19v3H24zM31 38h5v14h-5z"/>',
      planner:'<path fill="#58784d" d="M18 14h30v6H18zM24 9h18v5H24z"/><path fill="#ffe8b3" d="M42 5h4v11h-4z"/>',
      balance:'<path fill="#574344" d="M21 24h12v8H21zM36 24h12v8H36zM33 26h3v3h-3z"/><path fill="#d0eff2" d="M24 26h6v3h-6zM39 26h6v3h-6z"/>',
      engineer:'<path fill="#e3b951" d="M18 14h33v6H18zM23 8h23v7H23z"/><path fill="#ffe298" d="M31 6h6v13h-6z"/>',
      audio:'<path fill="#483c68" d="M18 17h5v21h-5zM47 17h5v21h-5zM23 12h24v5H23z"/><path fill="#cdb5f2" d="M16 26h9v12h-9zM45 26h9v12h-9z"/>',
      reviewer:'<path fill="#d3e3cc" d="M19 14h29v7H19zM24 10h19v5H24z"/><path fill="#294234" d="M36 24h11v10H36zM39 27h5v4h-5z"/>'
    };
    svg.innerHTML = `<path fill="#7e4541" d="M16 35h34v14H16zM12 39h9v13h-9zM7 46h13v9H7zM3 43h7v6H3zM6 54h11v5H6z"/><path fill="#f59c7d" d="M23 17h22v5H23zM18 22h32v17H18zM22 39h24v8H22zM15 43h9v9h-9zM9 50h13v6H9z"/><path fill="#ffc2a0" d="M24 20h19v4H24zM20 25h5v9h-5zM14 46h5v5h-5z"/><path fill="#442b34" d="M27 24h4v7h-4zM41 24h4v7h-4zM33 34h7v3h-7z"/><path fill="#fff4db" d="M27 24h2v2h-2zM41 24h2v2h-2z"/><path fill="#ef9b7a" d="M24 11h3v8h-3zM18 8h9v3h-9zM14 4h6v4h-6zM43 11h3v8h-3zM46 7h9v4h-9zM53 3h5v4h-5z"/><path fill="${colors[id] || '#a2cfac'}" d="M23 38h23v14H23zM19 40h5v9h-5zM45 40h6v9h-6z"/><path fill="#f8b295" d="M18 48h8v5h-8zM44 48h9v5h-9z"/><path fill="#633f3b" d="M25 52h6v6h-6zM38 52h6v6h-6z"/>${outfits[id] || ""}`;
    const tail = document.createElementNS("http://www.w3.org/2000/svg", "path");
    tail.setAttribute("fill", "#ef9479"); tail.setAttribute("d", "M45 40h9v-5h5V24h-4v-6h7v19h-4v8H45zM55 18h-5v-5h5zM58 15h5v-5h-5z"); svg.insertBefore(tail, svg.firstChild);
    const whiskers = document.createElementNS("http://www.w3.org/2000/svg", "path");
    whiskers.setAttribute("fill", "#ffbd96"); whiskers.setAttribute("d", "M20 31H7v-2H1v-2h8v2h11zM19 34H6v2H0v2h8v-2h11z"); svg.append(whiskers);
    svg.classList.add(`shrimp-${id}`);
    const hands = [...svg.querySelectorAll("path")].find(p => p.getAttribute("d") === "M18 48h8v5h-8zM44 48h9v5h-9z");
    if (hands) hands.setAttribute("class", "shrimp-hands");
    return svg;
  }
  function openAgent(role) {
    openedRole = role; $("agent-name").textContent = role.name; $("agent-description").textContent = role.description;
    $("agent-current").textContent = modelCatalog.find(m=>m.id===role.model)?.name || role.model || "Gateway 默认模型"; $("agent-portrait").replaceChildren(shrimp(role.id));
    $("agent-model").replaceChildren(); const defaultOption = node("option", "", "跟随此 Agent 的默认模型"); defaultOption.value = ""; $("agent-model").append(defaultOption);
    for (const m of modelCatalog) { const option = node("option", "", m.name + " · " + m.id); option.value = m.id; $("agent-model").append(option); }
    $("agent-model").value = role.override || ""; $("agent-message").textContent = ""; $("cloud-key").value = ""; $("agent-dialog").showModal();
  }
  $("agent-model-form").addEventListener("submit", async event => { event.preventDefault(); if (!openedRole) return; $("agent-save").disabled = true; try { const data = await api(`/api/agents/${openedRole.id}/model`, {model:$("agent-model").value}); roles = data.roles; modelCatalog = data.models; openedRole = roles.find(r=>r.id===openedRole.id); $("agent-current").textContent = openedRole.model; $("agent-message").textContent = "已保存，将在新会议中使用。"; renderRoles(); } catch(e) { $("agent-message").textContent = e.message; } finally { $("agent-save").disabled = false; } });
  let meetingsTrash = false;
  $("rt-trash").addEventListener("click", () => { meetingsTrash = !meetingsTrash; $("rt-trash").textContent = meetingsTrash ? "返回会议记录" : "回收站"; historyList().catch(error); });
  try { $("rt-history-fold").open = localStorage.getItem("sparkcraft:history-fold") !== "closed"; } catch {}
  $("rt-history-fold").addEventListener("toggle", () => { try { localStorage.setItem("sparkcraft:history-fold", $("rt-history-fold").open ? "open" : "closed"); } catch {} });
  async function historyList() {
    const items = await api(`/api/meetings?deleted=${meetingsTrash}`); $("rt-history").replaceChildren();
    if (!items.length) $("rt-history").append(node("p", "empty-small", "你的第一场圆桌，从一个创意开始。"));
    for (const item of items) {
      const button = node("button", "rt-record", item.topic); button.type = "button"; button.setAttribute("aria-pressed", String(item.id === selected));
      button.append(node("small", "", `${labels[item.status] || item.status} · ${item.provider_mode === "simulation" ? "规则模拟" : "OpenClaw"}`));
      button.addEventListener("click", () => select(item.id).catch(error)); const row = node("div", "history-row"); row.append(button);
      const remove = node("button", "history-remove", meetingsTrash ? "恢复" : "删除"); remove.type = "button"; remove.disabled = ["running","queued"].includes(item.status); remove.title = remove.disabled ? "请先停止会议" : "移入回收站，保留交付关联";
      remove.addEventListener("click", async () => { remove.disabled = true; try { await api(`/api/meetings/${item.id}/visibility?deleted=${!meetingsTrash}`, {}); if (selected === item.id) { ++version; selected = null; meeting = null; $("rt-output").hidden = true; renderRoles(); window.dispatchEvent(new CustomEvent("sparkcraft:meeting", {detail:{id:null}})); } await historyList(); } catch(e) { error(e); remove.disabled = false; } }); row.append(remove); $("rt-history").append(row);
    }
  }
  function render() {
    if (!meeting) return; const m = meeting;
    $("rt-output").hidden = false; $("rt-title").textContent = m.topic; $("rt-status").textContent = labels[m.status] || m.status;
    const active = roles.find(r => r.id === m.active_role_id);
    $("rt-progress").textContent = `${m.provider_mode === "simulation" ? "规则模拟 · 非 AI 推理" : "模型评审"} · 第 ${m.current_round} / ${m.max_rounds} 轮 · ${m.turns.length} 次发言${active ? ` · ${active.name}正在发言` : ""} · 保守预算 ${Number(m.budget_tokens || 0).toLocaleString()} / 1,000,000 token`;
    $("rt-cancel").hidden = !["queued","running"].includes(m.status); $("rt-develop").hidden = m.status !== "completed";
    $("rt-export").href = `/api/meetings/${encodeURIComponent(m.id)}/export?format=markdown`;
    $("rt-error").hidden = !m.error; $("rt-error").textContent = m.error || "";
    const signature = `${m.id}:${m.turns.length}`;
    if ($("rt-turns").dataset.signature !== signature) {
      $("rt-turns").dataset.signature = signature; $("rt-turns").replaceChildren();
      for (const turn of m.turns) {
        const card = node("article", `rt-turn ${turn.role_id}`);
        card.append(node("small", "", turn.phase === "opening" ? "开场提案" : `第 ${turn.round} 轮 · ${turn.stance === "approve" ? "认可" : "建议修订"}`), node("h3", "", turn.role_name), node("p", "", turn.summary));
        if (turn.recommendations?.length) { const list = node("ul", ""); for (const text of turn.recommendations) list.append(node("li", "", text)); card.append(list); }
        $("rt-turns").append(card);
      }
    }
    $("rt-proposal").textContent = m.proposal || "等待主持者形成初始方案。"; $("rt-issues").replaceChildren();
    for (const issue of m.issues) $("rt-issues").append(node("div", "rt-issue", `${issue.id} · ${issue.status === "open" ? "待解决" : "已解决"} · ${roles.find(r=>r.id===issue.owner_role_id)?.name || issue.owner_role_id}\n${issue.title}\n${issue.detail}`));
    renderRoles();
    const deliverySignature = `${m.id}:${m.status}`;
    if ($("rt-output").dataset.deliverySignature !== deliverySignature) {
      $("rt-output").dataset.deliverySignature = deliverySignature;
      window.dispatchEvent(new CustomEvent("sparkcraft:meeting", {detail:{id:m.id,status:m.status}}));
    }
  }
  async function select(id) { selected = id; const v = ++version; const m = await api(`/api/meetings/${encodeURIComponent(id)}`); if (v !== version) return; meeting = m; render(); await historyList(); }
  $("rt-form").addEventListener("submit", async event => {
    event.preventDefault(); $("rt-start").disabled = true; $("rt-form-error").hidden = true;
    try { const m = await api("/api/meetings", {topic:$("rt-topic").value.trim(), constraints:$("rt-constraints").value.trim(), max_rounds:Number($("rt-rounds").value)}); await select(m.id); $("rt-output").scrollIntoView({behavior:"smooth",block:"start"}); }
    catch(e) { error(e); } finally { $("rt-start").disabled = false; }
  });
  $("rt-refresh").addEventListener("click", () => historyList().catch(error));
  $("rt-cancel").addEventListener("click", async () => { const id = selected; if (!id) return; try { await api(`/api/meetings/${encodeURIComponent(id)}/cancel`, {}); if (selected === id) await select(id); } catch(e) { error(e); } });
  $("rt-develop").textContent = "人工审核与制作 ↗";
  window.addEventListener("sparkcraft:open-meeting", async event => { try { await select(event.detail.id); window.dispatchEvent(new CustomEvent("sparkcraft:delivery", {detail:{id:meeting.id}})); } catch(e) { error(e); } });
  $("rt-develop").addEventListener("click", () => { if (meeting?.status === "completed") window.dispatchEvent(new CustomEvent("sparkcraft:delivery", {detail:{id:meeting.id}})); });
  async function boot() { try { const data = await api("/api/agents"); roles = data.roles; modelCatalog = data.models; renderRoles(); await historyList(); $("rt-start").disabled = false; } catch(e) { error(e); } }
  setInterval(async () => { if (busy || !selected || $("roundtable-view").hidden || document.hidden || !["running","queued"].includes(meeting?.status)) return; busy = true; const id = selected, v = version; try { const m = await api(`/api/meetings/${encodeURIComponent(id)}`); if (v === version) { meeting = m; render(); if (!["running","queued"].includes(m.status)) await historyList(); } } catch(e) { error(e); } finally { busy = false; } }, 2500);
  boot();
})();
