from __future__ import annotations

STATUS_LABELS = {"queued": "排队中", "running": "讨论中", "completed": "评审收敛", "needs_review": "仍需人工评审", "cancelled": "已停止", "failed": "运行失败", "interrupted": "运行中断"}


def render_report(meeting: dict, *, transcript: bool = True) -> str:
    simulation = meeting["provider_mode"] == "simulation"
    lines = ["# Minecraft UGC · AI 圆桌会议记录", "",
             "> 规则模拟：本记录来自预设流程夹具，不是 AI 推理、Spark 性能或真实开发成果。" if simulation else
             "> OpenClaw 模型评审记录：结论属于设计建议，不代表已经通过 ModSDK / 游戏内验证。",
             "", f"- 会议：{meeting['id']}", f"- 状态：{STATUS_LABELS[meeting['status']]}",
             f"- 轮次：{meeting['current_round']} / {meeting['max_rounds']}",
             f"- 模式：{meeting['provider_mode']}", f"- 创建时间：{meeting['created_at']}",
             "", "## 议题", "", meeting["topic"], "", "## 约束", "", meeting["constraints"] or "未提供额外约束。",
             "", "## 当前方案", "", meeting.get("proposal") or "尚未形成方案。", "", "## 分歧记录", ""]
    for issue in meeting["issues"]:
        state = "已关闭" if issue["status"] == "resolved" else "未解决"
        lines += [f"### {issue['id']} · {issue['title']} · {state}", "",
                  f"提出者：{issue['owner_role_id']}；级别：{issue['severity']}；轮次：{issue['created_round']}",
                  "", issue["detail"], "", f"关闭依据：{issue.get('resolution') or '待提出者复核'}", ""]
    if not meeting["issues"]:
        lines += ["暂无已登记分歧。", ""]
    if meeting.get("error"):
        lines += ["## 运行说明", "", meeting["error"], ""]
    lines += ["## 验证边界", "", "本次仅进行方案评审。SDK 接口可用性、脚本运行时、数值仿真和游戏效果需分别取得实际验证证据。",
              "Skills 记录表示本地技能内容已提供给角色；仅凭模型自报引用不能证明外部工具执行或目标 OpenClaw 安装正确。", ""]
    if transcript:
        lines += ["## 完整发言", ""]
        for turn in meeting["turns"]:
            lines += [f"### 第 {turn['round']} 轮 · {turn['role_name']} · {turn['phase']}", "", turn["summary"], "",
                      f"意见：{turn['stance']}；用时：{turn['elapsed_ms']} ms",
                      f"提供的 Skill：{turn['provided_skill_id']}；内容 SHA-256：{turn['skill_sha256']}", ""]
            for path, digest in turn.get("reference_sha256", {}).items():
                lines += [f"提供的参考资料：{path}；SHA-256：{digest}", ""]
            for recommendation in turn["recommendations"]:
                lines += [f"- {recommendation}"]
            if turn["recommendations"]:
                lines += [""]
            for concern in turn["concerns"]:
                lines += [f"保留意见（{concern['severity']}）：{concern['title']} — {concern['detail']}", ""]
            if turn["resolved_issue_ids"]:
                lines += ["本次申请关闭：" + "、".join(turn["resolved_issue_ids"]) + "。是否接受以分歧记录与事件日志为准。", ""]
            if turn["phase"] in {"opening", "synthesis"} and turn["proposal"]:
                lines += ["本次提交的方案：", "", turn["proposal"], ""]
    return "\n".join(lines).rstrip() + "\n"
