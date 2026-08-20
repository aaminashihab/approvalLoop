import os
import re
from typing import Optional
from pydantic import BaseModel, Field

class SkillManifest(BaseModel):
    name: str
    description: str
    trigger_conditions: list[str] = Field(default_factory=list)
    when_not_to_trigger: list[str] = Field(default_factory=list)
    body: str = ""
    skill_dir: str = ""

class SkillRegistry:
    """
    Runtime Skill Discovery & Progressive Disclosure Loader:
    Discovers skills in the skills/ directory and loads procedural knowledge
    at runtime during autonomous agent execution.
    
    Progressive Disclosure:
    1. Loads SKILL.md overview when skill triggers.
    2. Loads detailed reference files (e.g. references/escalation_policy.md) only when needed.
    """
    def __init__(self, skills_dir: Optional[str] = None):
        if skills_dir:
            self.skills_dir = os.path.abspath(skills_dir)
        else:
            # Look relative to project root
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            self.skills_dir = os.path.join(base_dir, "skills")
        self._skills_cache: dict[str, SkillManifest] = {}

    def get_skill(self, skill_name: str) -> Optional[SkillManifest]:
        """Loads and caches the skill overview using progressive disclosure."""
        if skill_name in self._skills_cache:
            return self._skills_cache[skill_name]

        target_dir = os.path.join(self.skills_dir, skill_name)
        skill_file = os.path.join(target_dir, "SKILL.md")
        if not os.path.exists(skill_file):
            return None

        with open(skill_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse YAML frontmatter with explicit section state tracking
        name = skill_name
        description = ""
        triggers: list[str] = []
        non_triggers: list[str] = []

        fm_match = re.search(r"^---\s*(.*?)\s*---", content, re.DOTALL)
        body = content
        if fm_match:
            frontmatter = fm_match.group(1)
            body = content[fm_match.end():].strip()
            
            current_section = None
            for raw_line in frontmatter.split("\n"):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip().strip("\"'")
                    current_section = None
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip().strip("\"'")
                    current_section = None
                elif line.startswith("trigger_conditions:"):
                    current_section = "trigger_conditions"
                elif line.startswith("when_not_to_trigger:"):
                    current_section = "when_not_to_trigger"
                elif line.startswith("- "):
                    item = line[2:].strip().strip("\"'")
                    if current_section == "trigger_conditions":
                        triggers.append(item)
                    elif current_section == "when_not_to_trigger":
                        non_triggers.append(item)
                elif ":" in line and not line.startswith("-"):
                    # Unrecognized key, reset section state
                    current_section = None

        manifest = SkillManifest(
            name=name,
            description=description,
            trigger_conditions=triggers,
            when_not_to_trigger=non_triggers,
            body=body,
            skill_dir=target_dir
        )
        self._skills_cache[skill_name] = manifest
        return manifest

    def load_skill_reference(self, skill_name: str, reference_filename: str) -> Optional[str]:
        """Progressive disclosure level 2: loads specific reference document on demand."""
        skill = self.get_skill(skill_name)
        if not skill:
            return None

        ref_path = os.path.join(skill.skill_dir, "references", reference_filename)
        if os.path.exists(ref_path):
            with open(ref_path, "r", encoding="utf-8") as f:
                return f.read()
        return None
