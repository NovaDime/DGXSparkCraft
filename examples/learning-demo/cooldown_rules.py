# -*- coding: utf-8 -*-
"""学习索引演示：纯逻辑，不依赖游戏接口。"""
class Cooldown(object):
    def __init__(self, interval):
        if interval < 0:
            raise ValueError('interval must be nonnegative')
        self.interval = interval
        self.last_used = {}

    def try_use(self, actor_id, now):
        last = self.last_used.get(actor_id)
        if last is not None and now - last < self.interval:
            return False
        self.last_used[actor_id] = now
        return True

    def forget(self, actor_id):
        self.last_used.pop(actor_id, None)
