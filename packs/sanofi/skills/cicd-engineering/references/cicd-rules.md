# Sanofi CI/CD Rules

Sanofi source of truth for GitHub Actions CI/CD, by functional domain; RFC 2119 keywords. Sanofi-specific patterns (§6) override generic guidance. Copy-paste workflows: [pipeline-templates.md](skill://cicd-engineering/references/pipeline-templates.md). Attack vectors and mitigations: [security-hardening.md](skill://cicd-engineering/references/security-hardening.md).

## Contents

1. Workflow Security
2. Quality Gates
3. Supply Chain Integrity
4. Deployment & Environments
5. Operational Hygiene
6. Sanofi-Specific Patterns
7. Workflow Review Checklist, Common Compliance Gaps, Troubleshooting

---

## 1. Workflow Security

Pipelines run with high privileges → treat every workflow file as production code.

### 1.1 Reference actions in a form the Sanofi allowlist accepts

An **org-level allowlist** governs GitHub Actions at Sanofi: a well-formed workflow still fails at runtime when the action it calls is not permitted. Rule: pick the strongest pinning form the allowlist accepts, not the strongest in principle.

| Action source | Reference form |
| --- | --- |
| GitHub-published, verified creators | Allowed broadly; SHOULD pin full 40-char commit SHA + version comment, so a compromised maintainer tag cannot swap the code running with your `GITHUB_TOKEN` |
| Other third-party | MUST be explicitly allowlisted before it runs. Entries are tag-based, not SHA-based → a SHA pin for a non-listed action is rejected however secure. Use the exact registered reference (normally a tag such as `@v2`); request new actions/versions from the platform team. NEVER invent SHA pins the allowlist has not cleared |
| Sanofi-managed reusable workflows (e.g. CodeGuard `cyber-AST-Action_reusable`) | MAY use `@main`: centrally reviewed, no third-party supply-chain risk. Comment the exception |

```yaml
# GOOD — GitHub-published action, pinned SHA, version comment for humans
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```

Resolve a tag to its commit; dereferences annotated tags; same text runs in bash, zsh, and PowerShell:

```bash
gh api repos/actions/checkout/commits/refs/tags/v7.0.1 --jq .sha
```

NEVER pin `gh api repos/OWNER/REPO/git/ref/tags/TAG --jq .object.sha` output without checking `.object.type`: for an annotated tag it is the tag object SHA, not a commit. Pick the version from `gh release view --repo OWNER/REPO`; verified pins: [pipeline-templates.md](skill://cicd-engineering/references/pipeline-templates.md#action-pins).

**Org SHA-pin policy.** GitHub can enforce full-SHA pins and block specific versions at org level. If the platform team enables it, tag-based allowlist entries fail; follow what the platform team publishes and NEVER disable the policy to make a run pass.

### 1.2 Set explicit, least-privilege `permissions`

**Every workflow MUST declare a `permissions:` block.** Missing or `write-all` permissions let a compromised action push to protected branches, approve PRs, or publish packages.

```yaml
# Workflow-level default: read-only
permissions:
  contents: read

jobs:
  publish:
    # Narrow expansion only in the job that needs it
    permissions:
      contents: read
      packages: write
```

Common patterns:

| Workflow type   | Permissions                         |
| --------------- | ----------------------------------- |
| Build + test    | `contents: read`                    |
| Publish package | `contents: read`, `packages: write` |
| Create release  | `contents: write`                   |
| PR comment      | `pull-requests: write`              |
| Deploy via OIDC | `contents: read`, `id-token: write` |
| Code scanning   | `security-events: write`            |

`write-all`, `read-all`: **prohibited**. Reusable workflow callers MUST declare their own `permissions:` block — inherited permissions are not safe.

### 1.3 Manage secrets through GitHub Environments or approved vaults

**Secrets MUST NOT appear in workflow files, committed configs, or logs.** Secrets MUST be scoped per environment (dev / test / prod) with separate values; one `API_KEY` shared across environments is **prohibited**.

```yaml
# GOOD — secret scoped to the 'production' environment
jobs:
  deploy:
    environment: production
    steps:
      - run: deploy
        env:
          API_KEY: ${{ secrets.API_KEY }} # the CLI reads API_KEY from the environment (or stdin); NEVER pass it in argv or interpolate it into `run:`

# BAD — never hardcode secrets
env:
  API_KEY: sk-1234567890
```

- **Storage**: **GitHub Environments** or **AWS Secrets Manager** (the approved Sanofi vault).
- **Prod approval**: production environments SHOULD require manual approval via environment protection rules; MUST for GxP — regulatory change control requires a recorded approval step.
- **Scanning**: secret scanning MUST be enabled org-wide (GitHub secret scanning; GitGuardian for Sanofi). Exposed credentials MUST be revoked and rotated immediately.
- **Avoid `secrets: inherit`** to reusable workflows unless the callee is org-managed. Declare `on.workflow_call.secrets` for every secret the caller passes; pass only the named secrets it needs. A callee job setting `environment` receives that environment's secrets without the caller passing them (the `SONAR_TOKEN` pattern in §2.2). See [security-hardening.md](skill://cicd-engineering/references/security-hardening.md#8-environment-scoped-secrets-vs-secrets-inherit).

### 1.4 Prefer OIDC over long-lived cloud credentials

**Workflows SHOULD authenticate to cloud providers via OIDC federation** (short-lived, scoped tokens), not long-lived keys stored as secrets. AWS:

```yaml
permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    environment: ${{ inputs.env }}
    steps:
      - uses: aws-actions/configure-aws-credentials@e1253824e5c10ff9df46874f81ed3ec929e19cfd # v6.3.0
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/App_githubrunners_accelerator_${{ inputs.env }}
          aws-region: eu-west-1
```

IAM trust policy MUST scope the `sub` claim to the specific repo **and** environment; separate roles per environment (dev / test / prod). Discover the repo's actual `sub` format first (name-based or immutable owner/repo IDs); template and discovery command: [security-hardening.md](skill://cicd-engineering/references/security-hardening.md#6-oidc-for-aws-role-per-environment-pattern). Long-lived cloud keys in `secrets`: compliance gap → remove once OIDC is in place.

### 1.5 Prevent workflow injection

Attacker-controlled strings (PR title, branch name, issue body) interpolated into `run:` → command injection. **Never interpolate user-controlled expressions directly in shell commands**; pass them through environment variables.

```yaml
# BAD — PR title is interpolated into the shell
- run: echo "Processing ${{ github.event.pull_request.title }}"

# GOOD — PR title becomes a shell variable, not a shell token
- env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: echo "Processing $PR_TITLE"
```

Dangerous expressions: `github.event.pull_request.{title,body}`, `github.event.issue.{title,body}`, `github.event.comment.body`, `github.head_ref`, `github.event.pull_request.head.ref`.

`pull_request_target` MUST NOT check out code from the PR head; safe two-workflow alternative in `references/security-hardening.md`.

### 1.6 Never use `continue-on-error: true` on security steps

`continue-on-error: true` silently swallows failures: on SAST, dependency audit, secret scanning, or compliance steps the workflow reports green while a vulnerability ships. **Prohibited on any security-related step.**

### 1.7 Define workflows as code, detect workflow drift

**All CI/CD workflows MUST live in `.github/workflows/` under version control.** UI-defined jobs, manual tweaks, undocumented deviations from the committed files: prohibited.

_Drift_ here: **workflow-configuration drift** — committed workflow files diverging from org-level reference templates or policy rules (e.g. a team copies a template, later removes the SAST step or moves `runs-on` off the ARC runner). Detect with:

- `actionlint` for syntax and security patterns
- OPA/Conftest or reusable workflow policies for org-level rules
- PR checks comparing workflow files against reference templates

Exemptions (e.g. hotfix deviations) MUST be documented and time-bound.

> Scope note: this section covers the workflow files themselves. Infrastructure drift (deployed state vs. IaC) → `iac-terraform` skill; dependency drift → Dependabot or Renovate PRs.

---

## 2. Quality Gates

### 2.1 Lint, format, and type-check in CI

**Every repo MUST run lint, format, and type-check jobs that block merge on failure**, automated on every PR; manual enforcement does not scale.

| Language        | Lint                   | Format           | Types          |
| --------------- | ---------------------- | ---------------- | -------------- |
| TypeScript / JS | ESLint / Biome         | Prettier / Biome | `tsc --noEmit` |
| Python          | Ruff / Flake8 / Pylint | Black / Ruff     | mypy / Pyright |
| Go              | golangci-lint          | gofmt            | compiler       |

Runs SHOULD be **parallel jobs**, not one serial step, so developers see all failures at once:

```yaml
jobs:
  format: # Prettier check
  lint: # ESLint
  typecheck: # tsc --noEmit
  test: # Unit tests with coverage
  build:
    needs: [format, lint, typecheck, test]
    # Summary job — final gate
```

Config files (`.eslintrc`, `.prettierrc`, `tsconfig.json`, `pyproject.toml`) MUST be committed. Pre-commit hooks SHOULD run the same checks locally.

### 2.2 Enforce coverage thresholds via SonarCloud

**Every repo with automated tests MUST enforce a minimum coverage threshold**; merges dropping coverage below baseline MUST be blocked. Sanofi measures and enforces coverage with **SonarCloud** (Sanofi's managed SonarQube tenant); deviations from the standard Sanofi SonarCloud configuration require explicit approval.

Three pieces make the gate real; full workflow in [pipeline-templates.md](skill://cicd-engineering/references/pipeline-templates.md#sonarcloud-analysis-reusable):

1. Tests write a coverage report the Sonar language plugin reads (LCOV for JavaScript/TypeScript, Cobertura XML for Python) and upload it as an artifact.
2. `sonar-project.properties` imports it: `sonar.javascript.lcov.reportPaths` or `sonar.python.coverage.reportPaths`. An uploaded artifact alone is NOT imported coverage.
3. The scan runs with `-Dsonar.qualitygate.wait=true`, and the aggregate required check (`Build Complete`) depends on the Sonar job. Alternative: require the SonarCloud status check in branch protection.

```yaml
- uses: SonarSource/sonarqube-scan-action@d209202bc7d53ff1cc128f7f907dac145c9d6ae9 # v8.3.0
  env:
    SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
  with:
    args: >
      -Dsonar.qualitygate.wait=true
      -Dsonar.qualitygate.timeout=300
```

`SONAR_TOKEN` is an Environment secret on a `sonarcloud` environment with required reviewers; the reusable workflow's job sets `environment: sonarcloud` and callers pass no secret. Unapproved PR validation stays secretless.

---

## 3. Supply Chain Integrity

### 3.1 Commit lockfiles

**Lockfiles (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `Pipfile.lock`, `poetry.lock`) MUST be committed** for deterministic builds. CI MUST use deterministic installs (`npm ci`, `pipenv sync`, `uv sync --locked`, `bundle install --deployment`) and MUST fail when the lockfile is missing or out of sync (`--frozen` installs from a stale `uv.lock` without failing; use `--locked`).

Lockfile updates flow through PRs so dependency changes get reviewed; Dependabot or Renovate SHOULD automate them. Enable Dependabot `github-actions` updates so SHA pins and reusable workflow references refresh in reviewed PRs ([security-hardening.md §1](skill://cicd-engineering/references/security-hardening.md#1-supply-chain-attacks-via-compromised-actions)). Dependabot alerts do not cover SHA-pinned actions.

### 3.2 Audit dependencies automatically (SCA)

**Every repo MUST run automated dependency audits in CI** covering:

- **Security vulnerabilities** in direct **and** transitive dependencies
- **License compliance** against the approved list
- **Version freshness** (no deprecated or end-of-life libraries)

Critical vulnerabilities MUST block merge until remediated.

| Severity | Remediation SLA |
| --- | --- |
| Critical | within 7 days |
| High | within 14 days |
| Medium / low | team discretion, tracked |

Sanofi: use a Cybersecurity-provided tool (Checkmarx / CodeGuard SCA, or GitHub Dependabot) via the standard reusable workflows. Minimal inline examples:

```yaml
# Node.js — lightweight gate
- run: npm audit --audit-level=high

# Python (uv project: export the lock, audit the pinned set)
- run: uv export --locked --no-emit-project --format requirements.txt -o requirements-audit.txt
- run: uvx pip-audit@2.10.1 --strict --disable-pip -r requirements-audit.txt
```

Dependabot or Renovate SHOULD open PRs for vulnerable packages automatically.

### 3.3 Run SAST in the pipeline

**Every repo MUST integrate a SAST tool into CI** with blocking results. Preferred: **CodeGuard** (Checkmarx-based) via the org-level reusable workflow. **SonarCloud** adds quality + security scanning. **CodeQL**: acceptable fallback when CodeGuard is unavailable.

```yaml
jobs:
  codeguard:
    # Org-managed reusable workflow — @main acceptable (see §1.1 exception)
    uses: Sanofi-Shared-GitHub-Apps/cyber-AST-Action_reusable/.github/workflows/code_guard_ast.yml@main
    with:
      production-branch: main
      groups: Digital-Accelerator
      cmdb: ${{ vars.cmdb }}
      codeguard-gate: true
    secrets:
      CX_CLIENT_ID: ${{ secrets.CHECKMARX_CX_CLIENT_ID }}
      CX_CLIENT_SECRET: ${{ secrets.CHECKMARX_CX_CLIENT_SECRET }}
```

SAST findings MUST NOT be gated by `continue-on-error: true`.

### 3.4 Generate and keep an SBOM

Production-bound projects SHOULD generate a Software Bill of Materials (SBOM, CycloneDX or SPDX) at release time and store it alongside the release artifact. SBOMs feed SLSA provenance, vulnerability response, and license audits.

| Ecosystem | SBOM tooling |
| --- | --- |
| Node.js | `@cyclonedx/cyclonedx-npm` |
| Python | `uv export --locked --format cyclonedx1.5 -o sbom.cdx.json` (experimental in uv 0.12; prints a preview warning), `cyclonedx-py`, `pip-audit --format cyclonedx` |
| Container | Syft (`anchore/sbom-action`) |

SBOMs SHOULD be signed together with the release artifact (§3.5).

### 3.5 Sign and verify release artifacts (recommended)

**Production-bound artifacts SHOULD be cryptographically signed during CI and verified before deployment.** Unsigned artifacts SHOULD NOT be promoted to production registries.

- **Sigstore / cosign** for containers and generic artifacts; keyless OIDC flow preferred over long-lived keys.
- **SLSA provenance attestations** record builder, inputs, and timestamp.
- Configure the registry (ECR, JFrog) to reject unsigned uploads where supported.
- Rotate signing keys at least every 6 months; SHOULD prefer Sigstore keyless to avoid key rotation entirely.

Teams MUST document their signing process (tools, key management, verification gates) in the project runbook. Attestation command, inputs, permissions, prerequisites, verification: [security-hardening.md §11](skill://cicd-engineering/references/security-hardening.md#11-artifact-attestations-and-provenance). Verify with `gh attestation verify` before promoting a digest.

---

## 4. Deployment & Environments

### 4.1 Follow the dev → test → prod promotion flow

**Production deployments MUST go through dev → test → prod** with quality/security gates and approvals at each stage. Direct feature-branch-to-prod: **prohibited** outside documented emergency hotfix procedures.

Standard Sanofi pattern: build the image once in CI, then `workflow_run` (auto-deploy to dev when CI succeeds) + `workflow_dispatch` (manual promotion to test and prod). Both deploy the **image digest recorded by a specific CI run**, NEVER a rebuild and NEVER the branch tip. Full workflows: [pipeline-templates.md](skill://cicd-engineering/references/pipeline-templates.md#cd-auto-deploy--manual-promotion-to-ecs).

```yaml
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        type: choice
        options: [dev, test, prod]
      ci-run-id:
        description: "Successful CI run on main whose image to deploy"
        type: string
```

`workflow_run` workflows execute against the default-branch tip, not the commit CI tested → resolve everything from `github.event.workflow_run.id` / `head_sha`; NEVER build or check out from `github.sha` there.

- **Same artifact**: one image digest, deployed unchanged to dev, test, and prod (build once, deploy many).
- **Environment-specific secrets and IAM roles.**
- **Approval gate on `prod`** via GitHub Environment protection rules. Manual approval **required for GxP**, SHOULD be the default elsewhere; automated promotion (e.g. continuous delivery with progressive rollout and automated rollback) acceptable for non-GxP projects when documented in the runbook.
- Promotion flow documented in the project runbook.
- Canary or blue-green deployments SHOULD be validated in `test` before prod promotion.

### 4.2 Version artifacts and generate release notes

**Every repo producing release artifacts MUST declare a documented versioning scheme and MUST auto-generate release notes** from commits or PR metadata. Scheme depends on what the repo produces:

| Produces | Scheme |
| --- | --- |
| Published libraries, SDKs, CLIs, container images consumed by others | **Semantic Versioning** (`MAJOR.MINOR.PATCH`); consumers rely on semver to reason about breaking changes |
| Continuously deployed services / applications | Semver **not required**; any monotonic, traceable scheme (date-based `YYYY.MM.DD.N`, commit SHA, incremental build number). A service has no public API version surface for semver to describe; forcing it manufactures meaningless major bumps |
| Published HTTP/gRPC APIs | Version the API contract independently (URL path, `Accept` header), not tied to the deployable artifact version |

Approved tooling: **Release Please** (Google) — recommended for libraries / published artifacts · `semantic-release` — libraries · GitHub's built-in release notes generator — any repo.

Release notes MUST include contributors, bug fixes, new features, and explicit breaking-change callouts. Release tags SHOULD be signed (§3.5). SBOMs and vulnerability reports SHOULD be published alongside release notes.

---

## 5. Operational Hygiene

### 5.1 Clean up artifacts and temporary resources

**CI/CD pipelines MUST apply retention policies** to artifacts, logs, caches, and preview environments; stale resources inflate cost and expand the attack surface.

| Resource | Default |
| --- | --- |
| Artifacts | `retention-days: 7` for day-to-day build outputs; GitHub's 90-day default for persistent artifacts |
| Preview environments | destroyed automatically on branch merge or close |
| Untagged container images | purged after 14–30 days via registry lifecycle rules |
| Release artifacts and SBOMs | archived to long-term storage (e.g. S3 Glacier) |
| GxP artifacts | retained per regulatory requirements (longer than defaults) |

```yaml
- uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
  with:
    name: coverage_result
    path: coverage/
    retention-days: 7
```

### 5.2 Use deterministic caching (recommended)

**Caches SHOULD be keyed on lockfile or dependency hashes**, not branch names or static strings; non-deterministic keys cause silent cache corruption and hidden dependency drift.

```yaml
- uses: actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0
  with:
    path: node_modules
    key: ${{ runner.os }}-node-${{ hashFiles('package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
```

Workflows triggered by `pull_request_target`, `issue_comment`, or fork `workflow_run` MUST NOT save caches: GitHub issues them read-only cache tokens, and an explicit `cache-mode: write` overrides that safeguard. See [security-hardening.md §12](skill://cicd-engineering/references/security-hardening.md#12-cache-poisoning-and-cache-mode).

Caches MAY be force-refreshed periodically (e.g. weekly per project, monthly at org level) to flush stale dependencies and reclaim storage; cadence left to each team / platform owner unless a documented org-level policy applies.

### 5.3 Produce audit-ready logs with appropriate retention

**CI/CD pipelines MUST produce complete, centralized logs** with retention aligned to compliance needs.

- **SIEM** automatically ingests all CI/CD logs; Cybersecurity sets retention.
- **Regular projects**: GitHub default 90-day log retention.
- **GxP projects**: retention and immutability MUST match regulatory requirements; logs MUST go to tamper-proof storage (e.g. write-once S3, append-only index).

Logs SHOULD capture commit SHA, actor, artifact hash, and deployment target. Use `run-name` on workflows and `$GITHUB_STEP_SUMMARY` for human-readable run summaries:

```yaml
run-name: ${{ github.workflow }} - ${{ github.ref_name }}
```

```yaml
# Inside a job
- run: |
    echo "### Coverage" >> "$GITHUB_STEP_SUMMARY"
    echo "- Lines: 87%" >> "$GITHUB_STEP_SUMMARY"
```

---

## 6. Sanofi-Specific Patterns

Non-negotiable at Sanofi; override generic CI/CD guidance.

### 6.1 Use the Sanofi-managed ARC runner

**All jobs MUST use `runs-on: atmos-aws-arc-runner-set`.** GitHub-hosted runners (`ubuntu-latest`, `windows-latest`, `macos-latest`): **prohibited**. The ARC runner set provides ephemeral, pre-hardened runners managed by the platform team — the only approved execution environment for Sanofi CI/CD.

```yaml
# GOOD
jobs:
  build:
    runs-on: atmos-aws-arc-runner-set

# BAD — GitHub-hosted runner
jobs:
  build:
    runs-on: ubuntu-latest
```

### 6.2 CodeGuard (Checkmarx SAST)

Org-level reusable workflow satisfying the SAST requirement (§3.3). Runs on `schedule`, `push` to main, and via `workflow_call`. MAY use `@main` (§1.1 exception). Full template: [pipeline-templates.md](skill://cicd-engineering/references/pipeline-templates.md#codeguard--checkmarx-sast).

### 6.3 Tyr compliance scanning

Tyr (`tsg-tyr`): org-managed governance and policy-compliance workflow. No Tyr template or interface documentation here; take the current reference and inputs from the platform team, and apply the same `@main` exception and explicit-secrets rule as CodeGuard.

### 6.4 SonarCloud quality gating

One reusable workflow (`sonarcloud.yaml`) serves pull-request analysis and the main-branch baseline, waits for the quality gate, and feeds `Build Complete` (§2.2). Full template: [pipeline-templates.md](skill://cicd-engineering/references/pipeline-templates.md#sonarcloud-analysis-reusable).

### 6.5 JFrog Artifactory for Terraform modules

Private Terraform modules come from Sanofi's JFrog Artifactory. The JFrog token MUST be a GitHub Environment secret (not repo-level) → every job receiving it MUST set `environment:`, and that environment MUST have required reviewers or a `main`-only deployment branch rule. `pull_request` validation MUST be secretless: no `environment:`, no `secrets.*`, no `id-token: write`. Same-repository PRs run PR-controlled Terraform, so credentialed `init`/`plan` MUST run only after an environment approval gate or from a trusted ref (`workflow_dispatch` on `main`). Credentials written at runtime only (`hashicorp/setup-terraform` `cli_config_credentials_*` inputs, or a `.terraformrc` created in the job). See [security-hardening.md](skill://cicd-engineering/references/security-hardening.md#7-jfrog-credentials-via-terraformrc) and the [Terraform template](skill://cicd-engineering/references/pipeline-templates.md#terraform-plan--apply).

---

## Workflow Review Checklist

When reviewing `.github/workflows/*.yml`:

**Workflow security**

- [ ] All jobs use `runs-on: atmos-aws-arc-runner-set`
- [ ] Actions referenced in a form the Sanofi allowlist accepts: GitHub-published / verified-creator actions pinned to 40-char SHA; other third-party actions use the exact tag registered in the allowlist; Sanofi org-managed reusable workflows on `@main`
- [ ] `permissions:` block present at workflow level, minimal and explicit
- [ ] No `permissions: write-all` or `read-all`
- [ ] No hardcoded secrets; secrets scoped per environment
- [ ] No `secrets: inherit` except to Sanofi org-managed reusable workflows
- [ ] No `pull_request_target` checking out PR head code
- [ ] `pull_request_target`/`workflow_run` jobs do not run PR code, do not execute downloaded artifacts, and keep `cache-mode: read`
- [ ] Dependabot `github-actions` ecosystem configured
- [ ] No user-controlled expressions (`github.event.*.title/body`, `head_ref`) interpolated into `run:`
- [ ] No `continue-on-error: true` on SAST, audit, or compliance steps

**Quality gates**

- [ ] Parallel lint / format / typecheck / test jobs
- [ ] All block merge on failure
- [ ] Coverage flows into SonarCloud quality gate
- [ ] Configuration files committed (`.eslintrc`, `tsconfig.json`, etc.)

**Supply chain**

- [ ] Lockfile present and enforced (`npm ci` / `uv sync --locked` / etc.)
- [ ] Dependency audit job (CodeGuard SCA, `npm audit`, `pip-audit`)
- [ ] SAST job (CodeGuard preferred, SonarCloud or CodeQL acceptable)
- [ ] SBOM generated for production-bound artifacts
- [ ] Artifact signing for production releases (recommended)
- [ ] Provenance attestation for production images (confirm the plan and allowlist first)

**Deployment**

- [ ] dev → test → prod promotion via GitHub Environments
- [ ] `prod` environment has an approval gate (manual approval required for GxP)
- [ ] OIDC to cloud providers (no long-lived access keys)
- [ ] Release versioning scheme documented and automated (semver for libraries; any traceable scheme for services)

**Hygiene**

- [ ] `retention-days` set on all `upload-artifact` calls
- [ ] Cache keys derived from `hashFiles('**/lockfile')`
- [ ] `run-name` set
- [ ] `$GITHUB_STEP_SUMMARY` used for audit-readable summaries

---

## Common Compliance Gaps

| Gap | Severity | Remediation |
| --- | --- | --- |
| GitHub-published action pinned to tag (`@v4`) not SHA | MUST-fix | Replace with full SHA + version comment |
| Third-party action not on the Sanofi allowlist | MUST-fix | Use the reference registered in the allowlist, or request an update from the platform team — do not invent SHA pins |
| Missing `permissions:` block | MUST-fix | Add explicit minimal block at workflow level |
| No dependency scanning step | MUST-fix | Add CodeGuard SCA reusable workflow or `npm audit --audit-level=high` |
| No SAST | MUST-fix | Add CodeGuard reusable workflow (preferred) or CodeQL |
| Coverage uploaded but no threshold | MUST-fix | Wire into SonarCloud quality gate |
| No artifact `retention-days` | MUST-fix | Add `retention-days: 7` (or team policy) |
| `continue-on-error: true` on security steps | MUST-fix | Remove — failures MUST block merge |
| `secrets: inherit` to non-org workflow | MUST-fix | Pass secrets explicitly |
| `runs-on: ubuntu-latest` or other GitHub-hosted runner | MUST-fix | Replace with `atmos-aws-arc-runner-set` |
| Long-lived cloud keys in GitHub Secrets | SHOULD-fix | Migrate to OIDC federation |
| No `run-name` | SHOULD-fix | Add descriptive `run-name` |
| No GHA cache for install step | SHOULD-fix | Add `actions/cache` keyed on lockfile hash |
| No SBOM at release | SHOULD-fix | Add CycloneDX or SPDX generation |

---

## Troubleshooting

| Symptom | Cause → action |
| --- | --- |
| No workflow files found | No `.github/workflows/` directory → new CI setup; generate from [pipeline-templates.md](skill://cicd-engineering/references/pipeline-templates.md) |
| Action SHA lookup fails | GitHub API rate limit or action repo inaccessible → authenticate `gh` and retry |
| Sanofi shared workflows not accessible | `Sanofi-Shared-GitHub-Apps` org requires specific access → verify org membership; if blocked, fall back to CodeQL for SAST while access is granted |
