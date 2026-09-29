"""Read-only local startup diagnostics. Never returns or forwards credentials externally."""
import json
import shutil
import socket
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def local_models(port, token=''):
    try:
        request=Request(f'http://127.0.0.1:{port}/v1/models',headers={'Authorization':'Bearer '+token} if token else {})
        with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=2) as r:
            value=json.loads(r.read(1024*1024))
        if not isinstance(value,dict) or not isinstance(value.get('data'),list):
            return {'ok':False,'status':'invalid_response'}
        return {'ok':True,'status':'connected','models':[x['id'][:200] for x in value['data'] if isinstance(x,dict) and isinstance(x.get('id'),str)]}
    except HTTPError as e:
        return {'ok':False,'status':'auth_error' if e.code in (401,403) else 'http_error'}
    except (OSError,ValueError):
        return {'ok':False,'status':'unavailable'}

def probe(root, data_dir=None):
    root=Path(root); data_dir=Path(data_dir) if data_dir else root/'data'
    model=local_models(8000)
    model['url']='http://127.0.0.1:8000/v1'
    model['compatible']=any(x in model.get('models',[]) for x in ('nemotron-3.5-lightning','nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4'))
    path=data_dir/'openclaw/openclaw.json'
    gateway={'ok':False,'status':'not_configured','url':'http://127.0.0.1:19789'}
    if path.exists():
        try:
            config=json.loads(path.read_text());port=config['gateway'].get('port',19789)
            if type(port) is not int or not 1024<=port<=65535:raise ValueError()
            token=config['gateway'].get('auth',{}).get('token','')
            if not isinstance(token,str):raise ValueError()
            gateway={**local_models(port,token),'url':f'http://127.0.0.1:{port}'}
            gateway.pop('models',None)
        except (OSError,ValueError,KeyError,TypeError):
            gateway['status']='invalid_config'
    command=bool((root/'.runtime/openclaw/bin/openclaw').exists() or shutil.which('openclaw'))
    with socket.socket() as sock:
        sock.settimeout(.3);other=sock.connect_ex(('127.0.0.1',18789))==0
    return {'model':model,'openclaw':{**gateway,'installed':command},'other_gateway_detected':other,
            'inference_verified':False,'message':'检测模型列表与网关认证，不发送生成请求；不代表已完成推理或游戏验收。'}

def describe(report):
    model=report['model'];gateway=report['openclaw']
    statuses={'connected':'已连接','not_configured':'尚未创建项目配置','invalid_config':'项目配置无效','auth_error':'认证失败','unavailable':'未就绪或尚未启动','invalid_response':'响应格式不符','http_error':'HTTP 接口异常'}
    return [f"本地模型：{statuses[model['status']]}（{model['url']}）",
            'OpenClaw 命令：'+('已安装' if gateway['installed'] else '未安装'),
            f"项目 OpenClaw：{statuses[gateway['status']]}（{gateway['url']}）"]
