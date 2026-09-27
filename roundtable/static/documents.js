(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const panel = document.createElement('details'); panel.className='panel document-panel';
  panel.innerHTML=`<summary class="document-import-summary">补充我的世界开发文档 <span>粘贴正文 · 官方链接 · 上传文件</span></summary>
  <p class="muted">可添加项目特定的接口说明与版本资料。导入的补充文档可在上方知识库中检索。</p>
  <details class="document-settings"><summary>⚙ 文档识别模型与 API 配置</summary><p class="field-help">识别员负责归纳游戏、版本、API 和限制。选择云端模型时，导入的文档正文会发送至该服务。</p><form id="doc-model-form"><label>识别模型<select id="doc-model"><option value="">请先选择模型</option></select></label><button class="button secondary small">保存识别模型</button></form>
  <details><summary>接入自己的模型 API</summary><form id="doc-cloud-form" autocomplete="off"><div class="doc-fields"><label>连接名称<input id="doc-cloud-name" required maxlength="80" placeholder="我的文档识别模型"></label><label>模型 ID<input id="doc-cloud-id" required maxlength="200" placeholder="服务商提供的文本模型 ID"></label></div><label>API 基础地址<input id="doc-cloud-url" type="url" required placeholder="https://api.example.com/v1"></label><label>API Key<input id="doc-cloud-key" type="password" required autocomplete="new-password" maxlength="4096"></label><p class="field-help">兼容 Chat Completions。密钥只保存在本机私有目录，不随代码导出；保存后自动选为文档识别模型。</p><button class="button secondary small">保存并选用</button><button id="doc-test" type="button" class="button secondary small">测试已选云端连接</button></form></details></details>
  <form id="doc-import-form"><div class="doc-fields"><label>游戏 / 引擎<input id="doc-game" required maxlength="80" list="doc-games" value="Minecraft 中国版"><datalist id="doc-games"><option value="Minecraft 中国版"><option value="Minecraft Java"></datalist></label><label>客户端 / SDK 版本<input id="doc-version" maxlength="80" placeholder="例如：1.24 / SDK 版本"></label></div><label>资料标题<input id="doc-title" required maxlength="100" placeholder="例如：实体交互 API 文档"></label><label>资料方式<select id="doc-mode"><option value="text">粘贴文档正文</option><option value="url">粘贴官网文档链接</option><option value="file">上传文档文件</option></select></label><label id="doc-url-group" hidden>官网开发文档链接<input id="doc-url" type="url" placeholder="https://…"><small>仅抓取这一页；登录页面和动态站点可改为上传文件。链接来源需自行核对。</small></label><label id="doc-file-group" hidden>上传本地文档<input id="doc-file" type="file" accept=".txt,.md,.rst,.json,.html,.htm,.pdf,.docx"><small>最多 8 MiB；PDF 提取前 100 页。扫描件 / 图片 OCR 尚在开发中。</small></label><label id="doc-text-group">文档正文<textarea id="doc-text" rows="6" maxlength="100000" placeholder="粘贴接口说明、参数和示例…"></textarea></label><label class="checkbox-label"><input id="doc-analyze" type="checkbox" checked><span>由识别模型生成摘要（最多 24000 字符），同时保留原文</span></label><button id="doc-import" class="button primary">识别并加入知识库 ↗</button></form><p id="doc-message" role="status" aria-live="polite"></p><details id="doc-result" hidden><summary>查看模型识别摘要 · 待人工核对</summary><pre id="doc-analysis"></pre></details>`;
  $('minecraft-document-import').append(panel);
  const msg = text => {$('doc-message').textContent=text;};
  async function api(path, body, raw=false) {
    const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':raw?'application/octet-stream':'application/json'},body:body===undefined?undefined:raw?body:JSON.stringify(body),signal:AbortSignal.timeout(900000)});
    const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'配置或资料格式无效');return data;
  }
  function chooseGame(game) {
    $('knowledge-choices').hidden = Boolean(game);
    $('knowledge-game-content').hidden = !game;
    $('knowledge-minecraft-content').hidden = game !== 'minecraft';
    $('knowledge-other-content').hidden = game !== 'other';
    if (game === 'minecraft') loadOfficial().catch(showOfficialError);
  }
  function showOfficialError(error) {
    $('official-knowledge-message').textContent = `正文索引状态暂不可用：${error.message}。仍可打开官方文档。`;
    for (const card of document.querySelectorAll('.official-card')) card.querySelector('.official-index-status').textContent = '正文索引状态未确认';
  }
  function renderOfficial(data) {
    for (const card of document.querySelectorAll('.official-card')) {
      const source = (data.sources || []).find(item => item.url === card.dataset.sourceUrl);
      const count = Number(source?.document_count) || 0;
      const characters = Number(source?.character_count) || 0;
      const indexed = count > 0 && characters > 0;
      const labels = {guide_snapshot: '开发指南全文快照（固定仓库版本）', guide_snapshot_partial: '开发指南快照（存在未下载文章）', partial: '已索引部分官方正文', reference_snapshot: '已索引固定版本参考片段（非主站正文）'};
      card.querySelector('.official-index-status').textContent = indexed
        ? `${labels[source.status] || '已缓存部分资料'} · ${count} 篇 · ${characters.toLocaleString()} 字符`
        : source?.status === 'baseline_only' ? '基础规则已预置 · 官方正文尚未索引' : '正文索引尚未就绪 · 可尝试更新索引';
    }
    $('official-knowledge-message').textContent = data.message || '官方入口与正文索引分别管理，索引范围以实际获取的正文为准。';
  }
  async function loadOfficial() { renderOfficial(await api('/api/official-knowledge')); }
  $('knowledge-minecraft').onclick = () => chooseGame('minecraft');
  $('knowledge-other').onclick = () => chooseGame('other');
  $('knowledge-back').onclick = () => { chooseGame(null); $('knowledge-minecraft').focus(); };
  $('nav-knowledge').addEventListener('click', () => chooseGame(null));
  $('manage-repositories').addEventListener('click', () => chooseGame('minecraft'));
  $('review-learning').addEventListener('click', () => chooseGame('minecraft'));
  $('official-knowledge-sync').onclick = async () => {
    const button = $('official-knowledge-sync'); button.disabled = true;
    button.textContent = '正在更新…';
    $('official-knowledge-message').textContent = '正在获取官方正文并更新索引，请稍候…';
    try {
      const response = await fetch('/api/official-knowledge/sync', {method: 'POST', signal: AbortSignal.timeout(900000)});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '官方资料更新失败');
      renderOfficial(data);
    } catch (error) { showOfficialError(error); }
    finally { button.disabled = false; button.textContent = '更新官方正文索引'; }
  };
  async function models(){const data=await api('/api/documents/model');$('doc-model').replaceChildren(new Option('请选择识别模型',''));for(const m of data.models)$('doc-model').append(new Option(m.name,m.id));$('doc-model').value=data.model;}
  const busy = (form,value) => {for(const button of form.querySelectorAll('button'))button.disabled=value;};
  $('doc-model-form').onsubmit=async event=>{event.preventDefault();try{await api('/api/documents/model',{model:$('doc-model').value});msg('识别模型已保存。');}catch(e){msg(e.message);}};
  $('doc-cloud-form').onsubmit=async event=>{event.preventDefault();busy(event.target,true);const key=$('doc-cloud-key').value;$('doc-cloud-key').value='';try{const data=await api('/api/cloud-models',{name:$('doc-cloud-name').value,model:$('doc-cloud-id').value,base_url:$('doc-cloud-url').value,api_key:key});await api('/api/documents/model',{model:data.id});await models();msg('API 已保存并选为识别模型；可测试连接。');}catch(e){msg(e.message);}finally{busy(event.target,false);}};
  $('doc-test').onclick=async()=>{const id=$('doc-model').value;if(!id.startsWith('cloud/'))return msg('请选择云端连接；本地模型通过实际文档任务验证。');$('doc-test').disabled=true;try{const data=await api(`/api/cloud-models/${id.slice(6)}/check`,{});msg(data.message);}catch(e){msg(e.message);}finally{$('doc-test').disabled=false;}};
  $('doc-mode').onchange=()=>{for(const mode of ['text','url','file'])$('doc-'+mode+'-group').hidden=mode!==$('doc-mode').value;};
  $('doc-import-form').onsubmit=async event=>{event.preventDefault();$('doc-import').disabled=true;$('doc-result').hidden=true;msg('正在读取并识别资料，请稍候…');try{const mode=$('doc-mode').value;let text=mode==='text'?$('doc-text').value:'';let source='用户粘贴';if(mode==='file'){const file=$('doc-file').files[0];if(!file)throw new Error('请先选择文件');if(file.size>8*1024*1024)throw new Error('文件不能超过 8 MiB');text=(await api('/api/documents/extract?filename='+encodeURIComponent(file.name),file,true)).text;source=file.name;}const result=await api('/api/documents/import',{game:$('doc-game').value,version:$('doc-version').value,title:$('doc-title').value,url:mode==='url'?$('doc-url').value:'',text,source,analyze:$('doc-analyze').checked});$('doc-analysis').textContent=result.analysis;$('doc-result').hidden=false;$('doc-result').open=true;msg(`已加入「${result.repository.name}」。原文和识别摘要可在下方检索。`);$('refresh-repositories').click();}catch(e){msg(e.name==='TimeoutError'?'请求超时，请刷新知识库确认是否已导入。':e.message);}finally{$('doc-import').disabled=false;}};
  $('nav-knowledge').addEventListener('click',()=>models().catch(e=>msg(e.message)));
  models().catch(e=>msg(e.message));
})();
