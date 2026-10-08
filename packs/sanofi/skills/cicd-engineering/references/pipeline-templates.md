# Pipeline Templates

Copy-paste GitHub Actions workflows for Sanofi repositories. Every template uses `runs-on: atmos-aws-arc-runner-set`, explicit least-privilege `permissions`, SHA-pinned actions, explicit reusable-workflow secrets, `run-name`, and `$GITHUB_STEP_SUMMARY`.

## Contents

- [Action pins](#action-pins)
- [Prerequisites](#prerequisites)
- [Node.js / TypeScript CI](#nodejs--typescript-ci)
- [Python CI](#python-ci)
- [SonarCloud analysis (reusable)](#sonarcloud-analysis-reusable)
- [Terraform plan + apply](#terraform-plan--apply)
- [Container build + push to ECR (reusable)](#container-build--push-to-ecr-reusable)
- [CD: auto-deploy + manual promotion to ECS](#cd-auto-deploy--manual-promotion-to-ecs)
- [CodeGuard / Checkmarx SAST](#codeguard--checkmarx-sast)

## Action pins

Verified 2026-10-08 against each action's latest GitHub release; annotated tags dereferenced to the commit. All JavaScript actions below declare `runs.using: node24` (Node 20 was removed from Actions runners on 2026-09-23: <https://github.blog/changelog/2026-09-23-node-20-is-no-longer-available-in-github-actions/>).

| Action | Version | Commit SHA |
| --- | --- | --- |
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-node` | v7.1.0 | `949feb2413d6458794dcd2491c4babbbce0c15c1` |
| `actions/setup-python` | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `actions/upload-artifact` | v7.0.2 | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |
| `actions/download-artifact` | v8.0.2 | `9000827ccba6bdab643e8b6fd33ac0654aef8333` |
| `actions/cache` | v6.1.0 | `55cc8345863c7cc4c66a329aec7e433d2d1c52a9` |
| `actions/github-script` | v9.0.0 | `3a2844b7e9c422d3c10d287c895573f7108da1b3` |
| `hashicorp/setup-terraform` | v4.0.1 | `dfe3c3f87815947d99a8997f908cb6525fc44e9e` |
| `aws-actions/configure-aws-credentials` | v6.3.0 | `e1253824e5c10ff9df46874f81ed3ec929e19cfd` |
| `aws-actions/amazon-ecr-login` | v2.1.7 | `03f1aad4c6c7ffd436567f42f9384779290529bd` |
| `aws-actions/amazon-ecs-render-task-definition` | v1.9.1 | `8d79160660ad39c402a16e5fc7cd2a32e8f7d6b7` |
| `aws-actions/amazon-ecs-deploy-task-definition` | v2.6.3 | `c465972ecbd160473f22e683363b422a5412a3de` |
| `docker/setup-buildx-action` | v4.4.1 | `f87e5991a6d7451dcb8d9637bfbc97413f497069` |
| `docker/build-push-action` | v7.4.0 | `c3c9e263c25d99ce0380d002d59b67737d91b0dc` |
| `SonarSource/sonarqube-scan-action` | v8.3.0 | `d209202bc7d53ff1cc128f7f907dac145c9d6ae9` |
| `ossf/scorecard-action` | v2.4.4 | `2d1146689b8cda280b9bc96326124645441f03bc` |
| `actions/attest` | v4.2.2 | `1e69f48acb82d1966a394da916b4c1698aa569d6` |

Re-verify before reuse; pins age. Resolve a tag to its commit (dereferences annotated tags; same command in bash, zsh, and PowerShell):

```bash
gh release view --repo OWNER/REPO --json tagName --jq .tagName
gh api repos/OWNER/REPO/commits/refs/tags/TAG --jq .sha
```

NEVER use `gh api repos/OWNER/REPO/git/ref/tags/TAG --jq .object.sha` alone: for annotated tags it returns the tag object SHA, not the commit.

## Prerequisites

- **Allowlist**: confirm each action/version is permitted by the Sanofi org allowlist. Allowlist pins a tag? Use that exact tag instead of the SHA.
- **ARC runner image**: runner release `2.329.0` or later, the minimum GitHub requires to register a runner (Node 24 needs v2.328.0 or later), and each new release within 30 days. Container jobs need Docker/BuildKit. Sonar scan action v8 needs `unzip`, `curl` or `wget`, `gpg`, `dirmngr` on `PATH`. Confirm with the platform team; NEVER assume fleet versions. Runner enforcement: [security-hardening.md §5](security-hardening.md#5-self-hosted-runner-risks).
- **Environments** `dev`, `test`, `prod`: each holds `AWS_ACCOUNT_ID` and `JFROG_TOKEN` (Terraform repos). `prod` has required reviewers and a `main`-only deployment branch rule.
- **Repository/org secrets**: `SONAR_TOKEN`; CodeGuard `CHECKMARX_*` secrets.
- **Branch protection**: require the `Build Complete` check. It fails unless every quality, audit, and Sonar job succeeded.

---

## Node.js / TypeScript CI

`.github/workflows/ci.yaml`. The workflow name `CI` and the file name `ci.yaml` are load-bearing: the CD template triggers on the name and validates promoted runs against the file.

```yaml
name: "CI"
run-name: ${{ github.workflow }} - ${{ github.ref_name }}

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

permissions:
  contents: read

jobs:
  format:
    name: Format Check
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: ".nvmrc"
          cache: "npm"
      - run: npm ci
      - run: npx prettier --check .

  lint:
    name: Lint
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: ".nvmrc"
          cache: "npm"
      - run: npm ci
      - run: npx eslint . --max-warnings=0

  typecheck:
    name: Type Check
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: ".nvmrc"
          cache: "npm"
      - run: npm ci
      - run: npx tsc --noEmit

  test:
    name: Unit Tests
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: ".nvmrc"
          cache: "npm"
      - run: npm ci
      - name: Run tests with coverage (LCOV for Sonar)
        run: npx vitest run --coverage --coverage.reporter=lcov --coverage.reporter=text --coverage.thresholds.statements=80
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        if: always()
        with:
          name: coverage_result
          path: coverage/lcov.info
          retention-days: 7

  audit:
    name: Dependency Audit
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: ".nvmrc"
          cache: "npm"
      - run: npm ci
      - run: npm audit --audit-level=high

  sonarcloud:
    name: SonarCloud
    needs: [test]
    permissions:
      contents: read
    uses: ./.github/workflows/sonarcloud.yaml
    secrets:
      SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}

  build:
    name: Build Complete
    runs-on: atmos-aws-arc-runner-set
    if: always()
    needs: [format, lint, typecheck, test, audit, sonarcloud]
    steps:
      - name: CI Summary
        env:
          FORMAT: ${{ needs.format.result }}
          LINT: ${{ needs.lint.result }}
          TYPECHECK: ${{ needs.typecheck.result }}
          TEST: ${{ needs.test.result }}
          AUDIT: ${{ needs.audit.result }}
          SONAR: ${{ needs.sonarcloud.result }}
          REF_NAME: ${{ github.ref_name }}
          SHA: ${{ github.sha }}
        run: |
          {
            echo "## CI Results"
            echo ""
            echo "| Check | Status |"
            echo "|-------|--------|"
            echo "| Format | $FORMAT |"
            echo "| Lint | $LINT |"
            echo "| TypeScript | $TYPECHECK |"
            echo "| Tests | $TEST |"
            echo "| Audit | $AUDIT |"
            echo "| SonarCloud quality gate | $SONAR |"
            echo ""
            echo "**Branch:** \`$REF_NAME\`"
            echo "**Commit:** \`$SHA\`"
          } >> "$GITHUB_STEP_SUMMARY"
      - name: Fail unless every required job succeeded
        if: contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled') || contains(needs.*.result, 'skipped')
        run: exit 1
```

Containerized service? Add the [container build caller](#container-build--push-to-ecr-reusable) to this workflow.

---

## Python CI

```yaml
name: "CI"
run-name: ${{ github.workflow }} - ${{ github.ref_name }}

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

permissions:
  contents: read

jobs:
  format:
    name: Format Check
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version-file: ".python-version"
          cache: "pip"
      - run: pip install -r requirements-dev.txt
      - run: black --check .
      - run: isort --check-only .

  lint:
    name: Lint
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version-file: ".python-version"
          cache: "pip"
      - run: pip install -r requirements-dev.txt
      - run: ruff check .

  typecheck:
    name: Type Check
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version-file: ".python-version"
          cache: "pip"
      - run: pip install -r requirements-dev.txt
      - run: mypy src/

  test:
    name: Unit Tests
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version-file: ".python-version"
          cache: "pip"
      - run: pip install -r requirements-dev.txt
      - name: Run tests with coverage (Cobertura XML for Sonar)
        run: pytest --cov=src --cov-report=xml:coverage.xml --cov-fail-under=80
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        if: always()
        with:
          name: coverage_result
          path: coverage.xml
          retention-days: 7

  audit:
    name: Dependency Audit
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version-file: ".python-version"
          cache: "pip"
      - run: pip install pip-audit
      - run: pip-audit --strict -r requirements.txt

  sonarcloud:
    name: SonarCloud
    needs: [test]
    permissions:
      contents: read
    uses: ./.github/workflows/sonarcloud.yaml
    secrets:
      SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}

  build:
    name: Build Complete
    runs-on: atmos-aws-arc-runner-set
    if: always()
    needs: [format, lint, typecheck, test, audit, sonarcloud]
    steps:
      - name: CI Summary
        env:
          FORMAT: ${{ needs.format.result }}
          LINT: ${{ needs.lint.result }}
          TYPECHECK: ${{ needs.typecheck.result }}
          TEST: ${{ needs.test.result }}
          AUDIT: ${{ needs.audit.result }}
          SONAR: ${{ needs.sonarcloud.result }}
        run: |
          {
            echo "## CI Results"
            echo ""
            echo "| Check | Status |"
            echo "|-------|--------|"
            echo "| Format | $FORMAT |"
            echo "| Lint | $LINT |"
            echo "| Type Check | $TYPECHECK |"
            echo "| Tests | $TEST |"
            echo "| Audit | $AUDIT |"
            echo "| SonarCloud quality gate | $SONAR |"
          } >> "$GITHUB_STEP_SUMMARY"
      - name: Fail unless every required job succeeded
        if: contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled') || contains(needs.*.result, 'skipped')
        run: exit 1
```

---

## SonarCloud analysis (reusable)

`.github/workflows/sonarcloud.yaml`, called by both CI templates on pull requests and pushes. The scanner auto-detects PR vs branch context in GitHub Actions, so one workflow serves PR analysis and the main-branch baseline. `sonar.qualitygate.wait=true` makes the step fail on a failed quality gate, which fails `Build Complete`.

```yaml
name: "SonarCloud"

on:
  workflow_call:
    secrets:
      SONAR_TOKEN:
        required: true

permissions:
  contents: read

jobs:
  analysis:
    name: SonarCloud Analysis
    runs-on: atmos-aws-arc-runner-set
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          name: coverage_result
          path: coverage/
      - uses: SonarSource/sonarqube-scan-action@d209202bc7d53ff1cc128f7f907dac145c9d6ae9 # v8.3.0
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
        with:
          args: >
            -Dsonar.qualitygate.wait=true
            -Dsonar.qualitygate.timeout=300
```

Repo prerequisite: `sonar-project.properties` at the root. Coverage imports only through these properties; an uploaded artifact alone is ignored.

```properties
sonar.organization=<SonarCloud organization key>
sonar.projectKey=<SonarCloud project key>
sonar.sources=src
# Node.js / TypeScript (Vitest lcov reporter)
sonar.javascript.lcov.reportPaths=coverage/lcov.info
# Python (pytest-cov XML)
# sonar.python.coverage.reportPaths=coverage/coverage.xml
```

Sources: <https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/ci-based-analysis/github-actions-for-sonarcloud> (quality gate wait, self-hosted prerequisites), <https://github.com/SonarSource/sonarqube-scan-action> (properties file).

---

## Terraform plan + apply

`JFROG_TOKEN` is an Environment secret (see [cicd-rules.md §6.5](cicd-rules.md#65-jfrog-artifactory-for-terraform-modules)), so every job that runs `terraform init` binds an environment. `setup-terraform` writes the JFrog credential into a runtime-only CLI config file.

```yaml
name: "Infrastructure"
run-name: ${{ github.workflow }} - ${{ inputs.env || 'dev' }} - ${{ inputs.action || 'plan' }}

on:
  pull_request:
    paths: ["infrastructure/terraform/**"]
  workflow_dispatch:
    inputs:
      env:
        description: "Target environment"
        required: true
        type: choice
        options: [dev, test, prod]
        default: "dev"
      action:
        description: "Terraform action"
        required: true
        type: choice
        options: [plan, apply]
        default: "plan"

permissions:
  contents: read

concurrency:
  group: terraform-${{ inputs.env || 'dev' }}
  cancel-in-progress: false

jobs:
  validate:
    name: Validate
    runs-on: atmos-aws-arc-runner-set
    environment: ${{ inputs.env || 'dev' }}
    defaults:
      run:
        working-directory: infrastructure/terraform
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e # v4.0.1
        with:
          cli_config_credentials_hostname: "sanofi.jfrog.io"
          cli_config_credentials_token: ${{ secrets.JFROG_TOKEN }}
      - run: terraform fmt -check -recursive
      - run: terraform init -backend=false
      - run: terraform validate

  plan:
    name: Plan (${{ inputs.env || 'dev' }})
    needs: validate
    runs-on: atmos-aws-arc-runner-set
    environment: ${{ inputs.env || 'dev' }}
    permissions:
      contents: read
      id-token: write
    defaults:
      run:
        working-directory: infrastructure/terraform
    env:
      TF_ENV: ${{ inputs.env || 'dev' }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e # v4.0.1
        with:
          cli_config_credentials_hostname: "sanofi.jfrog.io"
          cli_config_credentials_token: ${{ secrets.JFROG_TOKEN }}
          terraform_wrapper: false
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@e1253824e5c10ff9df46874f81ed3ec929e19cfd # v6.3.0
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/App_githubrunners_accelerator_${{ inputs.env || 'dev' }}
          aws-region: eu-west-1
      - run: terraform init
      - name: Terraform Plan
        id: plan
        run: |
          set +e
          terraform plan -var-file="envs/${TF_ENV}.tfvars" -out=tfplan -detailed-exitcode
          exit_code=$?
          echo "exitcode=${exit_code}" >> "$GITHUB_OUTPUT"
          if [ "$exit_code" -eq 1 ]; then exit 1; fi
          exit 0
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: tfplan-${{ inputs.env || 'dev' }}
          path: infrastructure/terraform/tfplan
          retention-days: 7
      - name: Plan Summary
        env:
          EXIT_CODE: ${{ steps.plan.outputs.exitcode }}
        run: |
          {
            echo "## Terraform Plan - ${TF_ENV}"
            echo ""
            echo "**Exit code:** ${EXIT_CODE} (0 = no changes, 2 = changes)"
          } >> "$GITHUB_STEP_SUMMARY"

  apply:
    name: Apply (${{ inputs.env }})
    needs: plan
    if: github.event_name == 'workflow_dispatch' && inputs.action == 'apply' && github.ref == 'refs/heads/main'
    runs-on: atmos-aws-arc-runner-set
    environment: ${{ inputs.env }}
    permissions:
      contents: read
      id-token: write
    defaults:
      run:
        working-directory: infrastructure/terraform
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e # v4.0.1
        with:
          cli_config_credentials_hostname: "sanofi.jfrog.io"
          cli_config_credentials_token: ${{ secrets.JFROG_TOKEN }}
          terraform_wrapper: false
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@e1253824e5c10ff9df46874f81ed3ec929e19cfd # v6.3.0
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/App_githubrunners_accelerator_${{ inputs.env }}
          aws-region: eu-west-1
      - run: terraform init
      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          name: tfplan-${{ inputs.env }}
          path: infrastructure/terraform/
      - name: Terraform Apply
        run: terraform apply tfplan
```

- Plan files can contain sensitive values; keep `retention-days` short and repository access restricted.
- `apply` uses the plan produced in the same run; `prod` approval happens at the environment gate.

---

## Container build + push to ECR (reusable)

Builds once per commit on `main`, pushes `sha-<commit>`, and records the immutable digest reference as the `image-ref` artifact. CD deploys that digest unchanged to dev, test, and prod.

- Pass the reference by artifact, not job output: `AWS_ACCOUNT_ID` is a secret, so GitHub redacts job outputs containing the registry hostname.
- One ECR repository in the publishing account; its repository policy MUST grant pull to the dev/test/prod task execution roles. Per-account registries? Copy the same digest (`docker buildx imagetools create`); NEVER rebuild.

`.github/workflows/container-build.yaml`:

```yaml
name: "Container Build"

on:
  workflow_call:
    inputs:
      environment:
        description: "GitHub Environment holding the ECR publishing role"
        required: true
        type: string
      ecr-repository:
        description: "ECR repository name"
        required: true
        type: string
    secrets:
      AWS_ACCOUNT_ID:
        required: true

permissions:
  contents: read
  id-token: write

jobs:
  build:
    name: Build & Push
    runs-on: atmos-aws-arc-runner-set
    environment: ${{ inputs.environment }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@e1253824e5c10ff9df46874f81ed3ec929e19cfd # v6.3.0
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/App_githubrunners_accelerator_${{ inputs.environment }}
          aws-region: eu-west-1
      - name: Login to ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@03f1aad4c6c7ffd436567f42f9384779290529bd # v2.1.7
      - uses: docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069 # v4.4.1
      - name: Build and push
        id: build
        uses: docker/build-push-action@c3c9e263c25d99ce0380d002d59b67737d91b0dc # v7.4.0
        with:
          context: .
          push: true
          platforms: linux/amd64
          tags: ${{ steps.login-ecr.outputs.registry }}/${{ inputs.ecr-repository }}:sha-${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - name: Record immutable image reference
        env:
          IMAGE: ${{ steps.login-ecr.outputs.registry }}/${{ inputs.ecr-repository }}@${{ steps.build.outputs.digest }}
        run: |
          printf '%s\n' "$IMAGE" > image-ref.txt
          {
            echo "## Container Build"
            echo ""
            echo "**Commit:** \`${GITHUB_SHA}\`"
            echo "**Digest:** \`${IMAGE#*@}\`"
          } >> "$GITHUB_STEP_SUMMARY"
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: image-ref
          path: image-ref.txt
          retention-days: 90
```

Caller job, added to the `CI` workflow (runs after the `Build Complete` gate, `main` pushes only):

```yaml
jobs:
  container:
    name: Container Image
    needs: [build]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    permissions:
      contents: read
      id-token: write
    uses: ./.github/workflows/container-build.yaml
    with:
      environment: dev
      ecr-repository: my-service
    secrets:
      AWS_ACCOUNT_ID: ${{ secrets.AWS_ACCOUNT_ID }}
```

`AWS_ACCOUNT_ID` exists only in the `dev` environment; the callee job sets `environment`, and passing the secret by name resolves the environment value (<https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows>).

Production-bound image? Add a provenance attestation step after `Build and push`: [security-hardening.md §11](security-hardening.md#11-artifact-attestations-and-provenance). It needs `attestations: write` in this job and the caller, and `actions/attest` on the allowlist.

---

## CD: auto-deploy + manual promotion to ECS

- `workflow_run` deploys the image built by the successful CI run that triggered it (`github.event.workflow_run.id`), never the branch tip.
- `workflow_dispatch` promotes the image from a named CI run ID; the run MUST be a successful `CI` push run on `main`.
- Each deploy renders a new task-definition revision with the image digest, deploys it, and waits for service stability. `update-service --force-new-deployment` alone keeps the old task definition's image (<https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_UpdateService.html>).
- Deploy role needs `ecs:DescribeTaskDefinition`, `ecs:RegisterTaskDefinition`, `ecs:UpdateService`, `ecs:DescribeServices`, and `iam:PassRole` on the task/execution roles.

```yaml
name: "CD"
run-name: ${{ github.workflow }} - ${{ inputs.environment || 'dev' }}

on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        description: "Environment to deploy"
        required: true
        type: choice
        options: [dev, test, prod]
        default: "dev"
      ci-run-id:
        description: "ID of the successful CI run on main whose image to deploy"
        required: true
        type: string

permissions:
  contents: read

concurrency:
  group: cd-${{ inputs.environment || 'dev' }}
  cancel-in-progress: false

jobs:
  select:
    name: Select image
    if: >-
      github.event_name == 'workflow_dispatch' ||
      (github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.event == 'push')
    runs-on: atmos-aws-arc-runner-set
    permissions:
      actions: read
    outputs:
      environment: ${{ steps.target.outputs.environment }}
      run-id: ${{ steps.target.outputs.run-id }}
    steps:
      - name: Resolve target environment and CI run
        id: target
        uses: actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3 # v9.0.0
        env:
          TARGET_ENV: ${{ inputs.environment }}
          CI_RUN_ID: ${{ inputs.ci-run-id }}
        with:
          script: |
            let environment = 'dev';
            let runId = context.payload.workflow_run?.id;
            if (context.eventName === 'workflow_dispatch') {
              environment = process.env.TARGET_ENV;
              if (!/^\d+$/.test(process.env.CI_RUN_ID)) {
                core.setFailed('ci-run-id must be a numeric workflow run ID');
                return;
              }
              runId = Number(process.env.CI_RUN_ID);
              const { data: run } = await github.rest.actions.getWorkflowRun({ ...context.repo, run_id: runId });
              const { data: ci } = await github.rest.actions.getWorkflow({ ...context.repo, workflow_id: 'ci.yaml' });
              if (run.workflow_id !== ci.id || run.head_branch !== 'main' || run.event !== 'push' || run.conclusion !== 'success') {
                core.setFailed(`Run ${runId} is not a successful CI push run on main`);
                return;
              }
            }
            core.setOutput('environment', environment);
            core.setOutput('run-id', String(runId));

  deploy:
    name: Deploy (${{ needs.select.outputs.environment }})
    needs: select
    runs-on: atmos-aws-arc-runner-set
    environment: ${{ needs.select.outputs.environment }}
    permissions:
      actions: read
      id-token: write
    env:
      TARGET_ENV: ${{ needs.select.outputs.environment }}
    steps:
      - name: Download image reference from the CI run
        uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          name: image-ref
          run-id: ${{ needs.select.outputs.run-id }}
          github-token: ${{ github.token }}
      - name: Read image digest reference
        id: image
        run: |
          image="$(head -n 1 image-ref.txt)"
          case "$image" in
            *@sha256:*) ;;
            *) echo "image-ref.txt does not contain a digest reference" >&2; exit 1 ;;
          esac
          echo "image=${image}" >> "$GITHUB_OUTPUT"
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@e1253824e5c10ff9df46874f81ed3ec929e19cfd # v6.3.0
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/App_githubrunners_accelerator_${{ needs.select.outputs.environment }}
          aws-region: eu-west-1
      - name: Render task definition with the selected image
        id: render
        uses: aws-actions/amazon-ecs-render-task-definition@8d79160660ad39c402a16e5fc7cd2a32e8f7d6b7 # v1.9.1
        with:
          task-definition-family: my-service-${{ needs.select.outputs.environment }}
          container-name: my-service
          image: ${{ steps.image.outputs.image }}
      - name: Register, deploy, and wait for stability
        uses: aws-actions/amazon-ecs-deploy-task-definition@c465972ecbd160473f22e683363b422a5412a3de # v2.6.3
        with:
          task-definition: ${{ steps.render.outputs.task-definition }}
          cluster: my-service-${{ needs.select.outputs.environment }}
          service: my-service
          wait-for-service-stability: true
      - name: Deploy Summary
        env:
          IMAGE: ${{ steps.image.outputs.image }}
          CI_RUN: ${{ needs.select.outputs.run-id }}
        run: |
          {
            echo "## Deployed to ${TARGET_ENV}"
            echo ""
            echo "**Digest:** \`${IMAGE#*@}\`"
            echo "**Source CI run:** ${CI_RUN}"
          } >> "$GITHUB_STEP_SUMMARY"
```

- Promotion path: dev (automatic) → test → prod, each a `workflow_dispatch` with the same `ci-run-id`.
- `prod` approval comes from environment protection rules; dispatch from `main` to satisfy the deployment branch rule.
- `image-ref` retention (90 days) bounds the promotion window; raise it in repository settings if releases wait longer.

---

## CodeGuard / Checkmarx SAST

Org-managed reusable workflow; `@main` is the documented exception ([cicd-rules.md §1.1](cicd-rules.md#11-reference-actions-in-a-form-the-sanofi-allowlist-accepts)). Secrets are passed explicitly.

```yaml
name: "SAST"
run-name: ${{ github.workflow }} - CodeGuard

on:
  push:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1" # Weekly Monday 06:00 UTC
  workflow_call:

permissions:
  contents: read
  security-events: write

jobs:
  codeguard:
    name: CodeGuard SAST
    # @main exception: org-managed reusable workflow
    uses: Sanofi-Shared-GitHub-Apps/cyber-AST-Action_reusable/.github/workflows/code_guard_ast.yml@main
    with:
      production-branch: main
      groups: Digital-Accelerator
      cmdb: ${{ vars.cmdb }}
      summary-output: true
      codeguard-gate: true
    secrets:
      DOCKER_AUTH_CONFIG: ${{ secrets.CHECKMARX_DOCKER_AUTH_CONFIG }}
      CX_CLIENT_ID: ${{ secrets.CHECKMARX_CX_CLIENT_ID }}
      CX_CLIENT_SECRET: ${{ secrets.CHECKMARX_CX_CLIENT_SECRET }}
```
