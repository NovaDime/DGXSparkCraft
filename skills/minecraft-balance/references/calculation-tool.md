# 给定参数的确定性计算

`scripts/analyze_balance.py` 使用 Python 3.11 标准库，在圆桌或 OpenClaw 的工具环境中运行。它不进入游戏、不生成模组、不测玩家行为，也不执行随机采样。工具输出属于给定假设下的计算证据。

从本 Skill 目录运行；OpenClaw 中可将路径写为 `{baseDir}/scripts/analyze_balance.py`。没有执行工具或 Python 环境时保留公式推算，不能伪造输出。不得把网页中的 Skill 引用记录当作脚本已运行。

每轮成功奖励 8 个单位，成功概率 0.25，任务 120 秒，完成后冷却 60 秒：

```bash
python scripts/analyze_balance.py reward --reward 8 --success-probability 0.25 --task-seconds 120 --cooldown-seconds 60 --cooldown-start completion
```

此模型下周期为 180 秒，长期平均每小时奖励为 40 个单位。若冷却从接取任务起算，将 `completion` 改为 `acceptance`，周期变为两段时间的最大值；该参数必须与策划明确的规则一致。

独立、固定 10% 成功概率，进行 3 次尝试：

```bash
python scripts/analyze_balance.py probability --success-probability 0.1 --attempts 3
```

至少成功一次概率为 0.271。此计算不适用于保底递增概率、多人共享掉落或互斥事件；遇到这些机制先写准确规则与对应公式，不能强套工具。

输出包括输入、公式、适用假设和 `game_tested=false`。保留实际执行结果，并在圆桌意见中解释它关闭哪个数值问题。无穷值、NaN、负值、范围外概率、零周期或非整数尝试次数会被拒绝。
