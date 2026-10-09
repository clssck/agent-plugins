---
name: iac-security-review
description: AWS IaC security review with a control matrix for Terraform, CDK, SST, CloudFormation, and Pulumi, plus Sanofi tag and module policy. Use when auditing infrastructure code for public exposure, IAM, encryption, network, logging, or secrets. Not for authoring Terraform (iac-terraform), CI/CD workflows (cicd-engineering), or app code (/review, /security).
---

# IaC Security Review

Static, read-only review of AWS infrastructure code. Produces an evidence-graded report.

Complements omp built-ins: `/security` and `security-reviewer` run generic vulnerability discovery; this skill supplies the IaC resource-control matrix and Sanofi policy. Run both for a full security audit; use `/review` for diffs.

## References

| File | Read for |
|------|----------|
| [security-controls.md](references/security-controls.md) | Control IDs, per-framework checks, severity rules |
| [aws-defaults.md](references/aws-defaults.md) | Current AWS defaults and sources; check before flagging absent properties |
| [scanners.md](references/scanners.md) | Optional Checkov/Trivy/KICS cross-check, uv install, safe invocation, suppressions, 2026 supply-chain warnings |
| [report.template.md](assets/report.template.md) | Report structure |

## Guardrails

- NEVER modify IaC files.
- NEVER treat missing local configuration as proven exposure. Absent + AWS default, account/org control, or shared module → Needs confirmation.
- NEVER rate Critical without evidence of reachability, authorization gap, and sensitive data or privilege.
- NEVER invent application behavior or attack chains. Unknown → say unknown.
- MUST cite file:line and snippet per finding.
- MUST give remediation in the finding's own framework.
- MUST run all applicable control groups; list skipped ones with reason.
- MUST apply Sanofi controls (SN-*) only to Sanofi repositories.
- MUST emit the executive summary even when clean.

## Workflow

### 1. Discovery

Use omp tools; no shell needed.

| Framework | Step |
|-----------|------|
| Terraform | `glob` `**/*.tf`, skip `.terraform/` |
| CDK | `glob` `**/cdk.json`; `grep` `aws-cdk-lib` in `package.json` |
| SST | `glob` `**/sst.config.{ts,js}` |
| CloudFormation | `grep` `^Resources:` or `"Resources"` plus `Type: AWS::` or `"Type": "AWS::"` in `*.{yaml,yml,json,template}`. `AWSTemplateFormatVersion` is optional |
| Pulumi | `glob` `**/Pulumi.yaml`; resources via `aws.` imports |

- Identify environments from directories, workspaces, stack names, tfvars.
- No IaC found? STOP and tell the user.
- More than ~500 IaC files? Ask for a narrower scope.
- Mixed frameworks? Review all; list in metadata.
- Sanofi repo? Check git remote and tag conventions; note decision.

### 2. Inventory

`grep` resource declarations; `read` the files. Per resource record type, name, file:line, internet-facing, intended public (docs, comments, naming), and relationships (CloudFront → API → Lambda). Terraform: also record the AWS provider constraint (`required_providers`, `.terraform.lock.hcl`); defaults differ between provider 5.x and 6.x ([aws-defaults.md](references/aws-defaults.md)).

### 3. Analysis

For each resource, apply [security-controls.md](references/security-controls.md). Before flagging an absent property, check [aws-defaults.md](references/aws-defaults.md). Per finding record control ID, severity, status (Confirmed / Needs confirmation), confidence, evidence, exposure analysis, remediation. `grep` for scanner suppressions (`checkov:skip`, `trivy:ignore`, `kics-scan`) and judge each suppressed control. A scanner MAY cross-check the result: [scanners.md](references/scanners.md).

Large repos: delegate per directory with `task`; merge findings centrally.

### 4. Cross-Resource

- Layered controls on each public path (WAF, authorizer, backend authorization).
- Wildcard IAM blast radius.
- Environment drift (prod protections missing in dev/test).
- Traffic map through each layer, evidenced hops only.

### 5. Report

Fill [report.template.md](assets/report.template.md); `write` `audits/iac-security-review-YYYY-MM-DD.md`. Show the user:

```markdown
Overall risk: {level}
Findings: X Critical, Y High, Z Medium, W Low (N need confirmation)
Files scanned: N ({frameworks})
Report: audits/iac-security-review-YYYY-MM-DD.md
```

## Error Handling

| Scenario | Action |
|----------|--------|
| Unrecognized resource type | Informational; manual review |
| Module without visible source | Needs confirmation; name the module |
| Central control absent from scope (trail, org BPA, WAF policy) | Not evidenced; request evidence |

## Checklist

- Every finding has file:line, snippet, status, and framework-native fix.
- No Critical without reachability + impact evidence.
- Absent-property findings checked against aws-defaults.md.
- Sanofi section applied only for Sanofi repos.
- Scanner hits re-graded, not copied; scanner already installed or install approved by the user.
- Skipped controls listed with reasons.
- No IaC file modified.
