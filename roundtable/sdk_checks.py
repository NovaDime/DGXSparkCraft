"""Reject known module/component API confusion without executing generated scripts."""
import ast, io, tokenize
CORRECTIONS = {
    'AddTimer':'GetEngineCompFactory().CreateGame(GetLevelId()).AddTimer',
    'CreateExplosion':'GetEngineCompFactory().CreateExplosion(GetLevelId()).CreateExplosion',
    'GetLevel':'GetLevelId（返回关卡 ID；实体信息须通过组件读取）',
    'GetEntity':'GetEngineCompFactory().CreateEngineType(entityId).GetEngineTypeStr() 或 CreatePos(entityId).GetPos()；不存在实体字典查询接口',
    'ListenForEvent':'继承 GetServerSystemCls/GetClientSystemCls 后使用 self.ListenForEvent',
    'UnListenForEvent':'系统实例的 self.UnListenForEvent',
}
def sdk_checks(files):
    checks=[]
    for file in files:
        if not file['path'].endswith('.py'):continue
        text=file['content']
        aliases=set()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None  # Python 2 syntax remains the runtime validator's responsibility.
        for node in ast.walk(tree) if tree is not None else ():
            message = None
            if isinstance(node, ast.ImportFrom) and node.module in ('mod.server.extraServerApi', 'mod.client.extraClientApi'):
                for name in node.names:
                    if name.name in ('serverApi', 'clientApi'):
                        aliases.add(name.asname or name.name)
                        message = 'API 模块导入方式无效，使用 import ' + node.module + ' as ' + (name.asname or name.name)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                method = node.func.attr
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'self':
                    if method in ('ListenForEvent', 'UnListenForEvent') and not node.keywords and not any(isinstance(a, ast.Starred) for a in node.args) and len(node.args) not in ((5, 6) if method == 'ListenForEvent' else (5,)):
                        message = method + ' 需要五个位置参数：namespace, systemName, eventName, instance, callback；引擎事件使用 GetEngineNamespace(), GetEngineSystemName(), 事件名, self, 回调。'
                    elif method == 'UnlistenForEvent':
                        message = '注销监听的方法名为 UnListenForEvent，区分大小写，参数须与注册时一致。'
                owner = node.func.value
                if method == '__init__' and isinstance(owner, ast.Call) and isinstance(owner.func, ast.Attribute) and owner.func.attr in ('GetServerSystemCls', 'GetClientSystemCls') and len(node.args) == 2 and not node.keywords:
                    message = '系统基类初始化缺少 self，使用 GetServerSystemCls().__init__(self, namespace, systemName)。'
            if message:
                checks.append({'level': 'error', 'message': f"{file['path']}:{node.lineno} {message}"})
        try:
            tokens=[t for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT)]
        except (tokenize.TokenError, IndentationError):continue
        # Match exact dotted imports, including user-selected aliases.
        import re
        aliases.update(re.findall(r'^\s*import mod\.(?:server|client)\.extra(?:Server|Client)Api as (\w+)', text, re.M))
        for i,t in enumerate(tokens):
            if t.string in aliases and i+3<len(tokens) and tokens[i+1].string=='.' and tokens[i+3].string=='(':
                name=tokens[i+2].string
                if name in CORRECTIONS:
                    checks.append({'level':'error','message':f"{file['path']}:{t.start[0]} {t.string}.{name} 不是该模块的接口。请使用 {CORRECTIONS[name]}，按官方正文核对参数。"})
            if t.type==tokenize.STRING and t.string.strip('\"\'')=='OnEntityDeathEvent':
                checks.append({'level':'error','message':f"{file['path']}:{t.start[0]} 死亡事件应根据已索引官方正文使用 MobDieEvent，args 为字典，字段 id/attacker/cause。不得沿用方案中未核实的 OnEntityDeathEvent。"})
    return checks
