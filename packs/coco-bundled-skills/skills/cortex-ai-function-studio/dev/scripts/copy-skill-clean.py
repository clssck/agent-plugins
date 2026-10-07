#!/usr/bin/env python3
# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Copy a skill directory without local dependencies or generated artifacts.

By default this creates a sibling directory named ``<skill>-clean`` containing
only deployable skill contents. It excludes common local caches/deps and honors
the skill's ``.skillignore`` so test frameworks, dev tooling, virtualenvs, and
other maintainer-only files are left out.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
from pathlib import Path

DEFAULT_EXCLUDES = [
    ".git/",
    ".hg/",
    ".svn/",
    ".DS_Store",
    ".venv/",
    "venv/",
    "env/",
    "node_modules/",
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    ".coverage",
    "*.pyc",
    "*.pyo",
]


def normalize_pattern(pattern: str) -> str | None:
    pattern = pattern.strip()
    if not pattern or pattern.startswith("#"):
        return None
    return pattern.lstrip("/")


def load_patterns(source: Path, include_skillignore: bool) -> list[str]:
    patterns = list(DEFAULT_EXCLUDES)
    if include_skillignore:
        skillignore = source / ".skillignore"
        if skillignore.exists():
            for line in skillignore.read_text().splitlines():
                pattern = normalize_pattern(line)
                if pattern:
                    patterns.append(pattern)
    return patterns


def matches_pattern(relative_path: str, is_dir: bool, pattern: str) -> bool:
    pattern = pattern.rstrip() if pattern != " " else pattern
    directory_pattern = pattern.endswith("/")
    clean_pattern = pattern.rstrip("/")

    if directory_pattern and not is_dir:
        return False

    candidates = {relative_path}
    parts = relative_path.split("/")
    candidates.update(parts)
    if is_dir:
        candidates.add(relative_path + "/")

    if "/" not in clean_pattern:
        return any(
            fnmatch.fnmatch(candidate.rstrip("/"), clean_pattern)
            for candidate in candidates
        )

    return fnmatch.fnmatch(relative_path, clean_pattern) or relative_path.startswith(
        clean_pattern + "/"
    )


def should_exclude(path: Path, source: Path, patterns: list[str], is_dir: bool) -> bool:
    relative_path = path.relative_to(source).as_posix()
    return any(matches_pattern(relative_path, is_dir, pattern) for pattern in patterns)


def copy_clean(
    source: Path, destination: Path, patterns: list[str], force: bool
) -> tuple[int, int, int]:
    if destination.exists():
        if not force:
            raise SystemExit(
                f"Destination already exists: {destination}\nUse --force to replace it."
            )
        shutil.rmtree(destination)

    destination.mkdir(parents=True)
    copied = 0
    skipped = 0

    for root, dirs, files in os.walk(source):
        root_path = Path(root)

        kept_dirs = []
        for dirname in dirs:
            dir_path = root_path / dirname
            if should_exclude(dir_path, source, patterns, is_dir=True):
                skipped += 1
            else:
                kept_dirs.append(dirname)
        dirs[:] = kept_dirs

        relative_root = root_path.relative_to(source)
        target_root = destination / relative_root
        target_root.mkdir(parents=True, exist_ok=True)

        for filename in files:
            file_path = root_path / filename
            if should_exclude(file_path, source, patterns, is_dir=False):
                skipped += 1
                continue
            shutil.copy2(file_path, target_root / filename)
            copied += 1

    removed_empty_dirs = 0
    for path in sorted(
        destination.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                continue
            removed_empty_dirs += 1

    return copied, skipped, removed_empty_dirs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_source = Path("cortex-ai-function-studio")
    if not default_source.is_dir() and Path("SKILL.md").is_file():
        default_source = Path(".")

    parser.add_argument(
        "source", nargs="?", default=str(default_source), help="Skill directory to copy"
    )
    parser.add_argument(
        "destination", nargs="?", help="Destination directory; default: <source>-clean"
    )
    parser.add_argument(
        "--force", action="store_true", help="Replace destination if it already exists"
    )
    args = parser.parse_args()

    source = Path(args.source).resolve()
    if not source.is_dir():
        raise SystemExit(f"Source directory does not exist: {source}")

    destination = (
        Path(args.destination).resolve()
        if args.destination
        else source.with_name(f"{source.name}-clean")
    )
    if destination == source or source in destination.parents:
        raise SystemExit("Destination must not be the source directory or inside it.")

    patterns = load_patterns(source, include_skillignore=True)
    copied, skipped, removed_empty_dirs = copy_clean(
        source, destination, patterns, force=args.force
    )
    total = sum(1 for path in destination.rglob("*") if path.is_file())

    print(f"Copied {copied} files to {destination}")
    print(f"Skipped {skipped} excluded files/directories")
    print(f"Removed {removed_empty_dirs} empty directories")
    print(f"Destination file count: {total}")


if __name__ == "__main__":
    main()
