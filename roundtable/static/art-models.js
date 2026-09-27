(() => {
  'use strict';
  const card=document.createElement('details');card.className='panel art-connection';card.id='art-connection';
  card.innerHTML=`<summary>美术虾绘 · 多模态模型 API <span class="pill warning">测试版 · 接口预留</span></summary>
  <p>美术方案讨论由圆桌模型负责。图片与特效素材制作需要支持图像生成的多模态模型；当前先保存连接配置，生成适配器尚未启用。</p>
  <form id="art-model-form" autocomplete="off"><label for="art-protocol">接口协议</label><select id="art-protocol"><option value="openai_images">OpenAI Images 兼容接口（待适配）</option><option value="multimodal_custom">其他多模态接口（待适配）</option></select>
  <label for="art-base-url">API 基础地址</label><input id="art-base-url" type="url" maxlength="500" placeholder="https://your-provider.example/v1" required>
  <label for="art-model-id">图像生成模型 ID</label><input id="art-model-id" maxlength="200" placeholder="填写服务商提供的多模态生成模型名称" required>
  <label for="art-model-key">API Key</label><input id="art-model-key" type="password" maxlength="4096" autocomplete="new-password" placeholder="仅保存在本机，留空保留已有密钥">
  <button class="button secondary" id="art-save" type="submit">保存多模态配置</button><p id="art-model-status" role="status"></p></form>`;
  document.querySelector('.shrimp-office').after(card);
  const $=id=>document.getElementById(id);
  async function load(){const r=await fetch('/api/art/config');if(!r.ok)throw Error('读取美术配置失败');const v=await r.json();$('art-base-url').value=v.base_url;$('art-model-id').value=v.model;$('art-protocol').value=v.protocol||'openai_images';$('art-model-status').textContent=(v.configured?'已保存密钥。':'尚未配置。')+v.message;}
  $('art-model-form').onsubmit=async e=>{e.preventDefault();$('art-save').disabled=true;const key=$('art-model-key').value;$('art-model-key').value='';try{const r=await fetch('/api/art/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base_url:$('art-base-url').value,model:$('art-model-id').value,protocol:$('art-protocol').value,api_key:key})});if(!r.ok)throw Error('保存失败，请检查 API 地址、模型名称和密钥。');await load();}catch(e){$('art-model-status').textContent=e.message;}finally{$('art-save').disabled=false;}};
  load().catch(e=>$('art-model-status').textContent=e.message);
})();
