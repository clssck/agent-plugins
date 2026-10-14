# Scanner Cross-Check

Optional Checkov, Trivy, or KICS pass after the manual review. Scanner hits are leads, not findings: re-grade each with the evidence status and severity rules in [security-controls.md](skill://iac-security-review/references/security-controls.md) before it enters the report.

## Preconditions

- **Install gate:** MAY run a scanner only if already installed or the user approves fetching it. Check with `bash`: `command -v checkov trivy kics uvx` (POSIX) · `Get-Command checkov,trivy,kics,uvx` (PowerShell).
- **NEVER install or download a scanner without asking.** Checkov needs no install step: with approval, `uvx checkov ...` (ephemeral environment) or `uv tool install checkov` (persistent). Third-party packages are a supply-chain surface: Wiz reports trojanized PyPI releases of `litellm` (1.82.7, 1.82.8) in a follow-on operation.
- **Output location:** temp directory or `audits/`, NEVER next to the IaC files.
- **Untrusted repo:** `trivy config` downloads remote Terraform modules and the CLI cannot turn that off — each download is a request to a host the repo author chose. Prefer Checkov: it downloads external modules only when `--download-external-modules true` (or `DOWNLOAD_EXTERNAL_MODULES`) is set.

### 2026 scanner compromises

| Tool | Compromise |
|------|------------|
| Trivy | Malicious binary v0.69.4 (2026-03-19); malicious Docker Hub images 0.69.5, 0.69.6 (2026-03-22); 76 of 77 `aquasecurity/trivy-action` tags and all 7 `setup-trivy` tags force-pushed |
| KICS | 35 `Checkmarx/kics-github-action` tags hijacked (2026-03-23); malicious `checkmarx/kics` Docker Hub images (2026-04-22; tags `latest`, `alpine`, `debian`, `v2.1.20`, `v2.1.20-debian`, `v2.1.21`, `v2.1.21-debian`) exfiltrated scan output |

**STOP and tell the user** when: `trivy --version` reports 0.69.4 · a local Trivy image is 0.69.5 or 0.69.6 · a local `checkmarx/kics` image was pulled on 2026-04-22. The host may have leaked credentials. Docker restored `checkmarx/kics` to the legitimate 2026-03-03 image: pin by digest, not tag.

## Commands

Flags identical in POSIX shells and PowerShell; only Docker volume syntax differs. Drop the `uvx` prefix when Checkov is installed with `uv tool install`.

| Tool | Directory scan | Notes |
|------|----------------|-------|
| Checkov | `uvx checkov -d <dir> --framework terraform cloudformation -o json --quiet --output-file-path <outdir>` | Writes `<outdir>/results_json.json`. `--var-file <f>.tfvars` resolves variables. User-supplied plan JSON: `uvx checkov -f tfplan.json --repo-root-for-plan-enrichment <dir>` |
| Trivy | `trivy config -f json -o <out>.json <dir>` | Successor to tfsec (Aqua consolidated tfsec scanning into Trivy). `--tf-vars <f>.tfvars`; `--tf-exclude-downloaded-modules` marks findings inside remote modules as ignored |
| KICS | `kics scan -p <dir> -o <outdir> --report-formats json --cloud-provider aws` | Docker, POSIX: `docker run -t -v "$PWD:/path" checkmarx/kics@sha256:DIGEST scan -p /path -o /path/audits`. PowerShell: `docker run -t -v "${PWD}:/path" checkmarx/kics@sha256:DIGEST scan -p /path -o /path/audits` |

**CDK and SST:** scanners read synthesized CloudFormation, not TypeScript. Scan `cdk.out/*.template.json` only if already committed or user-supplied. **NEVER run `cdk synth` or SST commands** — they execute app code and may call AWS.

## Triage

- **Absent-property hits:** Trivy documents that a resource lacking a property is treated as using the service default, and the check may fail. Re-check every such hit against [aws-defaults.md](skill://iac-security-review/references/aws-defaults.md). Common false positives: S3 encryption, S3 Block Public Access on new buckets, SQS SSE, Lambda outside a VPC.
- **Mapping:** each kept hit → control ID (PE/AA/EN/NS/EP/LM/SM); merge with the matching manual finding; cite file:line from the source, not the scanner.
- **Severity:** scanner severity ≠ report severity. Apply exposure × operations × authorization × impact.
- **Record:** scanner, version, command → report appendix "Complementary scans".

## Inline Suppressions

`grep` for suppressions during analysis, scanner or not. Each hides a check from CI.

| Tool | Syntax |
|------|--------|
| Checkov | `#checkov:skip=CKV_AWS_20:reason` inside the resource block |
| Trivy | `# trivy:ignore:<ID>` comment; `.trivyignore` / `.trivyignore.yaml` files |
| KICS | `# kics-scan ignore` (first line, whole file), `# kics-scan ignore-line`, `# kics-scan disable=<query-id>` |

- **Judge the suppressed control yourself.** Issue real → report under its control ID; quote the suppression comment as evidence.
- **MUST report** a suppression on a High/Critical-class control that has no reason, or whose reason the code contradicts.

## CI Usage (Out of Scope)

Workflows referencing `aquasecurity/trivy-action`, `aquasecurity/setup-trivy`, `Checkmarx/kics-github-action`, or `Checkmarx/ast-github-action` by tag instead of full commit SHA, or a `checkmarx/kics` image by tag → CI/CD supply-chain risk. Tell the user; point to cicd-engineering; do not grade here.

## Sources

- Trivy, Scanning Terraform files (tfsec consolidation, `trivy config`, absent-property behavior): https://github.com/aquasecurity/trivy/blob/main/docs/tutorials/misconfiguration/terraform.md
- Trivy, Terraform coverage (remote module downloads, `--tf-vars`, `--tf-exclude-downloaded-modules`, inline ignore): https://github.com/aquasecurity/trivy/blob/main/docs/guide/coverage/iac/terraform.md
- Trivy, Filtering (`.trivyignore`, `.trivyignore.yaml`): https://github.com/aquasecurity/trivy/blob/main/docs/guide/configuration/filtering.md
- Aqua Security, Trivy supply chain attack advisory (affected versions, tag poisoning, Docker Hub 0.69.5/0.69.6): https://www.aquasec.com/blog/trivy-supply-chain-attack-what-you-need-to-know/
- GitHub advisory GHSA-69fq-xp46-6x23 (CVE-2026-33634): https://github.com/advisories/GHSA-69fq-xp46-6x23
- Wiz, KICS GitHub Action compromised (35 tags; `litellm` PyPI update): https://www.wiz.io/blog/teampcp-attack-kics-github-action
- Docker, malicious `checkmarx/kics` images on Docker Hub (2026-04-22, tags, restore to 2026-03-03 image): https://www.docker.com/blog/trivy-kics-and-the-shape-of-supply-chain-attacks-so-far-in-2026/
- Checkov, CLI command reference: https://github.com/bridgecrewio/checkov/blob/main/docs/2.Basics/CLI%20Command%20Reference.md
- Checkov, argument parser (`--download-external-modules` default unset): https://github.com/bridgecrewio/checkov/blob/main/checkov/common/util/ext_argument_parser.py
- Checkov, Terraform plan scanning: https://github.com/bridgecrewio/checkov/blob/main/docs/7.Scan%20Examples/Terraform%20Plan%20Scanning.md
- Checkov, Suppressing and skipping policies: https://github.com/bridgecrewio/checkov/blob/main/docs/2.Basics/Suppressing%20and%20Skipping%20Policies.md
- KICS, Commands: https://github.com/Checkmarx/kics/blob/master/docs/commands.md
- KICS, Running KICS (Docker, `kics-scan` comments): https://github.com/Checkmarx/kics/blob/master/docs/running-kics.md
