Load when: any AWS design or review. Use it to run the six Well-Architected pillar lenses.

# Pillar lenses

<apply>

- Run all six lenses. Report only findings that change the design or rank in a review.
- Depth follows the tier: prototype = checks marked ★ only; SMB = all checks; regulated/high-scale = all checks plus evidence.

</apply>

## OPS: Operational excellence

Checks:
- ★ All infrastructure in IaC; no console-only resources.
- ★ Deploys through CI with plan/diff review before apply.
- Alarms on user-facing SLOs, not only CPU.
- Runbook per alarm; named owner.
- Small, reversible changes: feature flags, blue/green or canary.

Anti-patterns: manual hotfixes in the console · alarms nobody receives · one giant stack for everything.

Default moves: CloudWatch alarms → SNS → chat/email · IaC pipeline with policy checks · post-incident review for every Sev1/Sev2.

## SEC: Security

Checks:
- ★ Root: MFA on, no access keys, not used day to day.
- ★ Humans sign in through IAM Identity Center; no IAM users with long-lived keys.
- ★ S3 Block Public Access on at account level.
- ★ Secrets in Secrets Manager or SSM SecureString, never in code, env files or IaC state.
- Least-privilege roles per workload; no `*:*`; IAM Access Analyzer findings reviewed.
- Encryption at rest (KMS) and in transit (TLS via ACM) on every data store and endpoint.
- CloudTrail on in all regions; GuardDuty and Security Hub CSPM (FSBP standard) enabled.
- Workloads in private subnets; no `0.0.0.0/0` on admin ports; EC2 enforces IMDSv2.
- Multi-account: SCP guardrails (deny leaving org, deny disabling CloudTrail/GuardDuty, region allowlist).

Anti-patterns: shared admin credentials · security groups opened "temporarily" · wildcard resource policies · KMS key policies granting the whole account.

Default moves: permission boundaries for delegated role creation · short-lived credentials everywhere · WAF on public HTTP entry points. Control mapping for SOC 2/HIPAA lives in compliance.md.

## REL: Reliability

Checks:
- ★ Backups automated (AWS Backup or native), restore tested at least once.
- RTO and RPO stated per workload; DR strategy matches them.
- Multi-AZ for every production stateful service.
- Health checks and auto-replacement on compute.
- Retries with exponential backoff and jitter; idempotent handlers; timeouts on every call.
- Quota headroom checked live for services on the scaling path.
- Async boundaries (SQS/EventBridge) between components with different scaling or failure modes.

DR ladder (pick the cheapest meeting RTO/RPO): backup/restore → pilot light → warm standby → multi-site active/active.

Anti-patterns: single-AZ database in production · untested backups · synchronous chains with no timeouts · hard dependency on one region's control plane during failover.

Default moves: Multi-AZ managed databases · DLQs on every queue and async Lambda · deletion protection on stateful resources.

## PERF: Performance efficiency

Checks:
- ★ Service type fits the access pattern (key-value vs relational vs analytical).
- Graviton considered for compute and managed databases.
- Caching at the right layer: CloudFront, ElastiCache or DAX, API Gateway cache.
- Load test against the stated scale before launch.
- Latency-sensitive paths avoid cross-region and cross-AZ hops.

Anti-patterns: relational database used as a queue · oversized instances instead of horizontal scale · N+1 calls across services.

Default moves: CloudFront in front of every public web/API origin · connection pooling (RDS Proxy) for Lambda → relational.

## COST: Cost optimization

Checks:
- ★ Budget alert exists for the account.
- ★ Cost-allocation tags defined before first deploy.
- Top 3 cost drivers named in every design.
- Idle and non-prod resources scheduled or scaled to zero.

Anti-patterns: provisioning for peak with no autoscaling · commitments bought before usage is stable.

Estimate method, levers and traps: finops.md.

## SUS: Sustainability

Checks:
- High utilization over idle headroom: autoscaling, serverless scale-to-zero.
- Graviton and current-generation instance families.
- Data lifecycle: tier or expire data nobody reads.
- Region choice considers the provider's published carbon data when latency and compliance allow.

Anti-patterns: always-on dev environments · retaining every log and snapshot forever.

Default moves: lifecycle rules on buckets and log groups at creation · batch non-urgent work.
