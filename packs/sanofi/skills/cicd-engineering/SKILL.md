---
name: cicd-engineering
description: GitHub Actions CI/CD for Sanofi repos - workflows, quality and security gates, SonarCloud, CodeGuard, AWS OIDC, image promotion, action pinning, attestations. Use when writing, reviewing, or hardening .github/workflows, or adding SAST, SCA, or coverage gates. Not for app review (code-review), Terraform (iac-terraform, iac-security-review), non-GitHub CI.
---

# CI/CD Engineering

Sanofi GitHub Actions rules and verified templates. Complements the built-in `/review` and `/security` commands: those find generic defects; this skill supplies the Sanofi runner, allowlist, gate, and promotion policy.

## References

- [cicd-rules.md](references/cicd-rules.md): requirements, review checklist, compliance gaps, troubleshooting.
- [pipeline-templates.md](references/pipeline-templates.md): verified action pins; Node, Python, Terraform, SonarCloud, container, CD, CodeGuard workflows.
- [security-hardening.md](references/security-hardening.md): supply chain, `pull_request_target`, injection, runners, OIDC trust policies, secrets, attestations, cache poisoning, sources.

Read only what the task needs.

## Workflow

1. Find workflows with `glob` (`.github/workflows/*.y*ml`), then `read` them with manifests, lockfiles, and build scripts.
2. Classify the pipeline: build/test, publish, release, deploy, Terraform, SAST/SCA.
3. Apply the rules below; load `cicd-rules.md` for exact wording.
4. Reuse the repo's own scripts and package manager. NEVER invent a parallel build path.
5. Validate: `actionlint` when installed (v1.7.12 rejects the newer `cache-mode` key and `vulnerability-alerts` permission; see Failure Modes); otherwise parse each YAML file and check every `needs.<job>.outputs.<name>` and `secrets.<NAME>` reference resolves.
6. Report changed behavior, required secrets/environments/variables, and manual platform setup.

## Rules

- **Runner**: every job MUST use `runs-on: atmos-aws-arc-runner-set`; GitHub-hosted labels are prohibited.
- **Permissions**: declare `permissions:` at workflow and job level; NEVER `write-all`/`read-all`.
- **Pinning**: pin GitHub-published and verified-creator actions to a full commit SHA with a version comment.
- **Allowlist**: other third-party actions use the exact tag the allowlist registers. NEVER invent SHA pins for them.
- **Org workflows**: Sanofi org-managed reusable workflows (CodeGuard) MAY use `@main`; comment the exception.
- **Secrets**: scope per Environment; NEVER in files or logs. Prefer OIDC over long-lived cloud keys.
- **Reusable workflows**: callee declares `on.workflow_call.secrets`; caller passes named secrets. `secrets: inherit` only to org-managed workflows.
- **Injection**: pass PR/issue text through `env:`, never `${{ }}` inside `run:`.
- **Untrusted triggers**: `pull_request_target` and `workflow_run` MUST NOT check out or execute PR code or trust downloaded artifacts. They run from the default branch and see secrets. Their caches stay `cache-mode: read`.
- **Security steps**: NEVER `continue-on-error: true` on SAST, SCA, secret scan, or gate steps.
- **Installs**: commit lockfiles; use deterministic installs (`npm ci`, `uv sync --frozen`).
- **SCA/SAST**: every repo runs both in CI with blocking results. CodeGuard preferred; SonarCloud adds quality gating; CodeQL is the fallback.
- **Coverage**: Sonar imports reports through `sonar-project.properties`, and the scan waits for the quality gate (`sonar.qualitygate.wait=true`). The aggregate required check MUST depend on the Sonar job.
- **Artifacts**: build once, promote the same image digest through dev → test → prod. NEVER rebuild per environment. Production images SHOULD carry a build-provenance attestation ([security-hardening.md §11](references/security-hardening.md#11-artifact-attestations-and-provenance)).
- **Deploy**: render a new ECS task-definition revision with the digest, deploy it, wait for stability.
- **Retention**: set `retention-days`; key caches on lockfile hashes.
- **Action updates**: enable Dependabot `github-actions` so SHA pins move through reviewed PRs ([security-hardening.md §1](references/security-hardening.md#1-supply-chain-attacks-via-compromised-actions)).
- **GxP**: production promotion needs environment approval and a retained audit record.

## Failure Modes

| Bad | Good |
| --- | --- |
| Pin `git/ref/tags/TAG` `.object.sha` | `gh api repos/O/R/commits/refs/tags/TAG --jq .sha` |
| `update-service --force-new-deployment` to ship a new image | Render task definition with digest, then deploy it |
| `workflow_run` job checks out `github.sha` | Use `workflow_run.id`/`head_sha`; deploy CI's recorded digest |
| Callee requests `pull-requests: read` the caller never granted | Grant at the calling job; callee cannot elevate |
| `terraform init` job without `environment:` for `JFROG_TOKEN` | Bind the environment on every job that initializes |
| Sonar scan without gate wait, excluded from `Build Complete` | `sonar.qualitygate.wait=true`, job in `needs` |
| OIDC trust copied as `repo:ORG/REPO:...` | Confirm the repo's `sub` format (name or owner/repo IDs) first |
| Tag pin of an action still on `node20` | Upgrade to a release declaring `node24`; Node 20 is gone from runners |
| Delete `cache-mode`/`vulnerability-alerts` because `actionlint` flags them | Keep them; they are valid GitHub syntax that `actionlint` v1.7.12 does not know yet |
| Rely on Dependabot alerts for SHA-pinned actions | Alerts cover only semver-tagged actions; keep the version comment and Dependabot version updates |
| Environment rule `refs/heads/feature` for a `pull_request` job | PR jobs evaluate `refs/pull/N/merge`; `pull_request_target` evaluates the default branch |
| Trust policy assumes only workflows reach the role | Dependabot OIDC tokens carry `event_name: dynamic`; GitHub states AWS lacks custom-claim conditions, so keep an exact `sub` plus an environment with deployment rules |

## Siblings

- Application code review: `code-review` skill.
- Terraform authoring and tags: `iac-terraform` skill. IaC security audit: `iac-security-review` skill.
- Release notes and versioning schemes: [cicd-rules.md §4.2](references/cicd-rules.md#42-version-artifacts-and-generate-release-notes). Dependency remediation: Dependabot/Renovate PRs.
- Tyr and other org-managed scanners: ask the platform team for the current reference; no template here.

## Checklist

- Every `uses:` pinned or allowlisted; pins verified against the tag's commit.
- Every `needs.*.outputs.*` and `secrets.*` reference resolves to a declared output/secret.
- Sonar gate blocks: `Build Complete` fails when Sonar fails.
- Deploy consumes the digest; summary prints it.
- Required secrets, environments, branch rules, and allowlist changes listed in the report.
- No `pull_request_target`/`workflow_run` job checks out or runs PR code; cache access on those triggers is read-only.
- Production images have a provenance attestation, or the report says why not.
