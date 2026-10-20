---
name: cicd-engineering
description: "Write, review, and fix Sanofi GitHub Actions workflows and CI security gates. Use when touching runner, permissions, action pinning and allowlist, SAST/SCA, SonarCloud coverage gate, CodeGuard, AWS OIDC, image promotion to ECS, attestations, pull_request_target, cache poisoning, or actionlint findings. Not for Terraform authoring (iac-terraform), IaC security audits (iac-security-review), or non-GitHub CI."
---

# CI/CD Engineering

Sanofi GitHub Actions rules and verified templates: workflows, quality and security gates (SAST, SCA, coverage), SonarCloud, CodeGuard, AWS OIDC, image promotion, action pinning, attestations. Complements the built-in `/review` and `/security` commands: those find generic defects; this skill supplies the Sanofi runner, allowlist, gate, and promotion policy. Governing principle: pick the strongest control the Sanofi allowlist and platform accept, not the strongest in principle. Pins, trust policies, and gate wiring that look correct but contradict the allowlist or the repo's real `sub` format fail at runtime.

## Reference Map

| File | Holds |
| --- | --- |
| [cicd-rules.md](skill://cicd-engineering/references/cicd-rules.md) | Requirements by domain, review checklist, compliance gaps, troubleshooting |
| [pipeline-templates.md](skill://cicd-engineering/references/pipeline-templates.md) | Verified action pins; Node, Python, Terraform, SonarCloud, container, CD, CodeGuard workflows |
| [security-hardening.md](skill://cicd-engineering/references/security-hardening.md) | Supply chain, `pull_request_target`, injection, runners, OIDC trust policies, secrets, attestations, cache poisoning, sources |

Load only what the task needs.

## Workflow

1. `glob` `.github/workflows/*.y*ml`; `read` them with manifests, lockfiles, build scripts.
2. Classify: build/test · publish · release · deploy · Terraform · SAST/SCA.
3. Apply Rules below; load `cicd-rules.md` for exact wording.
4. Reuse the repo's own scripts and package manager. NEVER invent a parallel build path.
5. Validate with `uvx --from actionlint-py actionlint` (or installed `actionlint`).
   - Unknown runner label → `atmos-aws-arc-runner-set` must be under `self-hosted-runner.labels` in `.github/actionlint.yaml`.
   - v1.7.12 also rejects the newer `cache-mode` key and `vulnerability-alerts` permission (see Failure Modes).
   - No `actionlint` → parse each YAML file; check every `needs.<job>.outputs.<name>` and `secrets.<NAME>` reference resolves.
6. Verify on GitHub when a run exists: `xd://github` `op: run_watch` (omit `run` → every run for the current HEAD, fast-fails on the first failed job; a failing run the user names → `run: <id or URL>`, raise `tail` for more lines per failed job). Failure logs land in a session artifact: diagnose from that log, not from the YAML alone. NEVER push to trigger a run without the user's go-ahead.
7. Report changed behavior, required secrets/environments/variables, manual platform setup.

## Rules

| Area | Rule |
| --- | --- |
| **Runner** | Every job MUST use `runs-on: atmos-aws-arc-runner-set`; GitHub-hosted labels prohibited |
| **Permissions** | Declare a read-only `permissions:` at workflow level; expand per job only where needed; NEVER `write-all`/`read-all` |
| **Pinning** | GitHub-published and verified-creator actions → full commit SHA + version comment |
| **Allowlist** | Other third-party actions → the exact tag the allowlist registers; NEVER invent SHA pins |
| **Org workflows** | Sanofi org-managed reusable workflows (CodeGuard) MAY use `@main`; comment the exception |
| **Secrets** | Scope per Environment; NEVER in files or logs; prefer OIDC over long-lived cloud keys |
| **Reusable workflows** | Callee declares `on.workflow_call.secrets`; caller passes named secrets; `secrets: inherit` only to org-managed workflows |
| **Injection** | Untrusted PR/issue text via `env:`; NEVER interpolate attacker-controlled `${{ }}` expressions inside `run:` |
| **Untrusted triggers** | `pull_request_target`, `workflow_run` MUST NOT check out or execute PR code or trust downloaded artifacts: they run from the default branch and see secrets. Caches stay `cache-mode: read` |
| **Security steps** | NEVER `continue-on-error: true` on SAST, SCA, secret scan, or gate steps |
| **Installs** | Commit lockfiles; deterministic installs (`npm ci`, `uv sync --locked`). Python CI: `astral-sh/setup-uv` + `uv run`, not `setup-python` + `pip install`; keep a repo's existing tooling (poetry, pip-tools) and say how to adopt uv |
| **SCA/SAST** | Every repo runs both in CI, blocking. CodeGuard preferred; SonarCloud adds quality gating; CodeQL fallback |
| **Coverage** | Sonar imports reports via `sonar-project.properties`; scan waits for the gate (`sonar.qualitygate.wait=true`); the aggregate required check MUST depend on the Sonar job |
| **Artifacts** | Build once; promote the same image digest dev → test → prod; NEVER rebuild per environment. Production images SHOULD carry a build-provenance attestation ([security-hardening.md §11](skill://cicd-engineering/references/security-hardening.md#11-artifact-attestations-and-provenance)) |
| **Deploy** | Render a new ECS task-definition revision with the digest, deploy it, wait for stability |
| **Retention** | Set `retention-days`; key caches on lockfile hashes |
| **Action updates** | Enable Dependabot `github-actions` so SHA pins move through reviewed PRs ([security-hardening.md §1](skill://cicd-engineering/references/security-hardening.md#1-supply-chain-attacks-via-compromised-actions)) |
| **GxP** | Production promotion needs environment approval and a retained audit record |

## Failure Modes

| Bad | Good |
| --- | --- |
| Pin `git/ref/tags/TAG` `.object.sha` | `gh api repos/O/R/commits/refs/tags/TAG --jq .sha` |
| `update-service --force-new-deployment` to ship a new image | Render task definition with digest, then deploy it |
| `workflow_run` job checks out `github.sha` | Use `workflow_run.id`/`head_sha`; deploy CI's recorded digest |
| Callee requests `pull-requests: read` the caller never granted | Grant at the calling job; callee cannot elevate |
| Job receiving `JFROG_TOKEN`/AWS credentials, or running credentialed `terraform init`/plan/apply, without `environment:` | Bind the protected environment and approval gate on every credentialed job; secretless PR `init -backend=false`/`validate` needs none |
| Sonar scan without gate wait, excluded from `Build Complete` | `sonar.qualitygate.wait=true`, job in `needs` |
| OIDC trust copied as `repo:ORG/REPO:...` | Confirm the repo's `sub` format (name or owner/repo IDs) first |
| Tag pin of an action still on `node20` | Upgrade to a release declaring `node24`; Node 20 is gone from runners. Check with `xd://github` `op: file_read`, `path: action.yml` (or `action.yaml`), `branch: <tag>` → `runs.using` |
| Delete `cache-mode`/`vulnerability-alerts` because `actionlint` flags them | Keep them; valid GitHub syntax that `actionlint` v1.7.12 does not know yet |
| Rely on Dependabot alerts for SHA-pinned actions | Alerts cover only semver-tagged actions; keep the version comment and Dependabot version updates |
| Environment rule `refs/heads/feature` for a `pull_request` job | PR jobs evaluate `refs/pull/N/merge`; `pull_request_target` evaluates the default branch |
| Trust policy assumes only workflows reach the role | Dependabot OIDC tokens carry `event_name: dynamic`; GitHub states AWS lacks custom-claim conditions → keep an exact `sub` plus an environment with deployment rules |

## Before Reporting

- Every `uses:` pinned or allowlisted; pins verified against the tag's commit.
- Every `needs.*.outputs.*` and `secrets.*` reference resolves to a declared output/secret.
- Sonar gate blocks: `Build Complete` fails when Sonar fails.
- Deploy consumes the digest; summary prints it.
- Required secrets, environments, branch rules, allowlist changes listed in the report.
- No `pull_request_target`/`workflow_run` job checks out or runs PR code; cache access on those triggers read-only.
- Production images have a provenance attestation, or the report says why not.

## Sibling Skills

| Need | Go to |
| --- | --- |
| Application code review | omp `/review` |
| Terraform authoring and tags | `iac-terraform` |
| IaC security audit | `iac-security-review` |
| Release notes and versioning schemes | [cicd-rules.md §4.2](skill://cicd-engineering/references/cicd-rules.md#42-version-artifacts-and-generate-release-notes) |
| Dependency remediation | Dependabot/Renovate PRs |
| Tyr and other org-managed scanners | Ask the platform team for the current reference; no template here |
