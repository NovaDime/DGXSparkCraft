from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROLE_SPECS = [
    {"id": "host", "name": "主管虾", "title": "会议主持", "description": "组织议题、整理分歧、形成可复核的结论。", "skill_id": "roundtable-host"},
    {"id": "planner", "name": "策划虾", "title": "玩法策划", "description": "审阅玩家体验、玩法规则与边界情况。", "skill_id": "minecraft-design"},
    {"id": "balance", "name": "数值虾", "title": "数值评审", "description": "检查奖励、概率、成长与经济循环的合理性。", "skill_id": "minecraft-balance"},
    {"id": "engineer", "name": "程序虾皮", "title": "技术可行性", "description": "依据目标 ModSDK 评估实现路径和约束。", "skill_id": "modsdk-feasibility"},
    {"id": "audio", "name": "调音虾尾", "title": "配音与交互音效", "description": "设计 NPC 对白、物品与交互音效，复核声音资源和触发规则。", "skill_id": "minecraft-audio"},
    {"id": "art", "name": "美术虾绘", "title": "像素贴图与特效", "description": "设计 UI 九宫格、物品贴图和序列帧，并交付资源接入合同。", "skill_id": "minecraft-art"},
    {"id": "reviewer", "name": "程序虾米", "title": "独立逻辑审查", "description": "质疑重复触发、状态同步与异常处理设计。", "skill_id": "modsdk-review"},
]


class SkillCatalog:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def get(self, skill_id: str) -> dict:
        if skill_id not in {role["skill_id"] for role in ROLE_SPECS} | {"modsdk-coding", "repository-learning"}:
            raise KeyError(skill_id)
        folder = (self.root / skill_id).resolve()
        if not folder.is_relative_to(self.root):
            raise ValueError("Skill 路径超出项目目录")
        path = (folder / "SKILL.md").resolve()
        if not path.is_relative_to(folder):
            raise ValueError("Skill 文件必须位于项目技能目录内")
        content = path.read_text(encoding="utf-8")
        front = content.split("---", 2)
        if len(front) != 3 or front[0].strip():
            raise ValueError(f"{skill_id} 缺少 YAML frontmatter")
        name = re.search(r"^name:\s*(.+)$", front[1], re.M)
        description = re.search(r"^description:\s*(.+)$", front[1], re.M)
        if not name or not description:
            raise ValueError(f"{skill_id} 缺少 name 或 description")
        references = []
        reference_contents = {}
        if (folder / "references").exists():
            for ref in sorted((folder / "references").glob("*.md")):
                if not ref.resolve().is_relative_to(folder):
                    raise ValueError("参考资料路径超出 Skill 目录")
                name_in_skill = ref.relative_to(folder).as_posix()
                references.append(name_in_skill)
                reference_contents[name_in_skill] = ref.read_text(encoding="utf-8")
        if getattr(self, 'learning', None):
            learned = self.learning.context(skill_id)
            if learned:
                reference_contents['learned/repository-lessons.md'] = learned
                references.append('learned/repository-lessons.md')
        return {"id": skill_id, "name": name.group(1).strip().strip("\"'"),
                "description": description.group(1).strip().strip("\"'"),
                "content": content, "references": references, "reference_contents": reference_contents,
                "sha256": hashlib.sha256(content.encode()).hexdigest()}

    def all(self) -> list[dict]:
        return [self.get(role["skill_id"]) for role in ROLE_SPECS]

    def role(self, role_id: str, agent_ids: dict[str, str]) -> dict:
        spec = next(dict(role) for role in ROLE_SPECS if role["id"] == role_id)
        skill = self.get(spec["skill_id"])
        content = skill["content"]
        reference_hashes = {}
        for path, text in skill["reference_contents"].items():
            content += f"\n\n---\n项目参考资料：{path}\n\n{text}"
            reference_hashes[path] = hashlib.sha256(text.encode()).hexdigest()
        spec.update(agent_id=agent_ids[role_id], skill_content=content, skill_sha256=skill["sha256"], reference_sha256=reference_hashes)
        return spec
