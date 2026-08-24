#!/usr/bin/env python3
"""Download DCM project files from the latest deployment.

Usage:
    python scripts/download_project.py <project_name> --connection <connection> --target <target_folder>
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_snow(args: list[str]) -> str:
    """Run a snow CLI command and return stdout. Exits on failure."""
    result = subprocess.run(["snow"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running: snow {' '.join(args)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download DCM project files from the latest deployment."
    )
    parser.add_argument("project_name", help="Name of the DCM project")
    parser.add_argument("--connection", required=True, help="Snowflake connection name")
    parser.add_argument("--target", required=True, help="Local folder to download files into")
    args = parser.parse_args()

    print("=== DCM Project Download ===")
    print(f"Project:    {args.project_name}")
    print(f"Connection: {args.connection}")
    print(f"Target:     {args.target}")
    print()

    # Describe project
    print("Fetching project description...")
    print(run_snow(["dcm", "describe", args.project_name, "-c", args.connection]))

    # Get latest deployment
    print("Fetching deployments...")
    deployments_json = run_snow(
        ["dcm", "list-deployments", args.project_name, "-c", args.connection, "--format", "json"]
    )

    deployments = json.loads(deployments_json)
    if not deployments:
        print(f"Error: No deployments found for project {args.project_name}", file=sys.stderr)
        sys.exit(1)

    deployment_path = deployments[0].get("deployment_file_path", "")
    if not deployment_path:
        print("Error: Could not find deployment_file_path in response", file=sys.stderr)
        sys.exit(1)

    print(f"Latest deployment path: {deployment_path}")

    # Extract deployment ID from path like:
    # snow://project/DB.SCHEMA.PROJECT/deployments/deployment$1/
    parts = deployment_path.rstrip("/").split("/")
    try:
        dep_idx = parts.index("deployments")
        deployment_id = parts[dep_idx + 1]
    except (ValueError, IndexError):
        print(f"Error: Could not parse deployment ID from path: {deployment_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Deployment ID: {deployment_id}")
    print()

    # List files in sources
    sources_path = f"snow://project/{args.project_name}/deployments/{deployment_id}/sources"
    print(f"Listing files from: {sources_path}")
    files_json = run_snow(["stage", "list-files", sources_path, "-c", args.connection, "--format", "json"])

    files = json.loads(files_json)
    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)

    print()
    print("Downloading files...")

    for file_entry in files:
        file_path = file_entry.get("name", "")
        if not file_path:
            continue

        # Skip files in sources/out/
        if "/sources/out/" in file_path:
            print(f"Skipping (in out/): {file_path}")
            continue

        # Extract relative path after sources/
        # Format: /deployments/deployment$1/sources/definitions/infrastructure.sql
        marker = "/sources/"
        idx = file_path.find(marker)
        if idx == -1:
            print(f"Skipping (unexpected path format): {file_path}")
            continue
        relative_path = file_path[idx + len(marker):]

        # Create target directory structure
        file_dir = Path(relative_path).parent
        copy_target = target / file_dir
        copy_target.mkdir(parents=True, exist_ok=True)

        # Construct snow:// URL and download
        file_url = f"snow://project/{args.project_name}/deployments/{deployment_id}/sources/{relative_path}"
        print(f"Downloading: {relative_path}")
        run_snow(["stage", "copy", file_url, str(copy_target), "-c", args.connection])

    print()
    print("=== Download Complete ===")
    print(f"Files downloaded to: {args.target}")


if __name__ == "__main__":
    main()
