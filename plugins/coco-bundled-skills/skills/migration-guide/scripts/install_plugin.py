#!/usr/bin/env python3
"""Install the Snowflake migrations plugin and disable the bundled stub.

Runs `cortex plugin install <url>` to clone and register the managed plugin,
runs the plugin's session-start hook to install runtime dependencies, then
mutates `~/.snowflake/cortex/settings.json` to add `migration-guide` to
`disableBundledSkills` so the stub stops firing on migration triggers.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_URL = "https://github.com/Snowflake-Labs/cortex-code-migrations/tree/preview/plugin"
PLUGIN_NAME = "snowflake-migration"
SETTINGS_PATH = Path.home() / ".snowflake" / "cortex" / "settings.json"
PLUGIN_ROOT = Path.home() / ".snowflake" / "cortex" / "plugins" / PLUGIN_NAME
SESSION_START_HOOK = PLUGIN_ROOT / "hooks" / "session-start.cmd"
SKILL_NAME = "migration-guide"


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        text = SETTINGS_PATH.read_text(encoding="utf-8").strip()
        if text:
            return json.loads(text)
    return {}


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )


def install_plugin() -> None:
    if shutil.which("cortex") is None:
        print(
            "ERROR: `cortex` CLI not found on PATH.\n"
            "Install Cortex Code first, then re-run this script."
        )
        sys.exit(1)
    result = subprocess.run(
        ["cortex", "plugin", "install", PLUGIN_URL],
        check=False,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)


def run_session_start_hook() -> None:
    if not SESSION_START_HOOK.exists():
        print(f"ERROR: session-start hook not found at {SESSION_START_HOOK}")
        sys.exit(1)
    if sys.platform == "win32":
        cmd = ["cmd.exe", "/c", str(SESSION_START_HOOK)]
    else:
        cmd = ["sh", str(SESSION_START_HOOK)]
    print(f"Running session-start hook: {SESSION_START_HOOK}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        sys.exit(result.returncode)


def disable_bundled_stub() -> None:
    settings = load_settings()
    disabled = settings.setdefault("disableBundledSkills", [])
    if SKILL_NAME in disabled:
        print(f"Bundled '{SKILL_NAME}' stub already disabled in {SETTINGS_PATH}")
        return
    disabled.append(SKILL_NAME)
    save_settings(settings)
    print(f"Disabled bundled '{SKILL_NAME}' stub in {SETTINGS_PATH}")


def main() -> None:
    install_plugin()
    run_session_start_hook()
    disable_bundled_stub()


if __name__ == "__main__":
    main()
