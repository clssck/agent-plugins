---
name: iac-terraform
description: "Use when authoring or reviewing AWS Terraform at Sanofi: picking terraform-aws-library modules, pinning module versions, applying or checking the 10 mandatory tags, S3 backend locking, AWS provider v6 upgrades, secrets via write-only arguments, terraform test, or validating a plan with check_tags.py. Not for IaC security audits — iac-security-review instead; not for CI/CD pipelines — cicd-engineering instead."
---

# Terraform IaC

Author or review AWS Terraform built from `Sanofi-InnerSource/terraform-aws-library` modules, with pinned versions and the full Sanofi tag set: module choice, tag application or checking, project validation. Governing principle: **library module + pinned version + `local.tags` + evaluated-plan verification**. Source greps and guessed values ship non-compliant infrastructure.

Complements built-in `/review`: that finds generic defects; this skill checks module, tag, and validation conventions. Non-AWS IaC out of scope.

## References

| File | Covers |
| --- | --- |
| [module-guide.md](references/module-guide.md) | discovery commands, version constraints + AWS provider v6 changes, S3 backend locking, `terraform test`, secrets, module catalog, project layout, pinning, sources |
| [tagging-guide.md](references/tagging-guide.md) | mandatory tag values, `local.tags` pattern, `default_tags` limits, effective-tag check, sources |
| [scripts/check_tags.py](scripts/check_tags.py) | validates tags on every resource in a plan JSON; tests in [scripts/test_check_tags.py](scripts/test_check_tags.py); invocation → [tagging-guide.md](references/tagging-guide.md#effective-tag-check) |

## Rules

- **Modules**: approved library module exists → use it. NEVER write a raw `aws_*` resource for it.
- **Read first**: module README + `variables.tf` before writing a call.
- **Pins**: pin every module `version`; NEVER float.
- **Tags**: all 10 mandatory tags on every taggable resource.
- **Missing values**: ASK for team, cost center, application ID, contact, environment. NEVER guess.
- **Sensitive settings**: NEVER guess network, IAM, encryption, or environment values.
- **Secrets**: NEVER hardcode → [module-guide.md](references/module-guide.md#secrets).
- **Apply**: NEVER run `terraform apply`. `plan` only on user authorization.
- **Backend**: new S3 backends use `use_lockfile = true`; NEVER add `dynamodb_table` → [module-guide.md](references/module-guide.md#state-backend).
- **Versions**: `required_version` + provider floors = what the code needs, compatible with every module → [module-guide.md](references/module-guide.md#versions-and-providers).
- **Tests**: NEVER run `terraform test` unmocked; default `command = apply` creates real resources → [module-guide.md](references/module-guide.md#testing).
- **Plan files**: `tfplan` + `plan.json` hold secrets in cleartext; NEVER commit or paste them.

## Workflow

1. **Scope**: service, environment, modules needed, missing inputs. Existing code → `glob` `**/*.tf` (excluding `.terraform/`), then `read`.
2. **Discover** modules + RFC guidance → [module-guide.md](references/module-guide.md#discovery). Confluence CODE-space docs → `search-company-knowledge` skill.
3. **Implement**: pinned modules, `tags = local.tags` → [tagging-guide.md](references/tagging-guide.md). No library module → state the reason in the report.
4. **Validate locally** (order matters; private modules need JFrog credentials for `init` → [module-guide.md](references/module-guide.md#validation)):

   ```bash
   terraform fmt -check -recursive
   terraform init -backend=false
   terraform validate
   ```

5. **Check effective tags** from a plan the user ran: `terraform show -json tfplan` → `check_tags.py`.
6. **Report**: manual prerequisites, unknown tag values, provider assumptions, open questions.

## Failure Modes

| Bad | Good |
| --- | --- |
| Only the 3 corporate tags | `local.tags` with all 10 |
| `variable "version"` | `app_version`; `version` is a reserved variable name |
| `application_id` derived from `cc-*`/`dp-*` cost center | Separate validated `application_id` variable |
| `terraform validate` before `init` | `terraform init -backend=false` first |
| `gh search code ... --path accepted` | `gh search code 'tagging path:accepted' --repo OWNER/REPO` |
| `grep` for tag names in `*.tf` | Evaluate tags from plan JSON |
| `password_wo` set but `password_wo_version` unchanged on rotation | Increment the `*_version` argument |
| `data "aws_secretsmanager_secret_version"` feeding a resource | `ephemeral` block feeding a write-only argument |
| `data.aws_region.current.name` on provider 6 | `.region` |
| Tags on `aws_autoscaling_group` via `default_tags` only | `tag` blocks from `local.tags` |

## Verification

Done when each holds, or its blocker is reported:

- Every resource from a library module, or stated reason no module exists.
- Every module call pins `version` and passes `tags = local.tags`.
- `terraform fmt -check`, `init -backend=false`, `validate` pass.
- Backend uses `use_lockfile`; `versions.tf` floors match features used.
- Plan JSON passes `check_tags.py`, or user has not yet produced a plan.
- Security review handed to `iac-security-review`.

## Siblings

| Need | Skill |
| --- | --- |
| Security audit of Terraform, CDK, CloudFormation. NEVER duplicate its findings or severity model here. | `iac-security-review` |
| GitHub Actions Terraform plan/apply workflows; JFrog credentials in CI | `cicd-engineering` |
| Confluence + company knowledge lookups | `search-company-knowledge` |
