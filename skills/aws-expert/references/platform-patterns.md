Load when: choosing AWS services, or designing networking/egress, data, observability or account structure.

# Platform patterns

## Service-selection ladders

Start at the left. Step right only when the stated trigger applies; name the trigger in the answer.

| Need | Default → step up | Step-up triggers |
|---|---|---|
| Compute | Lambda → ECS on Fargate → ECS/EKS on EC2 | long-running or steady high load; GPU; kernel/daemon access. EKS only if the team already runs Kubernetes |
| Key-value / known access patterns | DynamoDB on-demand → provisioned + autoscaling | steady, predictable throughput |
| Relational | Aurora Serverless v2 or RDS → Aurora provisioned | steady load, read replicas, global database |
| Analytics | S3 + Athena → Redshift Serverless | frequent, concurrent, complex BI queries |
| Search | OpenSearch Serverless → managed OpenSearch domain | cost at steady volume; plugin needs |
| Integration | SQS (work) · SNS (fan-out) · EventBridge (routing, SaaS events) → Kinesis or MSK | ordered high-throughput streams; replay |
| Workflow | Step Functions | always prefer over hand-rolled orchestration in Lambda |
| Web front end | S3 + CloudFront → Amplify Hosting | SSR framework needs, team prefers managed CI |
| API | API Gateway HTTP API → REST API → ALB | REST API: usage plans, WAF, request validation. ALB: container backends |

Self-managed (databases on EC2, Kafka on EC2) needs a written reason: a feature or license the managed option lacks.

## Networking and egress

- Prototype: skip a custom VPC when every service is serverless with a public endpoint.
- VPC baseline: public, private and isolated subnets across ≥2 AZs (3 for regulated/high-scale).
- NAT: one per AZ for production (REL). A single NAT is cheaper but one AZ failure cuts egress; state the delta.
- Add S3 and DynamoDB gateway endpoints to every VPC: no hourly charge, cuts NAT data processing.
- Interface endpoints bill per AZ-hour plus per GB; add them when NAT data-processing for that service exceeds their cost, or when compliance requires private paths. Compute both live.
- Lambda in a VPC only when it must reach private resources.
- Keep chatty service pairs AZ-local where reliability allows; cross-AZ transfer is billed in each direction.
- Public IPv4 addresses are billed; front services with ALB/CloudFront, prefer IPv6 where clients support it.
- Hybrid: Site-to-Site VPN first; Direct Connect when bandwidth or latency needs justify it. Transit Gateway once more than a few VPCs need to talk.

## Data

- Pick the store from access patterns, not familiarity. Write the top 3 queries before choosing.
- Encryption at rest on by default; customer-managed KMS keys when key policy control or audit is required.
- Backups: AWS Backup plans with retention per tier; PITR on DynamoDB and relational stores in production.
- S3: lifecycle rules at bucket creation; versioning plus lifecycle for noncurrent versions; Object Lock only when retention is mandated.
- Data classification tags (`data-class`: public/internal/confidential/phi) on every store.

## Observability

- Structured JSON logs with request/trace IDs.
- Set a retention period on every log group at creation.
- Traces via OpenTelemetry (ADOT) or X-Ray for any multi-service request path.
- Alarm on SLOs (error rate, latency, queue age), route to SNS; dashboards per service.
- Custom metrics: watch dimension cardinality; each unique combination is a billed metric.
- Audit trail (CloudTrail) is separate from app logs; never mix retention policies.

## Account structure by tier

| Tier | Structure |
|---|---|
| Prototype / side project | single account; root MFA; IAM Identity Center user; budget alert |
| Production SMB | AWS Organizations; separate prod and non-prod accounts; IAM Identity Center; org CloudTrail; baseline SCPs |
| Regulated / high-scale | Control Tower landing zone; OUs (Security, Infrastructure, Workloads, Sandbox); log-archive and audit accounts; delegated admin for GuardDuty and Security Hub CSPM; region-allowlist SCP; PHI workloads in dedicated accounts |

Move up a tier when a second workload, team, or regulated dataset appears.
