"""Private connection form for future multimodal art generation adapters."""
import json
import os
import re
from urllib.parse import urlsplit

class ArtConnection:
    def __init__(self, data_dir):
        self.path = data_dir / 'private' / 'art-model.json'

    def read(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def public(self):
        value = self.read()
        return {k:value.get(k,'') for k in ('base_url','model','protocol')} | {
            'configured': bool(value.get('api_key')), 'ready': False,
            'status': 'saved_pending_adapter' if value else 'not_configured',
            'message': '测试版：保存多模态 API 配置入口；图片生成适配器尚未启用，不会发起生成请求或计费。'}

    def save(self, body):
        fields = {'base_url','model','protocol','api_key'}
        if not isinstance(body,dict) or set(body)!=fields or any(not isinstance(v,str) for v in body.values()):
            raise ValueError('无效配置')
        value={k:v.strip() for k,v in body.items()}
        if value['protocol'] not in {'openai_images','multimodal_custom'}:
            raise ValueError('请选择多模态接口协议')
        url=urlsplit(value['base_url'])
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or len(value['base_url'])>500:
            raise ValueError('API 地址必须为不含凭据的 HTTPS 地址')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:-]{0,199}',value['model']):
            raise ValueError('模型 ID 无效')
        key=value['api_key'] or self.read().get('api_key','')
        if not key or len(key)>4096 or any(ord(c)<32 for c in key) or any(key in value[k] for k in ('base_url','model','protocol')):
            raise ValueError('密钥无效')
        value['api_key']=key
        self.path.parent.mkdir(parents=True,exist_ok=True);self.path.parent.chmod(0o700)
        temp=self.path.with_suffix('.tmp')
        with os.fdopen(os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as f:
            os.fchmod(f.fileno(),0o600);json.dump(value,f,ensure_ascii=False)
        temp.replace(self.path)
        return self.public()
