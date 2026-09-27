(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const el = (tag, cls, text) => { const n = document.createElement(tag); n.className = cls; if (text != null) n.textContent = text; return n; };
  let meetingId = null, delivery = null, generation = 0, pollBusy = false;
  const active = new Set(["planning", "queued", "running"]);
  const labels = {planning:"整理任务单",awaiting_approval:"等待你的审核",queued:"已批准 · 排队执行",running:"Agent 制作中",blocked:"需要处理",failed:"执行失败",interrupted:"执行中断",cancelled:"已停止",packaged:"已打包 · 待游戏验收"};
  const panel = el("section", "panel delivery-panel"); panel.id = "delivery-panel"; panel.hidden = true;
  panel.innerHTML = `<div class="panel-title"><div><span class="section-number">FROM CONSENSUS TO CREATION</span><h2>确认方案，进入开发圆桌</h2></div><span class="pill" id="delivery-status"></span></div>
    <ol class="delivery-steps"><li>01 圆桌共识</li><li>02 人工审核</li><li>03 开发圆桌</li><li>04 集成打包</li></ol>
    <p class="muted">讨论通过不等于开始制作。审核锁定方案、目标版本和音效描述后，策划整合数值，再逐项下发程序与素材任务，检查并汇总产物。</p>
    <p id="delivery-error" class="form-error" role="alert" hidden></p>
    <details class="advanced"><summary>查看待批准的圆桌方案</summary><pre id="delivery-proposal" class="delivery-proposal"></pre></details>
    <form id="delivery-approval"><fieldset id="delivery-fields"><label for="delivery-title">模组名称</label><input id="delivery-title" maxlength="120" required>
    <label for="delivery-target">目标客户端与版本</label><input id="delivery-target" maxlength="160" required value="Minecraft 中国版基岩 1.24">
    <label for="delivery-code">程序 Agent 任务</label><textarea id="delivery-code" rows="6" minlength="4" maxlength="3500" required></textarea>
    <div class="panel-title"><h3>调音虾尾 · 素材任务</h3><button id="delivery-add-sound" class="text-button" type="button">＋ 添加音效</button></div>
    <div id="delivery-assets"></div><p class="field-help">资源 ID 在审批后固定，程序按同一清单接入播放。NPC 台词和音效描述将发送到 StepFun，最多 12 条。</p>
    <h3>美术虾绘 · 计划素材</h3><pre id="delivery-art-plan" class="delivery-proposal"></pre><p class="field-help">多模态生成当前为测试版配置入口；有必需的新素材时，需修改为已有资源或等待适配器完成后再开工。</p><label for="delivery-resources">其他待制作素材 <span class="optional">每行一项</span></label><textarea id="delivery-resources" rows="2" placeholder="若需要新贴图、模型等，必须先解决；有未完成素材不能批准执行。"></textarea>
    <label for="delivery-notes">审核备注</label><textarea id="delivery-notes" rows="2" maxlength="2000"></textarea>
    <label class="checkbox-label"><input id="delivery-confirm" type="checkbox" required><span>我已审核方案与任务单，同意自动调用程序和音频模型执行（可能产生 API 费用）。</span></label>
    <button id="delivery-approve" class="button primary" type="submit">审核通过并自动执行 ↗</button></fieldset></form>
    <details class="panel art-connection" id="audio-connection"><summary>调音虾尾 · 音频模型 API · <span id="audio-config-status">读取中</span></summary><p>用于 NPC 对话语音、物品与交互音效。默认使用 stepaudio-3-gen-preview；保存配置不会生成音频，人工批准制作任务后才会调用 StepFun。</p>
    <form id="audio-config-form" autocomplete="off"><label for="audio-endpoint">服务区域</label><select id="audio-endpoint"><option value="https://api.stepfun.com/v1/audio/generate">中国 · api.stepfun.com</option><option value="https://api.stepfun.ai/v1/audio/generate">国际 · api.stepfun.ai</option></select>
    <label for="audio-generation-model">音频模型</label><input id="audio-generation-model" value="stepaudio-3-gen-preview" maxlength="100" required>
    <label for="audio-api-key">API Key</label><input id="audio-api-key" type="password" autocomplete="new-password" required maxlength="4096" placeholder="只保存在本机私有配置，保存后不回显">
    <button class="button secondary" id="audio-save">保存音频连接</button><p id="audio-save-result" role="status"></p></form></details>
    <div id="delivery-approval-record" class="delivery-approval-record"></div>
    <div id="delivery-events" class="delivery-events" aria-live="polite"></div><div id="delivery-sounds" class="delivery-sounds"></div><div id="delivery-checks"></div>
    <div class="job-actions"><button id="delivery-stop" class="button danger small" type="button" hidden>停止制作</button><a id="delivery-code-link" class="button secondary small" hidden>查看程序产物</a><a id="delivery-download" class="button primary" download hidden>下载完整交付包 ↓</a><a id="delivery-addon" class="button secondary" download hidden>仅下载附加包 ↓</a></div>
    <div id="delivery-retry-panel" hidden><label class="checkbox-label"><input id="delivery-retry-confirm" type="checkbox"><span>继续时复用已完成产物；未完成的音频请求可能再次计费。</span></label><button id="delivery-retry" class="button secondary" type="button">继续执行</button></div>
    <form id="delivery-revise-form"><label for="delivery-revise">退回修改意见</label><textarea id="delivery-revise" rows="2" minlength="4" maxlength="2000" required placeholder="说明需要改动的功能或素材。重新整理后必须再次审核。"></textarea><button class="button secondary" id="delivery-revise-submit">提出修改 · 继续讨论</button></form>`;
  $("rt-output").after(panel);
  document.querySelector(".shrimp-office").after($("audio-connection"));
  const audioHint = document.querySelector(".rt-layout aside .context-card .field-help");
  if (audioHint) audioHint.textContent = "参与圆桌评审。人工批准任务单后自动生成 NPC 配音与音效，并转为游戏用 OGG 资源。";
  async function api(url, body) {
    const r = await fetch(url, {method:body === undefined ? "GET" : "POST", headers:body === undefined ? {} : {"Content-Type":"application/json"},body:body === undefined ? undefined : JSON.stringify(body)});
    const data = await r.json(); if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "字段格式无效，请检查任务单与音效内容。"); return data;
  }
  function error(e) { $("delivery-error").textContent = e.message || "操作失败"; $("delivery-error").hidden = false; }
  function soundRow(a = {id:"",kind:"interaction",text:"",voice:"",direction:"独立游戏音效，不含背景音乐。",trigger:""}) {
    if ($("delivery-assets").children.length >= 12) return;
    const row = el("div", "delivery-asset");
    const key = crypto.randomUUID();
    for (const [field, label, limit] of [["id","资源 ID（小写英文、数字、下划线）",48],["kind","素材类别",0],["text","NPC 台词 / 音效描述",950],["voice","NPC 音色描述",450],["direction","情绪、质感与制作要求",500],["trigger","游戏内触发时机",500]]) {
      const labelNode = el("label", "", label); const input = el(field === "kind" ? "select" : ["text","direction","trigger"].includes(field) ? "textarea" : "input", "");
      input.id = `asset-${key}-${field}`; labelNode.htmlFor = input.id; input.dataset.field = field;
      if (field === "kind") for (const [v,n] of [["npc","NPC 对话"],["item","物品音效"],["interaction","交互音效"]]) { const opt=el("option","",n); opt.value=v; input.append(opt); }
      else { input.maxLength = limit; input.required = field !== "voice"; }
      input.value = a[field]; row.append(labelNode,input);
    }
    const remove=el("button","text-button","移除此素材"); remove.type="button"; remove.onclick=()=>row.remove(); row.append(remove); $("delivery-assets").append(row);
  }
  function render(item) {
    if(item.status === "packaged") {
      const key=`sparkcraft:delivery-notified:${item.id}:${item.revision}`;
      let notified=false;try{notified=localStorage.getItem(key)==="yes";}catch{}
      if(!notified && !document.getElementById("delivery-done")){
        const dialog=el("dialog","agent-dialog");dialog.id="delivery-done";
        dialog.append(el("h2","","模组已制作完成"),el("p","","可以下载本地交付包。结构检查已通过，目标客户端内效果仍需你验收。"));
        const download=el("a","button primary","下载模组包 ↓");download.href=`/api/deliveries/${item.id}/download`;download.download="";
        const close=el("button","button secondary","知道了");close.onclick=()=>dialog.close();dialog.append(download,close);document.body.append(dialog);
        dialog.addEventListener("close",()=>dialog.remove());dialog.showModal();try{localStorage.setItem(key,"yes");}catch{}
      }
    }
    window.dispatchEvent(new CustomEvent("sparkcraft:production",{detail:{role:active.has(item.status) ? ({planning:"planner",planning_handoff:"planner",audio:"audio",code:"engineer",integration:"reviewer",package:"host"}[item.stage] || "host") : null}}));
    delivery = item; panel.hidden = false; $("delivery-status").textContent = labels[item.status] || item.status;
    $("delivery-error").hidden = !item.error; $("delivery-error").textContent = item.error || "";
    $("delivery-proposal").textContent = item.proposal;
    const editable = item.status === "awaiting_approval";
    $("delivery-approval").hidden = !item.plan; $("delivery-fields").disabled = !editable;
    if (panel.dataset.revision !== `${item.id}:${item.revision}:${Boolean(item.plan)}`) {
      panel.dataset.revision = `${item.id}:${item.revision}:${Boolean(item.plan)}`;
      $("delivery-assets").replaceChildren(); $("delivery-confirm").checked = false; $("delivery-notes").value = "";
      if (item.plan) { $("delivery-art-plan").textContent=(item.plan.art_assets || []).map(a=>`${a.id} · ${a.kind} · ${a.description}`).join("\n") || "不需要新美术素材，复用已有资源"; $("delivery-title").value=item.plan.title; $("delivery-target").value=item.plan.target; $("delivery-code").value=item.plan.code_task; $("delivery-resources").value=item.plan.required_resources.join("\n"); item.plan.assets.forEach(soundRow); }
    }
    $("delivery-approve").hidden = !editable;
    $("delivery-approval-record").textContent = item.approval ? `已人工批准 · ${new Date(item.approval.time).toLocaleString()} · 版本 ${item.approval.revision} · 方案指纹 ${item.approval.plan_hash.slice(0,12)}` : "尚未获得人工批准，不会自动制作。";
    $("delivery-events").replaceChildren(...item.events.map(e=>el("p",`event-${e.status}`,e.message)));
    $("delivery-checks").replaceChildren(...(item.checks || []).map(c=>el("p", c.level === "error" ? "form-error" : "field-help",c.message)));
    if (item.review) $("delivery-checks").append(el("p","field-help",item.review.summary),...(item.review.issues || []).map(x=>el("p","form-error",x)));
    for (const [id, sound] of Object.entries(item.sounds)) {
      if ($("delivery-sounds").querySelector(`[data-asset="${id}"]`)) continue;
      const card=el("div","delivery-sound"); card.dataset.asset=id; const audio=el("audio",""); audio.controls=true; audio.preload="none"; audio.src=sound.url;
      card.append(el("strong","",id),el("small","",`${sound.seconds}s · OGG/Vorbis`),audio); $("delivery-sounds").append(card);
    }
    $("delivery-stop").hidden = !active.has(item.status);
    $("delivery-revise-form").hidden = active.has(item.status) || item.status === "packaged";
    $("delivery-retry-panel").hidden = !item.approval || !["blocked","failed","interrupted","cancelled"].includes(item.status);
    for (const [id,url] of [["delivery-download",item.download_url],["delivery-addon",item.addon_url]]) { $(id).hidden=item.status!=="packaged"; if (url) $(id).href=url; }
    $("delivery-code-link").hidden = !item.code_job_id;
    if (item.code_job_id) $("delivery-code-link").href=`/api/development/jobs/${item.code_job_id}/download`;
  }
  async function loadConfig() { try { const c=await api("/api/audio/config"); $("audio-config-status").textContent=c.configured?"已配置":"未配置"; $("audio-endpoint").value=c.endpoint; $("audio-generation-model").value=c.model; } catch(e){$("audio-config-status").textContent="读取失败";$("audio-save-result").textContent=e.message;} }
  window.addEventListener("sparkcraft:meeting", async event=> { meetingId=event.detail.id; delivery=null; panel.hidden=true; $("delivery-sounds").replaceChildren(); const v=++generation; if (!meetingId) return; try { const item=await api(`/api/meetings/${meetingId}/delivery`); if(v===generation && item) render(item); } catch(e){error(e);} });
  window.addEventListener("sparkcraft:delivery", async event=> { meetingId=event.detail.id; const v=++generation; panel.hidden=false; $("delivery-status").textContent="正在整理任务单…"; try {const item=await api(`/api/meetings/${meetingId}/delivery`,{}); if(v===generation) {render(item); await loadConfig(); panel.scrollIntoView({behavior:"smooth",block:"start"});}}catch(e){error(e);} });
  $("delivery-add-sound").onclick=()=>soundRow();
  $("delivery-approval").onsubmit=async event=> { event.preventDefault(); if(!delivery)return; $("delivery-approve").disabled=true;
    try { const assets=[...$("delivery-assets").children].map(row=>Object.fromEntries([...row.querySelectorAll("[data-field]")].map(n=>[n.dataset.field,n.value.trim()])));
      render(await api(`/api/deliveries/${delivery.id}/approve`,{revision:delivery.revision,confirmed:$("delivery-confirm").checked,notes:$("delivery-notes").value,plan:{...delivery.plan,title:$("delivery-title").value,target:$("delivery-target").value,code_task:$("delivery-code").value,assets,required_resources:$("delivery-resources").value.split("\n").map(x=>x.trim()).filter(Boolean)}}));
    }catch(e){error(e);}finally{$("delivery-approve").disabled=false;} };
  $("audio-config-form").onsubmit=async event=> { event.preventDefault(); const key=$("audio-api-key").value; $("audio-api-key").value=""; $("audio-save").disabled=true;
    try{await api("/api/audio/config",{api_key:key,endpoint:$("audio-endpoint").value,model:$("audio-generation-model").value});$("audio-save-result").textContent="已保存至本机私有目录。";await loadConfig();}catch(e){$("audio-save-result").textContent=e.message;}finally{$("audio-save").disabled=false;} };
  $("delivery-stop").onclick=async()=>{try{render(await api(`/api/deliveries/${delivery.id}/cancel`,{}));}catch(e){error(e);}};
  $("delivery-retry").onclick=async()=>{if(!$("delivery-retry-confirm").checked){error(new Error("请先确认重试可能产生的 API 费用。"));return;}try{render(await api(`/api/deliveries/${delivery.id}/retry`,{confirmed:true}));$("delivery-retry-confirm").checked=false;}catch(e){error(e);}};
  $("delivery-revise-form").onsubmit=async event=>{event.preventDefault();$("delivery-revise-submit").disabled=true;try{const parent=await api(`/api/meetings/${delivery.meeting_id}`);const next=await api("/api/meetings",{topic:parent.topic,constraints:parent.constraints || "",max_rounds:Number($("rt-rounds").value),parent_meeting_id:parent.id,revision_notes:$("delivery-revise").value});window.dispatchEvent(new CustomEvent("sparkcraft:select-meeting",{detail:{id:next.id}}));panel.hidden=true;}catch(e){error(e);}finally{$("delivery-revise-submit").disabled=false;}};
  setInterval(async()=>{if(pollBusy || !delivery || !active.has(delivery.status) || document.hidden)return; pollBusy=true;const v=generation,id=delivery.id;try{const item=await api(`/api/deliveries/${id}`);if(v===generation)render(item);}catch(e){error(e);}finally{pollBusy=false;}},2000);
  loadConfig();
})();
