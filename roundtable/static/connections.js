(() => {
  'use strict';
  const box=document.createElement('details');box.className='panel art-connection';box.id='connection-check';
  box.innerHTML='<summary>本机连接检测 · <span id="connection-summary">检测中…</span></summary><p id="connection-model"></p><p id="connection-gateway"></p><p id="connection-help"></p><button id="connection-refresh" class="button secondary" type="button">重新检测</button>';
  document.getElementById('main').prepend(box);
  const $=id=>document.getElementById(id);
  async function check(){ $('connection-refresh').disabled=true;try{
    const r=await fetch('/api/connections');if(!r.ok)throw Error('连接检测请求失败，请确认工作台服务已更新。');const data=await r.json();
    const labels={connected:'已连接',unavailable:'未启动或正在加载',not_configured:'尚未创建项目配置',invalid_config:'配置无效',auth_error:'认证失败',http_error:'接口异常',invalid_response:'响应格式不符'};
    $('connection-model').textContent=`本地模型：${labels[data.model.status] || data.model.status} · ${data.model.models?.join('、') || data.model.url}`;
    $('connection-gateway').textContent=`OpenClaw：${data.openclaw.installed?'已安装':'未检测到命令'} · 项目网关${labels[data.openclaw.status] || data.openclaw.status} · ${data.openclaw.url}`;
    const ready=data.model.ok && data.model.compatible && data.openclaw.ok;
    $('connection-summary').textContent=ready?'本地模型与 OpenClaw 已连接':'需要检查';box.open=!ready;
    $('connection-help').textContent=ready?data.message:'请运行完整项目目录中的启动.sh，等待模型加载与网关启动，再重新检测。若认证失败，查看 data/runtime/startup.log。'+(data.other_gateway_detected?' 已检测到通用 OpenClaw 18789，本项目默认使用独立的 19789 网关。':'');
  }catch(e){$('connection-summary').textContent='检测失败';$('connection-help').textContent=e.message;box.open=true;}finally{$('connection-refresh').disabled=false;}}
  $('connection-refresh').onclick=check;check();
})();
