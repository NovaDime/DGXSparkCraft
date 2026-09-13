"""Deterministic design calculations; no game, model, or sampled player data."""

from __future__ import annotations

import argparse
import json
import math
import sys


def finite_nonnegative(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是数字") from exc
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("必须是有限的非负数")
    return number


def probability(value: str) -> float:
    number = finite_nonnegative(value)
    if number > 1:
        raise argparse.ArgumentTypeError("概率使用 0 至 1 的小数")
    return number


def attempts(value: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("尝试次数必须是整数") from exc
    if not 0 <= count <= 1_000_000_000:
        raise argparse.ArgumentTypeError("尝试次数须在 0 至 1000000000 之间")
    return count


def reward_result(args: argparse.Namespace) -> dict:
    period = (args.task_seconds + args.cooldown_seconds if args.cooldown_start == "completion"
              else max(args.task_seconds, args.cooldown_seconds))
    if not math.isfinite(period) or period <= 0:
        raise ValueError("任务与冷却定义的周期须为有限正数")
    expected = args.reward * args.success_probability
    hourly = expected / period * 3600
    if not math.isfinite(hourly):
        raise ValueError("参数导致数值溢出，请使用合理量级")
    return {
        "kind": "reward_rate",
        "inputs": {key: getattr(args, key) for key in (
            "reward", "success_probability", "task_seconds", "cooldown_seconds", "cooldown_start")},
        "cycle_seconds": period,
        "expected_reward_per_cycle": expected,
        "long_run_expected_reward_per_hour": hourly,
        "formula": "3600 * reward * success_probability / cycle_seconds",
        "assumptions": ["每轮耗时相同；失败仍消耗完整周期", "每轮成功概率固定；无保底、共享掉落或额外准备时间",
                        "按完成起算的冷却与任务时间相加；按接取起算时取二者最大值", "结果为长期平均速率，不是首小时保证收入"],
    }


def probability_result(args: argparse.Namespace) -> dict:
    chance = args.success_probability
    count = args.attempts
    if count == 0 or chance == 0:
        at_least_one = 0.0
    elif chance == 1:
        at_least_one = 1.0
    else:
        at_least_one = -math.expm1(count * math.log1p(-chance))
    return {
        "kind": "independent_probability",
        "inputs": {"success_probability": chance, "attempts": count},
        "expected_successes": chance * count,
        "probability_at_least_one_success": at_least_one,
        "formula": "1 - (1 - success_probability) ** attempts",
        "assumptions": ["每次试验相互独立，成功概率相同", "不适用于保底、概率递增、互斥或共享掉落"],
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="对给定模组设计参数进行确定性计算；不执行游戏或随机模拟")
    commands = parser.add_subparsers(dest="command", required=True)
    reward = commands.add_parser("reward", help="长期平均奖励速率")
    reward.add_argument("--reward", type=finite_nonnegative, required=True)
    reward.add_argument("--success-probability", type=probability, default=1.0)
    reward.add_argument("--task-seconds", type=finite_nonnegative, required=True)
    reward.add_argument("--cooldown-seconds", type=finite_nonnegative, required=True)
    reward.add_argument("--cooldown-start", choices=("completion", "acceptance"), required=True)
    chances = commands.add_parser("probability", help="独立重复试验至少成功一次的概率")
    chances.add_argument("--success-probability", type=probability, required=True)
    chances.add_argument("--attempts", type=attempts, required=True)
    args = parser.parse_args()
    try:
        result = reward_result(args) if args.command == "reward" else probability_result(args)
    except ValueError as exc:
        parser.error(str(exc))
    result["evidence"] = "deterministic_input_calculation"
    result["game_tested"] = False
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
