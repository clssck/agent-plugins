# IaC Security Review Report Template

Save to `audits/iac-security-review-YYYY-MM-DD.md`. Copy the structure below. Omit empty subsections; keep the executive summary even when clean.

````markdown
# Infrastructure Security Review

## 1. Metadata

| Field | Value |
|-------|-------|
| Review date | YYYY-MM-DD |
| Repository | {name} |
| Environments | {dev, test, prod as detected} |
| Frameworks | {Terraform, CDK, SST, CloudFormation, Pulumi} |
| Files scanned | {count} |
| Scope | Static IaC only; no cloud account access |
| Sanofi controls | Applied / Skipped ({reason}) |
| Standards referenced | {e.g. CIS AWS Foundations, NIST SP 800-53} |

## 2. Executive Summary

**Overall risk**: Critical / High / Medium / Low / Clean

| Severity | Confirmed | Needs confirmation |
|----------|-----------|--------------------|
| Critical | X | X |
| High | X | X |
| Medium | X | X |
| Low | X | X |
| Informational | X | X |

**Top findings**: {one line per Critical/High}

**Not evidenced in scope**: {controls that need external evidence, e.g. organization CloudTrail}

## 3. Resource Inventory

| Type | Name | File:line | Internet-facing | Intended public? | Auth | Notes |
|------|------|-----------|-----------------|------------------|------|-------|
| HTTP API | orders-api | infra/api.ts:42 | Yes | Yes (documented) | JWT authorizer | |

## 4. Findings

### F1: {title}

| Attribute | Value |
|-----------|-------|
| Control | {ID, e.g. PE-02} |
| Severity | Critical / High / Medium / Low / Informational |
| Status | Confirmed / Needs confirmation |
| Confidence | High / Medium / Low |

**Evidence**: `path/to/file` lines X-Y
```hcl
{snippet in the source language}
```

**Exposure analysis**: {intended exposure, reachable operations, authorization at each layer, data or privilege impact; mark application behavior as unknown when not visible in IaC}

**Exploit path** (Critical/High, Confirmed only): {steps supported by the code; no invented endpoints or data}

**Confirm by** (Needs confirmation only): {exact artifact or owner that settles it}

**Remediation**:
```hcl
{corrected code in the same framework}
```

**Effort**: Minimal / Low / Moderate / High / Extensive

## 5. Cross-Resource Findings

- Defense in depth: {public paths lacking layered controls}
- Blast radius: {wildcard IAM reaching other services}
- Environment drift: {controls present in prod, missing elsewhere}
- Traffic map: `Internet → CloudFront → API Gateway → Lambda → DynamoDB` {annotate each hop's controls}

## 6. Recommendations

1. Immediate (Critical/High): {action + file}
2. Short term (Medium): {action}
3. Long term (Low/Informational): {action}

## 7. Appendix

- Files scanned: {list}
- Controls evaluated: {IDs}
- Controls not applicable: {ID: reason}
- Complementary scans: {`/security` or `security-reviewer` findings, if run}
````

## Effort Scale

| Level | Time | Scope |
|-------|------|-------|
| Minimal | <1 hour | Single config change |
| Low | 1-4 hours | One resource or module |
| Moderate | 0.5-2 days | Multi-service impact |
| High | 2-5 days | Architectural impact |
| Extensive | >5 days | Policy-level change |
