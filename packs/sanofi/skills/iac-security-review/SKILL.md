---
name: iac-security-review
description: "Audit AWS infrastructure code for security — Terraform, CDK, SST, CloudFormation, Pulumi. Use when checking public S3 buckets, open security groups, wildcard IAM, missing encryption, unauthenticated API Gateway or Lambda URLs, logging gaps, hardcoded secrets, Sanofi tag and module policy, or triaging Checkov/Trivy/KICS. Read-only, evidence-graded report. Not for writing Terraform — iac-terraform instead; not CI/CD workflows — cicd-engineering."
---

# IaC Security Review

Static, read-only review of AWS infrastructure code (Terraform, CDK, SST, CloudFormation, Pulumi) against a control matrix and Sanofi tag and module policy: public exposure, IAM, encryption, network, logging, secrets. Output: an evidence-graded report. Governing principle: **absence is not exposure** — AWS defaults, account/org controls, and shared modules often supply what local code omits, so every finding carries an evidence status and severity is proven from code, never assumed.

Scope: Terraform authoring → iac-terraform · CI/CD workflows → cicd-engineering · app code → `/review`, `/security`. omp built-ins `/security` and `security-reviewer` run generic vulnerability discovery; this skill supplies the IaC resource-control matrix and Sanofi policy. Full security audit → run both; diffs → `/review`.

## References

| File | Read for |
|------|----------|
| [security-controls.md](skill://iac-security-review/references/security-controls.md) | Control IDs, per-framework checks, evidence status, severity rules |
| [aws-defaults.md](skill://iac-security-review/references/aws-defaults.md) | Current AWS defaults and sources; check before flagging absent properties |
| [scanners.md](skill://iac-security-review/references/scanners.md) | Optional Checkov/Trivy/KICS cross-check, uv install, safe invocation, suppressions, 2026 supply-chain warnings |
| [report.template.md](skill://iac-security-review/assets/report.template.md) | Report structure |

## Guardrails

- **NEVER modify IaC files.**
- **NEVER treat missing local configuration as proven exposure.** Absent + AWS default, account/org control, or shared module → Needs confirmation.
- **NEVER rate Critical without evidence** of reachability, authorization gap, and sensitive data or privilege.
- **NEVER invent application behavior or attack chains.** Unknown → say unknown.
- **Evidence:** MUST cite file:line and snippet per finding. **Exception — secret findings** (SM-01–SM-03, EN-07, any finding whose evidence contains a credential value): NEVER reproduce the value, in whole or in part, in the report, summary, or remediation. Cite file:line, replace the value with a redacted placeholder (`"<REDACTED:aws-access-key-id>"`), and state credential kind plus rotation guidance. Keep surrounding syntax so the finding stays locatable; no prefix, suffix, length, or hash of the value.
- **Remediation:** MUST be in the finding's own framework.
- **Coverage:** MUST run all applicable control groups; list skipped ones with reason.
- **Sanofi controls (SN-\*):** Sanofi repositories only.
- **Executive summary:** MUST emit even when clean.

## Workflow

### 1. Discovery

omp tools only; no shell needed.

| Framework | Step |
|-----------|------|
| Terraform | `glob` `**/*.tf`, skip `.terraform/` |
| CDK | `glob` `**/cdk.json`; `grep` `aws-cdk-lib` in `package.json` |
| SST | `glob` `**/sst.config.{ts,js}` |
| CloudFormation | `grep` `^Resources:` or `"Resources"` plus `Type: AWS::` or `"Type": "AWS::"` in `*.{yaml,yml,json,template}`; `AWSTemplateFormatVersion` optional |
| Pulumi | `glob` `**/Pulumi.yaml`; resources via `aws.` imports |

- **Environments:** from directories, workspaces, stack names, tfvars.
- **No IaC found?** STOP; tell the user.
- **> ~500 IaC files?** Ask for a narrower scope.
- **Mixed frameworks?** Review all; list in metadata.
- **Sanofi repo?** Check git remote and tag conventions; record the decision.

### 2. Inventory

`grep` resource declarations; `read` the files. Per resource: type, name, file:line, internet-facing, intended public (docs, comments, naming), relationships (CloudFront → API → Lambda). Terraform: also record the AWS provider constraint (`required_providers`, `.terraform.lock.hcl`) — defaults differ between provider 5.x and 6.x ([aws-defaults.md](skill://iac-security-review/references/aws-defaults.md)).

### 3. Analysis

Apply [security-controls.md](skill://iac-security-review/references/security-controls.md) per resource; check [aws-defaults.md](skill://iac-security-review/references/aws-defaults.md) before flagging any absent property. Per finding: control ID, severity, status (Confirmed / Needs confirmation), confidence, evidence, exposure analysis, remediation.

- **Suppressions:** `grep` `checkov:skip`, `trivy:ignore`, `kics-scan`; judge each suppressed control yourself.
- **Scanner cross-check:** MAY run; rules in [scanners.md](skill://iac-security-review/references/scanners.md). Hits are re-graded, never copied; scanner already installed or install approved by the user.
- **Large repos:** use one batched OMP `task` call with a `security-reviewer` per independent directory. Give every child the recorded scope, its directory, the applicable control/reference paths, the evidence-and-redaction rules above, and an instruction to return `findings`, `reviewed_paths`, and `deferred` only. The agent is read-only and has no `bash`; keep scanner runs, cross-directory paths, final control grading, and report integration with the parent.

### 4. Cross-Resource

- Layered controls on each public path: WAF, authorizer, backend authorization.
- Wildcard IAM blast radius.
- Environment drift: prod protections missing in dev/test.
- Traffic map through each layer; evidenced hops only.

### 5. Report

Fill [report.template.md](skill://iac-security-review/assets/report.template.md); `write` `audits/iac-security-review-YYYY-MM-DD.md`. Show the user:

```markdown
Overall risk: {level}
Findings: X Critical, Y High, Z Medium, W Low (N need confirmation)
Files scanned: N ({frameworks})
Report: audits/iac-security-review-YYYY-MM-DD.md
```

## Edge Cases

| Scenario | Action |
|----------|--------|
| Unrecognized resource type | Informational; manual review |
| Module without visible source | Needs confirmation; name the module |
| Central control absent from scope (trail, org BPA, WAF policy) | Not evidenced; request evidence |

## Verification

Before handing over the report:

- Every finding: file:line, snippet, status, framework-native fix. Secret findings: redacted placeholder, credential kind, rotation guidance; no raw value anywhere in the report.
- No Critical without reachability + impact evidence.
- Absent-property findings checked against aws-defaults.md.
- Sanofi section applied only for Sanofi repos; otherwise skip stated.
- Scanner hits re-graded, not copied.
- Skipped controls listed with reasons.
- No IaC file modified.
