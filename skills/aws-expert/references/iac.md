Load when: writing or reviewing Terraform or CDK, or reading plan/diff output.

# Infrastructure as code

## Choose one per project

1. Project already uses Terraform or CDK → use it. Never mix both in one stack.
2. Greenfield → Terraform when infra is managed apart from app code, spans non-AWS providers, or reviewers read plans. CDK when one TypeScript or Python team owns app and infra together, especially Lambda-heavy apps.
3. State the choice and the one-line reason in the design answer.

## Structure

**Terraform**
- Root module per environment/account; shared logic in versioned modules.
- Remote state in S3, encrypted, with locking; access limited to the deploy role.
- Pin Terraform and provider versions; commit `.terraform.lock.hcl`.
- `default_tags` in the AWS provider for mandatory tags.
- Variables for environment differences; no copy-pasted environment folders.

**CDK**
- One app; stacks split by lifecycle and blast radius (network, data, app).
- Explicit `env` (account, region) for production stacks.
- Commit `cdk.context.json`.
- `Tags.of(app)` for mandatory tags; Aspects for org-wide rules.
- L2 constructs by default; L1 only for missing features.
- Stateful resources: `RemovalPolicy.RETAIN` and deletion protection.

## Secrets and state

- Never put secrets in variables, `tfvars`, CDK context or code. Reference Secrets Manager or SSM parameters by name or ARN.
- Terraform state can hold sensitive values: treat the state bucket as sensitive data.
- Mark sensitive outputs `sensitive = true`.

## Policy as code

- Run in CI before plan review: Checkov or Trivy for Terraform; cdk-nag for CDK; cfn-guard for synthesized templates.
- Failing Critical/High checks block merge. Suppressions need an inline reason.

## Reading plan/diff output

Summarize counts first (add / change / destroy), then flag:

| Signal | Severity |
|---|---|
| Destroy or replace of a stateful resource (database, bucket, table, volume, KMS key) | Critical |
| IAM policy widened: `*` actions or resources, new trust principals | Critical |
| Public exposure: `0.0.0.0/0` ingress, public bucket or snapshot | Critical |
| Encryption, logging or deletion protection turned off | High |
| Replace of stateless compute behind live traffic | Medium |
| Tag-only or description changes | Low |

- Replacement markers: Terraform `-/+` or "must be replaced"; CDK `[-]`/`[+]` pairs or "replace".
- Unexpected drift in the plan → report it; never propose `refresh` or `import` as a fix without the user.

## Writing next steps as files

- Output: module or stack skeleton, variables with safe defaults, and a README listing the plan/diff command and, under `# MUTATING: run yourself`, the apply/deploy command.
- Match the project's existing layout, naming and formatter (`terraform fmt`, project linter).
