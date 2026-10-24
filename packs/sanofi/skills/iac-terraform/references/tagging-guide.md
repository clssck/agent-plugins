# Sanofi AWS Tagging Guide

Every taggable AWS resource carries 10 mandatory tags (accepted RFC, `Sanofi-Accelerator/Request-for-Comments`). Governing principle: one `local.tags` set per project, passed everywhere, verified on the evaluated plan. Live RFC + library tags module are the authority; re-verify before deployment ([module-guide.md](skill://iac-terraform/references/module-guide.md#discovery)).

## Contents

- [Mandatory tags](#mandatory-tags)
- [Environment mapping](#environment-mapping)
- [Standard implementation](#standard-implementation)
- [Provider default tags](#provider-default-tags)
- [tags_mandatory_tags module](#tags_mandatory_tags-module)
- [Effective-tag check](#effective-tag-check)
- [Common mistakes](#common-mistakes)
- [Sources](#sources)

## Mandatory tags

| Tag | Format | Example |
| --- | --- | --- |
| `team` | Single word, pod/team | `platform` |
| `name` | Alphanumeric, `-` or `_`; project name | `user-service` |
| `env` | `dev`, `test`, `prod` (lowercase) | `dev` |
| `version` | Semver of the deployed resources | `1.0.0` |
| `service` | Service identifier | `api-gateway` |
| `cost_center` | Prefix `cc-`, `dp-`, or `apm-` | `apm-1234567` |
| `contact` | Team/tech-lead email: non-empty local part, no whitespace or `@`, then `@sanofi.com` | `platform-team@sanofi.com` |
| `CE_Application_ID` | `APM` + 7 digits | `APM1234567` |
| `CE_Application_Name` | Free text, human-readable application name | `Order Portal` |
| `CE_Environment` | Uppercase `env` | `DEV` |

`CE_Application_ID` ↔ `cost_center`:

- `cost_center = apm-1234567` → `CE_Application_ID = APM1234567` (same digits, uppercase prefix).
- `cost_center = cc-*` or `dp-*` → no APM ID derivable. ASK the user. NEVER copy the cost center into `CE_Application_ID`.
- Company-wide cost-center → application mapping: [UNVERIFIED]. Use one only when the user or the RFC supplies it.

## Environment mapping

| `env` | `CE_Environment` | Use |
| --- | --- | --- |
| `dev` | `DEV` | Development/sandbox |
| `test` | `TEST` | QA/UAT, shared with business |
| `prod` | `PROD` | Production, change control |

## Standard implementation

Inputs avoid Terraform's reserved variable names (`source`, `version`, `providers`, `count`, `for_each`, `lifecycle`, `depends_on`, `locals`) ⇒ the `version` tag comes from `app_version`.

```hcl
# variables.tf
variable "team" {
  type        = string
  description = "Pod/team name (single word)"
}

variable "project_name" {
  type        = string
  description = "Custom project name (tag: name)"
}

variable "environment" {
  type        = string
  description = "Environment: dev, test, or prod"

  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be dev, test, or prod."
  }
}

variable "app_version" {
  type        = string
  description = "Deployed resource version (tag: version)"
  default     = "1.0.0"
}

variable "service" {
  type        = string
  description = "Service name"
}

variable "cost_center" {
  type        = string
  description = "Cost center code (cc-*, dp-*, or apm-*)"

  validation {
    condition     = can(regex("^(cc-|dp-|apm-)", var.cost_center))
    error_message = "Cost center must start with cc-, dp-, or apm-."
  }
}

variable "application_id" {
  type        = string
  description = "APM application ID (tag: CE_Application_ID), obtained from the application owner"

  validation {
    condition     = can(regex("^APM[0-9]{7}$", var.application_id))
    error_message = "Application ID must be APM followed by 7 digits."
  }
}

variable "application_name" {
  type        = string
  description = "CE_Application_Name value"
}

variable "contact_email" {
  type        = string
  description = "Team/tech lead email"

  validation {
    condition     = can(regex("^[^\\s@]+@sanofi\\.com$", var.contact_email))
    error_message = "Contact must be a local-part@sanofi.com email."
  }
}
```

```hcl
# locals.tf
locals {
  ce_environment_map = {
    dev  = "DEV"
    test = "TEST"
    prod = "PROD"
  }

  # Complete mandatory set: pass this everywhere
  tags = {
    # Accelerator team tags
    team        = var.team
    name        = var.project_name
    env         = var.environment
    version     = var.app_version
    service     = var.service
    cost_center = var.cost_center
    contact     = var.contact_email

    # Sanofi corporate tags
    CE_Application_ID   = var.application_id
    CE_Application_Name = var.application_name
    CE_Environment      = local.ce_environment_map[var.environment]
  }
}

# Cross-variable consistency (Terraform 1.5+ check block)
check "application_id_matches_cost_center" {
  assert {
    condition     = !startswith(var.cost_center, "apm-") || var.application_id == "APM${substr(var.cost_center, 4, -1)}"
    error_message = "application_id must carry the same digits as an apm-* cost_center."
  }
}
```

```hcl
# Every module call receives the full set
module "s3_bucket" {
  source  = "sanofi.jfrog.io/terraform-innersource-local__aws-services/s3_bucket/aws"
  version = "X.Y.Z" # replace with the released version

  tags = local.tags
}
```

Operational tags (`ManagedBy = "Terraform"`, `Repository`) MAY be merged: `merge(local.tags, { ManagedBy = "Terraform" })`. They never replace the 10.

## Provider default tags

Same map at the provider ⇒ raw resources and modules without a `tags` input are still covered:

```hcl
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.tags
  }
}
```

- Resource-level `tags` override `default_tags` for the same key (AWS provider 5+ allows duplicates and zero-value `""` tags). Effective set = read-only `tags_all`; `check_tags.py` reads it. Keep identical keys with identical values: a different value silently wins at the resource.
- `default_tags` = backstop. Still pass `tags = local.tags` to each module.
- `default_tags` does NOT cover `aws_autoscaling_group`; give it `tag` blocks (with `propagate_at_launch`) built from `local.tags`.
- Resources with no `tags` argument (some `aws_*` sub-resources): not taggable, not checked.
- `ignore_tags` (provider) or `lifecycle { ignore_changes = [tags] }` hides drift on those keys. NEVER apply either to the 10 mandatory tags. A key in both `ignore_tags` and a resource's `tags` → perpetual diff.
- Tag set only via `aws_ec2_tag` on a resource whose own `tags` argument is also managed → perpetual diff; use one or the other.
- Optional: AWS provider 6.22+ `tag_policy_compliance = "error"` fails plans missing tags required by the account's AWS Organizations tag policy. Runner role needs `tags:ListRequiredTags`; most SDKv2-based resources can only log a warning. Complements, never replaces, the 10-tag check.

## tags_mandatory_tags module

Library helper builds the corporate tags. Verify inputs in the module's `variables.tf`.

```hcl
module "tags" {
  source  = "sanofi.jfrog.io/terraform-innersource-local__aws-services/tags_mandatory_tags/aws"
  version = "X.Y.Z" # replace with the released version

  application_id   = var.application_id
  application_name = var.application_name
  environment      = local.ce_environment_map[var.environment]
}

locals {
  all_tags = merge(module.tags.tags, {
    team        = var.team
    name        = var.project_name
    env         = var.environment
    version     = var.app_version
    service     = var.service
    cost_center = var.cost_center
    contact     = var.contact_email
  })
}
```

Pass `local.all_tags` where this guide says `local.tags`. ONE set per project.

## Effective-tag check

Source-text greps miss unquoted HCL keys, match variable declarations, skip nested files. Check the evaluated plan: covers module + provider tag propagation. User produces the plan; the assistant's check is read-only. `tfplan` and `plan.json` contain sensitive values in cleartext: keep out of Git and chat. NEVER delete or move the user-supplied `tfplan`; delete only derived files the assistant created.

User-only command (the user runs it; NEVER run it without explicit user authorization to generate a plan):

```bash
terraform plan -out=tfplan
```

Read-only conversion and check, from a user-supplied `tfplan`. Create an assistant-owned private temp directory first; if that fails, nothing runs. Write the derived JSON only inside it and delete only that directory:

```bash
tmp="$(mktemp -d)" || { echo "mktemp failed; not converting plan" >&2; exit 1; }
if [ -z "$tmp" ] || ! chmod 700 "$tmp"; then
  [ -n "$tmp" ] && rm -rf "$tmp"
  echo "private temp directory setup failed; not converting plan" >&2
  exit 1
fi
status=0
terraform show -json tfplan > "$tmp/plan.json" || status=$?
if [ "$status" -eq 0 ]; then
  uv run "$(realpath skill://iac-terraform/scripts/check_tags.py)" "$tmp/plan.json" || status=$?
fi
rm -rf "$tmp"
exit "$status"
```

The block preserves the checker's exit status (0 compliant, 1 violations, 2 unreadable input) while still deleting its own temp directory; setup failure exits 1 before any plan JSON is written, and a failed conversion never becomes a successful block.

Run only the conversion/check block in the omp `bash` tool; `realpath` resolves `skill://` there; script needs no installed dependencies. Script walks `resource_changes`, reads `tags_all` (fallback `tags`), fails on missing/empty tags, wrong case, bad prefixes, mismatched `CE_Environment`. `aws_autoscaling_group` checked via `tag` blocks (key, value, `propagate_at_launch = true`). Tags or tag values unknown until apply → warnings (`--strict` fails them); invalid known values still fail. Exit codes: 0 compliant, 1 violations, 2 unreadable input.

In CI: copy the script to a named repository path such as `scripts/check_tags.py`; run `uv run ./scripts/check_tags.py plan.json` after the plan step. Workflow template → `cicd-engineering`.

## Common mistakes

| Bad | Good |
| --- | --- |
| `CE_Environment = var.environment` | `local.ce_environment_map[var.environment]` |
| `env = "development"`, `CE_Environment = "Dev"` | `env = "dev"`, `CE_Environment = "DEV"` |
| `cost_center = "12345"` | `cost_center = "apm-1234567"` |
| Module call with no `tags` | `tags = local.tags` |
| `ignore_tags` covering `cost_center` or `CE_*` | Leave mandatory keys managed by Terraform |

## Sources

- AWS provider index (`default_tags`, `ignore_tags`, `tag_policy_compliance`; ASG exception): <https://registry.terraform.io/providers/hashicorp/aws/latest/docs>
- AWS provider resource tagging guide: <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/guides/resource-tagging>
- AWS provider tag policy compliance guide: <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/guides/tag-policy-compliance>
- AWS provider v5 upgrade guide (default tags changes): <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/guides/version-5-upgrade>
- AWS provider changelog 6.22.0 (`tag_policy_compliance`): <https://github.com/hashicorp/terraform-provider-aws/blob/main/CHANGELOG.md>
- `terraform plan` and `terraform show` (cleartext sensitive values in plan files and JSON): <https://developer.hashicorp.com/terraform/cli/commands/plan>, <https://developer.hashicorp.com/terraform/cli/commands/show>
