"""Resolved filesystem locations for scripts, rules, prompts and langpacks."""

from pathlib import Path

__layer__ = "infrastructure"
__pattern__ = "Configuration Path Registry"
__owns__ = "canonical plugin directory and scripts path resolution"

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent
SKILL_DIR = SCRIPTS_DIR.parent
PLUGIN_DIR = SKILL_DIR.parent.parent
AGENTS_DIR = PLUGIN_DIR / "agents"
REFS_DIR = SKILL_DIR / "references"
PROMPTS_DIR = SKILL_DIR / "prompts"
LANGPACK_DIR = SKILL_DIR / "langpack"
DEFAULT_RULES_DIR = SCRIPTS_DIR / "rules"
DEFAULT_PROVIDERS_CONFIG = SCRIPTS_DIR / "providers.config.json"
