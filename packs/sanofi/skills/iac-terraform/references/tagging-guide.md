# Sanofi AWS Tagging Guide

Per the accepted RFC in `Sanofi-Accelerator/Request-for-Comments`, every taggable AWS resource carries 10 mandatory tags. The live RFC and the library tags module are the authority; re-verify before deployment ([module-guide.md](module-guide.md#discovery)).

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
| `contact` | Team/tech-lead `@sanofi.com` email | `platform-team@sanofi.com` |
| `CE_Application_ID` | `APM` + 7 digits | `APM1234567` |
| `CE_Application_Name` | Free text, human-readable application name | `Order Portal` |
| `CE_Environment` | Uppercase `env` | `DEV` |

`CE_Application_ID` and `cost_center`:

- `cost_center = apm-1234567` → `CE_Application_ID = APM1234567` (same digits, uppercase prefix).
- `cost_center = cc-*` or `dp-*` → no APM ID is derivable. ASK the user. NEVER copy the cost center into `CE_Application_ID`.
- A company-wide cost-center → application mapping is [UNVERIFIED]. Use one only when the user or the RFC supplies it.

## Environment mapping

| `env` | `CE_Environment` | Use |
| --- | --- | --- |
| `dev` | `DEV` | Development/sandbox |
| `test` | `TEST` | QA/UAT, shared with business |
| `prod` | `PROD` | Production, change control |

## Standard implementation

Input names avoid Terraform's reserved variable names (`source`, `version`, `providers`, `count`, `for_each`, `lifecycle`, `depends_on`, `locals`), so the `version` tag comes from `app_version`.

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
    condition     = can(regex("@sanofi\\.com$", var.contact_email))
    error_message = "Contact must be a @sanofi.com email."
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

Operational tags (`ManagedBy = "Terraform"`, `Repository`) MAY be merged in: `merge(local.tags, { ManagedBy = "Terraform" })`. They never replace the 10.

## Provider default tags

Set the same map at the provider so raw resources and modules without a `tags` input are still covered:

```hcl
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.tags
  }
}
```

- Resource-level `tags` override `default_tags` for the same key (AWS provider 5+ allows duplicates and zero-value `""` tags). The effective set is the read-only `tags_all`; that is what `check_tags.py` reads. Still keep identical keys with identical values: a different value silently wins at the resource.
- `default_tags` is a backstop. Still pass `tags = local.tags` to each module.
- `default_tags` does NOT cover `aws_autoscaling_group`; give it `tag` blocks (with `propagate_at_launch`) built from `local.tags`.
- Resources with no `tags` argument (some `aws_*` sub-resources) are not taggable and not checked.
- `ignore_tags` (provider) or `lifecycle { ignore_changes = [tags] }` hides drift on those keys. NEVER apply either to the 10 mandatory tags. A key in both `ignore_tags` and a resource's `tags` shows a perpetual diff.
- A tag set only through `aws_ec2_tag` on a resource whose own `tags` argument is also managed produces a perpetual diff; use one or the other.
- Optional: AWS provider 6.22+ `tag_policy_compliance = "error"` fails plans that miss tags required by the account's AWS Organizations tag policy. The runner role needs the `tags:ListRequiredTags` permission; most SDKv2-based resources can only log a warning. It complements, and does not replace, the 10-tag check.

## tags_mandatory_tags module

The library helper builds the corporate tags. Verify its inputs in the module's `variables.tf`.

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

Pass `local.all_tags` where this guide says `local.tags`. Use ONE set per project.

## Effective-tag check

Source-text greps miss unquoted HCL keys, match variable declarations, and skip nested files. Check the evaluated plan instead. It covers module and provider tag propagation. The user produces the plan; the check is read-only. `tfplan` and `plan.json` contain sensitive values in cleartext: keep them out of Git and chat, and delete them after the check.

```bash
terraform plan -out=tfplan
terraform show -json tfplan > plan.json
uv run "$(realpath skill://iac-terraform/scripts/check_tags.py)" plan.json
```

Run these in the omp `bash` tool; `realpath` resolves `skill://` there, and the script needs no installed dependencies. The script walks `resource_changes`, reads `tags_all` (falling back to `tags`), and fails on missing/empty tags, wrong case, bad prefixes, and mismatched `CE_Environment`. `aws_autoscaling_group` is checked through its `tag` blocks (key, value, `propagate_at_launch = true`). Tags or individual tag values unknown until apply print as warnings (`--strict` fails them); invalid known values still fail. Exit codes: 0 compliant, 1 violations, 2 unreadable input.

In CI, copy the script into the repository and run `uv run check_tags.py plan.json` after the plan step; the workflow template is in the `cicd-engineering` skill.

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
