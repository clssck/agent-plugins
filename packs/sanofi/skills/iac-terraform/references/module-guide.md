# Terraform Module Guide

Discovery, module usage, validation, versions, state backend, testing, secrets, and module pinning for Sanofi AWS Terraform. Tag rules: [tagging-guide.md](tagging-guide.md).

## Contents

- [Discovery](#discovery)
- [Module call pattern](#module-call-pattern)
- [Validation](#validation)
- [Versions and providers](#versions-and-providers)
- [State backend](#state-backend)
- [Testing](#testing)
- [Secrets](#secrets)
- [Module catalog](#module-catalog)
- [Project layout](#project-layout)
- [Pinning](#pinning)
- [Sources](#sources)

## Discovery

Run first. Use the GitHub integration if available; otherwise `gh` (same syntax in bash, zsh, PowerShell). No access to a repository? Stop and report it; NEVER guess module inputs.

```bash
# Catalog and service modules
gh api repos/Sanofi-InnerSource/terraform-aws-library/contents/README.md -H "Accept: application/vnd.github.raw"
gh api repos/Sanofi-InnerSource/terraform-aws-library/contents/src/SERVICE --jq '.[].name'

# Module documentation and inputs
gh api repos/Sanofi-InnerSource/terraform-aws-library/contents/src/SERVICE/MODULE/README.md -H "Accept: application/vnd.github.raw"
gh api repos/Sanofi-InnerSource/terraform-aws-library/contents/src/SERVICE/MODULE/variables.tf -H "Accept: application/vnd.github.raw"

# Accepted RFCs: path is a search qualifier, not a flag
gh search code 'tagging path:accepted' --repo Sanofi-Accelerator/Request-for-Comments
```

Confluence CODE-space docs: use the `search-company-knowledge` skill. No integration at all? Use user-provided references.

## Module call pattern

```hcl
module "example" {
  source  = "sanofi.jfrog.io/terraform-innersource-local__aws-services/MODULE/aws"
  version = "X.Y.Z" # always pin; take the released version from the module repo

  tags = local.tags

  # Module-specific variables from its variables.tf
}
```

## Validation

Run in the Terraform root. Order matters: `validate` needs initialized providers and modules.

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

Private modules resolve from `sanofi.jfrog.io`, so `init` needs a token. Prefer the host-specific environment variable (Terraform 1.2+; periods become underscores) over a committed `.terraformrc`:

```bash
# bash / zsh
export TF_TOKEN_sanofi_jfrog_io="<token from the user's secret store>"
```

```powershell
# PowerShell
$env:TF_TOKEN_sanofi_jfrog_io = "<token from the user's secret store>"
```

- `init -backend=false` validates syntax and module wiring without touching state.
- `terraform plan`, with a real backend and AWS credentials, runs only on user authorization. NEVER run `apply`.
- Review plan output for the user; tag verification is in [tagging-guide.md](tagging-guide.md#effective-tag-check).
- Optional `uvx checkov -d .` is a static scan. Triage its findings through the `iac-security-review` skill.

CI plan/apply workflows and runner-side JFrog credentials: `cicd-engineering` skill.

## Versions and providers

Set floors to the features the code actually uses; NEVER copy a floor you do not need:

```hcl
# versions.tf
terraform {
  required_version = ">= 1.11" # 1.10: ephemeral resources/values; 1.11: write-only arguments, GA S3 lockfile

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0" # MUST also satisfy every library module's constraint
    }
  }
}
```

- Terraform selects ONE version per provider that all modules accept. Read each library module's `required_providers` (same `gh api` pattern as [Discovery](#discovery)) before picking the root constraint. NEVER raise a major version a module does not allow.
- Commit `.terraform.lock.hcl` and review its diff like code. Locked versions move only with `terraform init -upgrade`.
- AWS provider 5 → 6: move to the latest 5.x first; the user's plan MUST be clean with no deprecation warnings. Then set `~> 6.0` and run `terraform init -upgrade`.

AWS provider v6 changes that break or mislead existing code:

| v5 code | v6 |
| --- | --- |
| `data.aws_region.current.name` | `.region`; `name` is deprecated |
| `aws_s3_bucket.x.region` read as the bucket's location | `bucket_region`; `region` now selects where the provider manages the resource |
| Secrets in `aws_instance.user_data` | `user_data` is stored unhashed in clear text; NEVER put secrets there |
| `cpu_core_count`, `cpu_threads_per_core` on `aws_instance` | `cpu_options { core_count, threads_per_core }` |
| One aliased provider per Region | MAY use the per-resource `region` argument instead; aliases stay valid |

Changing a resource's `region` forces replacement. Moving deployed resources from provider aliases to `region` needs a user-run `terraform apply -refresh-only` first, so propose the change and let the user run it.

## State backend

```hcl
# backend.tf: bucket, key, and region come from the user; NEVER guess them
terraform {
  backend "s3" {
    bucket       = "<state bucket>"
    key          = "<service>/<env>/terraform.tfstate"
    region       = "<region>"
    encrypt      = true
    use_lockfile = true # S3-native locking: Terraform 1.10+, GA in 1.11
  }
}
```

- `dynamodb_table` locking is deprecated (Terraform 1.11) and slated for removal. NEVER add it to a new backend.
- Migrating an existing backend: set `use_lockfile = true` alongside `dynamodb_table`, which acquires both locks. Remove `dynamodb_table` once every local and CI runner is on 1.11+.
- The state role needs `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject` on `<key>.tflock`. The state object itself needs no `DeleteObject`.
- The state bucket SHOULD have versioning enabled so state can be recovered.
- Keep credentials out of the `backend` block and `-backend-config`. Those values are copied into `.terraform/` and plan files; use environment variables or an AWS profile.
- Changing an initialized backend needs `terraform init -migrate-state` (or `-reconfigure`) against real state. Only the user runs it.

## Testing

`terraform test` defaults every `run` block to `command = apply`, which creates real infrastructure and destroys it at the end of the file. NEVER run it unless every `run` block sets `command = plan` with the AWS provider mocked, or the user authorizes real resources.

```hcl
# tests/tags.tftest.hcl: assumes the root defines the variables and local.tags from tagging-guide.md
mock_provider "aws" {} # Terraform 1.7+; no AWS account or credentials needed

variables {
  team             = "platform"
  project_name     = "user-service"
  environment      = "dev"
  service          = "api"
  cost_center      = "apm-1234567"
  application_id   = "APM1234567"
  application_name = "Order Portal"
  contact_email    = "platform-team@sanofi.com"
}

run "tags_complete" {
  command = plan

  assert {
    condition     = local.tags["CE_Environment"] == "DEV"
    error_message = "CE_Environment must be the uppercase env."
  }
}

run "rejects_bad_cost_center" {
  command = plan

  variables {
    cost_center = "12345"
  }

  expect_failures = [var.cost_center]
}
```

- `expect_failures` only covers the operation named by `command`; with `command = apply`, a failing custom condition fails the whole run during plan.
- Mock providers invent values for computed attributes, so a mocked run proves logic, not effective tags. Effective tags still come from `check_tags.py` on a real plan.
- With `command = apply`, switching provider configuration between `run` blocks breaks resources the earlier provider created.
- Terraform 1.13+: external variables referenced in a test file SHOULD have a `variable` block in that file; complex types may error without it.

## Secrets

NEVER put a literal secret in `.tf`, `.tfvars`, or variable defaults. Pick by what the module or provider supports; check the module's `variables.tf` first.

| Need | Approach |
| --- | --- |
| RDS master password | `manage_master_user_password = true` (RDS keeps it in Secrets Manager; excludes `password`/`password_wo`). Use the module's equivalent input if it exposes one. |
| Value must be written to an argument | Write-only arguments (`password_wo` + `password_wo_version`, `secret_string_wo` + `secret_string_wo_version`) fed by an `ephemeral` resource such as `ephemeral "aws_secretsmanager_secret_version"`. Needs Terraform 1.11+ and a resource that supports the argument. |
| Secret container only | `secrets_manager_secret` module; set the value outside Terraform |

```hcl
# BAD: secret in code
resource "aws_db_instance" "db" {
  password = "my-secret-password"
}

# BAD: data source read lands the value in state and plan
data "aws_secretsmanager_secret_version" "db_password" {
  secret_id = module.db_secret.secret_id
}

# GOOD: RDS manages the master password
resource "aws_db_instance" "db" {
  manage_master_user_password = true
  # ...
}
```

```hcl
# GOOD: write-only password from an ephemeral read; neither value reaches state or plan
resource "aws_db_instance" "db" {
  password_wo         = ephemeral.aws_secretsmanager_secret_version.db_password.secret_string
  password_wo_version = 1 # bump to push a new password; Terraform cannot diff a write-only value
  # ...
}
```

- Write-only arguments also accept literals and non-ephemeral values. Nothing enforces ephemerality, so a literal there is still a literal in code.
- A changed write-only value alone triggers nothing: increment the paired `*_version` argument.
- A `data` source read of a secret stores the value in state; use the `ephemeral` block instead.
- A saved plan file and `terraform show -json` output hold sensitive values in cleartext. Treat `tfplan` and `plan.json` as secret artifacts: NEVER commit them or paste them into chat.

The `aws_db_instance` snippets illustrate the arguments. Prefer the `rds_instance` library module and check whether it exposes `manage_master_user_password` or a write-only input.

## Module catalog

Versions and inputs change; confirm in the repository. Services under `src/` in `Sanofi-InnerSource/terraform-aws-library`:

| Service | Modules |
| --- | --- |
| acm | acm_public_certificate |
| api_gateway | api_gateway_bootstrap, api_gateway_domain_name, api_gateway_rest_api |
| athena | athena_database, athena_workgroup |
| batch | batch_compute_environment, batch_job_definition |
| cloudwatch | cloudwatch_metric_alarm, cloudwatch_metric_filter |
| documentdb | documentdb_elastic_cluster, documentdb_instance_cluster |
| dynamodb | dynamodb_table |
| ecr | ecr_repository |
| ecs | ecs_cluster, ecs_default_execution_role, ecs_service, ecs_task_definition |
| elasticache | elasticache_memcached_cluster, elasticache_redis_cluster, elasticache_redis_replication_group |
| elb | elb_alb, elb_glb, elb_nlb, elb_target_group |
| event_bridge | event_bridge_bus, event_bridge_rule |
| iam | iam_role_custom_trust, iam_role_github, iam_role_service |
| kinesis | kinesis_datastream |
| kms | kms_symmetric_key |
| lambda | lambda_function |
| rds | rds_instance, rds_instance_snapshot |
| route53 | route53_private_alias, route53_private_cname |
| s3 | s3_bucket, s3_bucket_private_website, s3_bucket_public_website |
| secrets_manager | secrets_manager_secret |
| sns | sns_topic |
| sqs | sqs_queue |
| step_functions | step_functions_state_machine |
| tags | tags_accelerator_tags, tags_mandatory_tags |
| vpc | vpc_endpoint, vpc_selector |

## Project layout

```text
infrastructure/
├── main.tf            # Root module, provider config
├── variables.tf       # Inputs
├── locals.tf          # local.tags
├── outputs.tf
├── versions.tf        # Terraform and provider constraints
├── backend.tf         # State backend
├── modules/           # Local modules, if needed
├── envs/              # Per-environment .tfvars (dev/test/prod)
```

Keep secrets out of committed `*.tfvars`.

## Pinning

Registry modules take `version`. Local (`./modules/...`) and Git modules cannot use it; pin Git sources with `?ref=<tag-or-sha>`. A registry `module` block without `version` floats to the latest release.

## Sources

- Terraform S3 backend (`use_lockfile`, deprecated DynamoDB locking, `.tflock` permissions, versioning): <https://developer.hashicorp.com/terraform/language/backend/s3>
- Terraform 1.10 changelog (ephemeral resources/values, S3 native state locking added): <https://github.com/hashicorp/terraform/blob/v1.10/CHANGELOG.md>
- Terraform 1.11 changelog (write-only attributes, S3 lockfile GA, DynamoDB arguments deprecated): <https://github.com/hashicorp/terraform/blob/v1.11/CHANGELOG.md>
- Terraform 1.13 changelog (test-file variable definitions upgrade note): <https://github.com/hashicorp/terraform/blob/v1.13/CHANGELOG.md>
- Write-only arguments: <https://developer.hashicorp.com/terraform/language/manage-sensitive-data/write-only>
- Ephemeral values in resources: <https://developer.hashicorp.com/terraform/language/manage-sensitive-data/ephemeral>
- Manage sensitive data: <https://developer.hashicorp.com/terraform/language/manage-sensitive-data>
- `terraform plan` (plan files hold sensitive data in cleartext): <https://developer.hashicorp.com/terraform/cli/commands/plan>
- `terraform show` (`-json` exposes sensitive values): <https://developer.hashicorp.com/terraform/cli/commands/show>
- `terraform init` (`-migrate-state`, `-reconfigure`): <https://developer.hashicorp.com/terraform/cli/commands/init>
- Dependency lock file: <https://developer.hashicorp.com/terraform/language/files/dependency-lock>
- `terraform test` (default `command = apply`, `expect_failures`, provider switching): <https://developer.hashicorp.com/terraform/language/tests>
- Test mocking (`mock_provider`): <https://developer.hashicorp.com/terraform/language/tests/mocking>
- AWS provider v6 upgrade guide: <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/guides/version-6-upgrade>
- AWS provider enhanced Region support: <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/guides/enhanced-region-support>
- `aws_db_instance` (`password_wo`, `manage_master_user_password`): <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/db_instance>
- `aws_secretsmanager_secret_version` ephemeral resource and `secret_string_wo`: <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/ephemeral-resources/secretsmanager_secret_version>
