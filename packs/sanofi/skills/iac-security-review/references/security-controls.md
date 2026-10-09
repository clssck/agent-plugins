# Security Controls

AWS IaC control matrix. Frameworks: Terraform (TF), CDK, SST, CloudFormation (CFN), Pulumi (use the TF resource names with Pulumi's property casing). Defaults and sources: [aws-defaults.md](aws-defaults.md).

## Evidence Status

Every finding carries one status.

| Status | Meaning | Use when |
|--------|---------|----------|
| Confirmed | Explicit insecure setting in scope | `AuthType: NONE`, `cidr 0.0.0.0/0` on port 22, `Action: "*"` |
| Needs confirmation | Setting absent or controlled outside the scanned files | Missing WAF, trail, account-level BPA, shared module internals |
| Not evidenced | Control cannot be judged from this scope | Central logging, runtime behavior, application authz |

NEVER report an absent property as Confirmed when an AWS default, account/org control, or shared module supplies it. Absent + default-safe → no finding, or Informational.

## Severity

Severity = exposure × reachable operations × authorization × data/privilege impact. Prove each factor from the code.

| Level | Requires |
|-------|----------|
| Critical | Confirmed unauthenticated or world-reachable path to sensitive data or privileged action |
| High | Confirmed weakness with a plausible path; impact limited by one remaining control |
| Medium | Defense-in-depth gap, or High-class gap with Needs confirmation status |
| Low | Hardening or policy gap |
| Informational | Observation; unverified area; legacy style |

- Public by design (marketing site, public docs API)? Not a finding by itself. Record intent, then check authorization, data, write operations, and cost abuse.
- Application behavior behind the endpoint is outside static scope: mark unknown, NEVER invent an attack chain.

## 1. Public Exposure

### PE-01: API Gateway route without authorization

| Framework | Check |
|-----------|-------|
| TF | `aws_apigatewayv2_route` `authorization_type = "NONE"` or absent; `aws_api_gateway_method` `authorization = "NONE"` |
| CDK | Route/method without `authorizer` and not under a default authorizer |
| SST | `api.route(...)` without per-route `auth` (and no `transform` authorizer) |
| CFN | `AWS::ApiGatewayV2::Route` / `AWS::ApiGateway::Method` with `AuthorizationType: NONE` |

Severity: High–Critical only when the route reaches sensitive data or mutates state. Check authorization at every layer (WAF, authorizer, backend) before rating.

### PE-02: Lambda function URL

| Framework | Check |
|-----------|-------|
| TF | `aws_lambda_function_url` `authorization_type = "NONE"`; `aws_lambda_permission` with `function_url_auth_type` (`lambda:InvokeFunctionUrl`) or `invoked_via_function_url` (`lambda:InvokeFunction`) |
| CDK | `FunctionUrl` `authType: NONE` |
| SST | Function `url` with `authorization: "none"` |
| CFN | `AWS::Lambda::Url` `AuthType: NONE` |

- Read effective permission statements: `Principal`, `Effect`, `Action`, conditions `lambda:FunctionUrlAuthType`, `lambda:InvokedViaFunctionUrl`.
- New function URLs need BOTH `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction` (since October 2025). A statement lacking either is not public access. A `NONE`-auth URL without the `lambda:InvokedViaFunctionUrl` condition on the `InvokeFunction` statement also lets any caller invoke the function directly: Low–Medium hardening.
- NEVER match on a Sid such as `FunctionURLAllowPublicAccess`.
- `AuthType: AWS_IAM` → not public.

### PE-03: Public S3 bucket

Public access = public ACL or policy grant AND no effective Block Public Access (bucket, account, or organization).

| Framework | Check |
|-----------|-------|
| TF | `aws_s3_bucket_public_access_block` with any of `block_public_acls`, `ignore_public_acls`, `block_public_policy`, `restrict_public_buckets` = `false`; `aws_s3_bucket_acl` `public-read*`; bucket policy `Principal: "*"` without fixed-value conditions |
| CDK | `publicReadAccess: true`; `blockPublicAccess` set to a permissive `BlockPublicAccess` |
| SST | `sst.aws.Bucket` `access: "public"` |
| CFN | `PublicAccessBlockConfiguration` with `false` values; `AccessControl: PublicRead`; public bucket policy |

- ACLs: new buckets default to Object Ownership `BucketOwnerEnforced`, which disables ACLs. A `public-read` ACL is exploitable only when `aws_s3_bucket_ownership_controls` / `OwnershipControls` sets `BucketOwnerPreferred` or `ObjectWriter`. Read both before rating ACL findings.
- Omitted BPA config: new buckets block public access by default. Account-level BPA may be set elsewhere. Status: Needs confirmation, Low–Medium at most.
- Intentional static hosting (`StaticSite`, CloudFront OAC)? Verify intent; NEVER flag as Critical by itself.
- Check the content type before rating.

### PE-04: Publicly accessible database

| Framework | Check |
|-----------|-------|
| TF | `publicly_accessible = true` on `aws_db_instance` or `aws_rds_cluster_instance` (Aurora: instances, NOT `aws_rds_cluster`); `aws_redshift_cluster` (default `false` only on provider ≥ 6.0, so check the provider constraint); `aws_dms_replication_instance` |
| CDK | `publiclyAccessible: true` on `DatabaseInstance`; Aurora: `ClusterInstance` options |
| CFN | `PubliclyAccessible: true` on `AWS::RDS::DBInstance` |

Confirm reachability: subnet routes to an internet gateway AND security group ingress from broad CIDRs. A public DNS setting alone is not unauthenticated access; report as High when network reachability is also confirmed, Medium otherwise.

### PE-05: OpenSearch / Elasticsearch

| Framework | Check |
|-----------|-------|
| TF | `aws_opensearch_domain` without `vpc_options`, or access policy `Principal: "*"` without conditions |
| CDK | `Domain` without `vpc`, or open access policy |
| CFN | `AWS::OpenSearchService::Domain` without `VPCOptions`, or open policy |

### PE-06: Load balancer open ingress

ALB/NLB internet-facing with `0.0.0.0/0` ingress and no WAF or authentication action. High only when the target serves sensitive operations; otherwise Medium.

## 2. Authentication and Authorization

### AA-01: Wildcard IAM actions

| Framework | Check |
|-----------|-------|
| TF | `actions = ["*"]` / `"Action": "*"` / service wildcards (`s3:*`) in `aws_iam_policy_document`, `aws_iam_*policy` |
| CDK | `PolicyStatement` `actions: ['*']` |
| SST | `permissions` / `link` with wildcard actions |
| CFN | `Action: '*'` in `AWS::IAM::Policy`, `ManagedPolicy` |

`Action: "*"` + `Resource: "*"` on an attached role = Critical. Service wildcards = High.

### AA-02: Wildcard resources

`Resource: "*"` where the action supports resource scoping. High. Exempt actions that require `*` (e.g. `ec2:Describe*`).

### AA-03: Trust policy without conditions

Cross-service assume-role missing `aws:SourceArn` / `aws:SourceAccount` (confused-deputy). Medium.

### AA-04: IAM users

`aws_iam_user` with console login profile or long-lived `aws_iam_access_key`. Prefer roles/SSO. Medium. MFA enforcement is an account policy: Needs confirmation.

### AA-05: Cross-account trust

Trust policy with external account principals and no `sts:ExternalId` (third-party access) or `aws:PrincipalOrgID` condition. High when the principal is outside the organization.

## 3. Encryption

AWS defaults (since 2022–2023) encrypt S3 objects (SSE-S3), SQS queues (SSE-SQS), DynamoDB (AWS-owned key). Missing config on these is NOT unencrypted data. See [aws-defaults.md](aws-defaults.md).

### EN-01: S3 encryption policy

| Situation | Finding |
|-----------|---------|
| No encryption block | None, or Informational (default SSE-S3 applies) |
| Policy requires CMK and bucket lacks `aws:kms` + key | Medium, "CMK policy" |
| `BucketEncryption.UNENCRYPTED` (legacy CDK) | Informational |
| `blocked_encryption_types = ["NONE"]` (re-enables SSE-C; new buckets block it by default since April 2026, except Bahrain and UAE Regions) | Low, "SSE-C allowed". Ask for the use case: AWS documents SSE-S3/SSE-KMS as the modern default |

Remediate with the standalone `aws_s3_bucket_server_side_encryption_configuration`; the inline `server_side_encryption_configuration` block is legacy.

### EN-02: RDS / Aurora storage encryption

| Framework | Check |
|-----------|-------|
| TF | `storage_encrypted = false` or absent on `aws_db_instance` / `aws_rds_cluster` |
| CDK | `storageEncrypted: false` or absent on `DatabaseInstance` / `DatabaseCluster` |
| CFN | `StorageEncrypted: false` or absent |

Absent = unencrypted for RDS instance and cluster resources (provider default `false`; only `engine_mode = "serverless"` clusters default to `true`). High (Confirmed when explicitly false or absent in a resource defined here). `aws_redshift_cluster` `encrypted` defaults to `true` only on provider ≥ 6.0: on 5.x or an unknown version, absent = Needs confirmation.

### EN-03: EBS

`aws_ebs_volume`, root/ebs block devices without `encrypted = true`. Account-level EBS default encryption may apply: Needs confirmation unless explicitly `false`. High if explicit `false`, Medium otherwise.

### EN-04: SQS and SNS

- SQS: SSE-SQS is on by default for new queues. Absent KMS key → NOT a finding. Explicit `sqs_managed_sse_enabled = false` with no KMS key → Medium. CMK policy gaps → Low.
- SNS: no default encryption. Topic without `kms_master_key_id` → Medium when it carries sensitive payloads; otherwise Low.

### EN-05: DynamoDB CMK

Encrypted by default with AWS-owned keys. Missing CMK is a policy question only. Low; Informational when no CMK policy applies.

### EN-06: TLS enforcement

| Check | Notes |
|-------|-------|
| S3 bucket policy without `aws:SecureTransport` deny | Medium |
| ALB listener on 80 without redirect to 443 | High on internet-facing |
| CloudFront `viewer_protocol_policy = "allow-all"` | High |
| API Gateway (HTTP and REST default endpoints) | TLS enforced by service. NOT a finding. Custom domain: check `security_policy` / TLS version |

### EN-07: Secrets in Terraform state

Plain `password` on `aws_db_instance`/`aws_rds_cluster` and any secret passed as a regular argument is stored in raw state. Prefer `manage_master_user_password = true`, or `password_wo` + `password_wo_version` with an ephemeral source (Terraform ≥ 1.11). Medium when state is remote and encrypted, High when local or the bucket is shared broadly. Provider 6.x `aws_instance.user_data` is stored in clear text: any credential there is SM-02.

## 4. Network

### NS-01: Open security group ingress

`0.0.0.0/0` or `::/0` ingress on 22, 3389, 3306, 5432, 6379, 27017, 9200 → High. Critical only when attached to an internet-reachable resource (confirmed public subnet + public IP or internet-facing LB). Other ports → Medium. Web ports 80/443 on a public LB are expected. Check BOTH styles: inline `ingress` blocks (`cidr_blocks`, `ipv6_cidr_blocks`) and `aws_vpc_security_group_ingress_rule` (`cidr_ipv4`, `cidr_ipv6`, `ip_protocol = "-1"`). Provider docs warn that mixing the styles on one group makes them conflict.

### NS-02: Unrestricted egress

All-protocol `0.0.0.0/0` egress. Low. Informational for default SG behavior.

### NS-03: Data stores in public subnets

Databases or caches in subnets with a route to an internet gateway. High when also publicly accessible; Medium otherwise.

### NS-04: Missing VPC endpoints

S3/DynamoDB reached from private subnets without gateway endpoints. Low.

### NS-05: VPC attachment

Check service-specific defaults before flagging:

| Service | Default |
|---------|---------|
| Lambda | AWS-managed network, no customer VPC. Not a finding unless the function reaches VPC-only resources |
| ECS/EC2/RDS | Default VPC used if no subnet group or VPC given. Medium |
| Managed services (S3, SQS, DynamoDB, API GW) | No VPC attachment. Not a finding |

### NS-06: EC2 instance metadata (IMDSv2)

| Framework | Check |
|-----------|-------|
| TF | `aws_instance` / `aws_launch_template` `metadata_options { http_tokens = "optional" }`; `http_endpoint = "enabled"` with `http_put_response_hop_limit` > 1 on non-container hosts |
| CDK | `Instance` / `LaunchTemplate` without `requireImdsv2: true` |
| CFN | `AWS::EC2::Instance` / `LaunchTemplateData` `MetadataOptions.HttpTokens: optional` |

Explicit `optional` = Medium (High when the instance is internet-facing or runs an SSRF-prone app visible in scope). Absent = Needs confirmation: account/Region defaults (`aws_ec2_instance_metadata_defaults`), an org declarative policy, or an AMI with `ImdsSupport: v2.0` may already require tokens. Hop limit 2 is correct for container hosts.

## 5. Edge and Perimeter

### EP-01: CloudFront without WAF

TF `aws_cloudfront_distribution` without `web_acl_id`; CDK `webAclId`; CFN `WebACLId`; SST CDN config. Medium for public endpoints serving APIs; Low for static content. WAF may be attached via `aws_wafv2_web_acl_association` or Firewall Manager: Needs confirmation.

### EP-02: ALB / API Gateway without WAF

Internet-facing ALB or REST/HTTP API without `aws_wafv2_web_acl_association` (WAF is not available on HTTP APIs: use throttling/auth). Medium.

### EP-03: Permissive CORS

`allow_origins = ["*"]` together with credentials, or on authenticated APIs. Medium. Public read-only content → Informational.

### EP-04: Rate limiting

Public API without stage throttling, usage plan, or WAF rate rule. Low–Medium. Higher when the endpoint triggers paid backends (cost abuse).

### EP-05: CloudFront viewer protocol

`allow-all` → see EN-06.

## 6. Logging and Monitoring

### LM-01: CloudTrail

Trails are often organization-managed outside the repo. No trail resource in scope → Not evidenced. Ask for central logging evidence. NEVER assert "CloudTrail missing" from local absence.

A trail defined here MUST be checked: `is_multi_region_trail = true`, `enable_log_file_validation = true` (both default `false`), `kms_key_id`, and `cloud_watch_logs_group_arn` (CFN `IsMultiRegionTrail`, `EnableLogFileValidation`, `KMSKeyId`, `CloudWatchLogsLogGroupArn`). Missing multi-Region or validation → Medium; missing KMS or CloudWatch Logs → Low. The trail's S3 bucket must not be public (PE-03).

### LM-02: VPC flow logs

VPCs defined here without `aws_flow_log` / `FlowLog`. Medium when this repo owns the VPC; Needs confirmation if network layer is shared.

### LM-03: S3 access logging

Buckets holding sensitive or audit data without `aws_s3_bucket_logging` / `serverAccessLogsBucket` / `LoggingConfiguration`. Low; data events in CloudTrail may substitute.

### LM-04: Alarms

Critical resources (RDS, Lambda, API) without alarms on errors, latency, throttles. Low. Alarms may live in a monitoring stack: Needs confirmation.

### LM-05: Access logs

ALB or CloudFront without access logs. Low–Medium.

## 7. Secrets

### SM-01: Hardcoded credentials

`grep` patterns: `AKIA[0-9A-Z]{16}`, `(password|secret|api_?key|token)\s*[=:]\s*["'][^"']{6,}`, private key headers. Exclude placeholders and variable references. Confirmed hit = Critical; rotate the secret.

### SM-02: Plaintext sensitive config

Secrets in Lambda/ECS environment variables, connection strings, user data. High. Use Secrets Manager or SSM SecureString references.

### SM-03: State and variable files

`*.tfvars` / `*.auto.tfvars` with secrets committed; remote state backend without `encrypt = true` or without locking (S3 backend: `use_lockfile = true`; `dynamodb_table` alone is deprecated, Informational). Medium.

## 8. Sanofi Policy (Sanofi projects only)

Run this section only for Sanofi repositories (confirm from remote, org, or tags convention). Skip otherwise and say so in the report.

### SN-01: Mandatory tags

Resources need `CE_Application_ID`, `CE_Application_Name`, `CE_Environment`, `team`, `name`, `env`, `version`, `service`, `cost_center`, `contact`. Provider `default_tags` count. Low.

### SN-02: terraform-aws-library modules

Raw `resource "aws_*"` where a `terraform-aws-library` module exists. Low (Terraform only).

### SN-03: Module source pinning

| Source | Check |
|--------|-------|
| Registry (`namespace/name/provider`) | `version` constraint present |
| Git (`git::`, `github.com/`) | `?ref=` pinned to tag or commit SHA, not a branch |
| Local (`./`, `../`) | Exempt (`version` is invalid there) |

Medium for unpinned registry/Git sources.

### SN-04: RFC patterns

Resources that should be compared with accepted patterns in `Sanofi-Accelerator/Request-for-Comments`. Informational.
