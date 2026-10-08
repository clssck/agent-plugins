---
name: iac-terraform
description: Author or review AWS Terraform using Sanofi terraform-aws-library modules, pinned versions, and the mandatory tag set. Use when creating or changing AWS Terraform at Sanofi, picking a library module, applying or checking tags, or validating a project. Not for security audits (iac-security-review), CI/CD (cicd-engineering), or non-AWS IaC.
---

# Terraform IaC

Build AWS Terraform from `Sanofi-InnerSource/terraform-aws-library` modules with pinned versions and the full Sanofi tag set. Complements the built-in `/review` command: that finds generic defects; this skill checks module, tag, and validation conventions. Security analysis belongs to the `iac-security-review` skill.

## References

- [module-guide.md](references/module-guide.md): discovery commands, version constraints and AWS provider v6 changes, S3 backend locking, `terraform test`, secrets, module catalog, project layout, anti-patterns, sources.
- [tagging-guide.md](references/tagging-guide.md): mandatory tag values, `local.tags` pattern, `default_tags` limits, effective-tag check, sources.
- [scripts/check_tags.py](scripts/check_tags.py): validates tags on every resource in a plan JSON (run via `bash`, see tagging guide).

## Rules

- **Modules**: use an approved library module when one exists. NEVER write a raw `aws_*` resource for it.
- **Read first**: read the module README and `variables.tf` before writing a call.
- **Pins**: pin every module `version`; NEVER float.
- **Tags**: apply all 10 mandatory tags to every taggable resource.
- **Missing values**: ASK for team, cost center, application ID, contact, environment. NEVER guess.
- **Sensitive settings**: NEVER guess network, IAM, encryption, or environment values.
- **Secrets**: NEVER hardcode; see [module-guide.md](references/module-guide.md#secrets).
- **Apply**: NEVER run `terraform apply`. Run `plan` only when the user authorizes it.
- **Backend**: new S3 backends use `use_lockfile = true`; NEVER add `dynamodb_table` ([module-guide.md](references/module-guide.md#state-backend)).
- **Versions**: pick `required_version` and provider floors the code needs, compatible with every module ([module-guide.md](references/module-guide.md#versions-and-providers)).
- **Tests**: NEVER run `terraform test` unmocked; its default `command = apply` creates real resources ([module-guide.md](references/module-guide.md#testing)).
- **Plan files**: `tfplan` and `plan.json` hold secrets in cleartext; NEVER commit or paste them.

## Workflow

1. Identify service, environment, modules needed, and missing inputs. Find existing code with `glob` (`**/*.tf`, excluding `.terraform/`) and `read` it.
2. Discover modules and RFC guidance ([module-guide.md](references/module-guide.md#discovery)). Confluence CODE-space docs: use the `search-company-knowledge` skill.
3. Implement with pinned modules and `tags = local.tags` ([tagging-guide.md](references/tagging-guide.md)).
4. Validate locally: `terraform fmt -check -recursive`, `terraform init -backend=false`, `terraform validate`. Private modules need JFrog credentials for `init` ([module-guide.md](references/module-guide.md#validation)).
5. Check effective tags from a plan the user ran: `terraform show -json tfplan` into `check_tags.py`.
6. Report manual prerequisites, unknown tag values, provider assumptions, and open questions.

## Failure Modes

| Bad | Good |
| --- | --- |
| Raw `aws_s3_bucket` when `s3_bucket` module exists | Library module with pinned `version` |
| Only the 3 corporate tags | `local.tags` with all 10 |
| `variable "version"` | `app_version`; `version` is a reserved variable name |
| `application_id` derived from `cc-*`/`dp-*` cost center | Separate validated `application_id` variable |
| `terraform validate` before `init` | `terraform init -backend=false` first |
| `gh search code ... --path accepted` | `gh search code 'tagging path:accepted' --repo OWNER/REPO` |
| `grep` for tag names in `*.tf` | Evaluate tags from plan JSON |
| `dynamodb_table` in a new `backend "s3"` | `use_lockfile = true` (Terraform 1.11+) |
| `password_wo` set but `password_wo_version` unchanged on rotation | Increment the `*_version` argument |
| `data "aws_secretsmanager_secret_version"` feeding a resource | `ephemeral` block feeding a write-only argument |
| `data.aws_region.current.name` on provider 6 | `.region` |
| Tags on `aws_autoscaling_group` via `default_tags` only | `tag` blocks from `local.tags` |

## Siblings

- Security audit of Terraform, CDK, or CloudFormation: `iac-security-review` skill. NEVER duplicate its findings or severity model here.
- GitHub Actions Terraform plan/apply workflows and JFrog credentials in CI: `cicd-engineering` skill.
- Confluence and company knowledge lookups: `search-company-knowledge` skill.

## Checklist

- Every resource comes from a library module or has a stated reason no module exists.
- Every module call pins `version`; all calls pass `tags = local.tags`.
- `terraform fmt -check`, `init -backend=false`, and `validate` pass, or the blocker is reported.
- Backend uses `use_lockfile`; `versions.tf` floors match the features used.
- Plan JSON passes `check_tags.py`, or the user has not yet produced a plan.
- Security review handed to `iac-security-review`.
