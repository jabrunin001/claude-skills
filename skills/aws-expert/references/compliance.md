Load when: PHI, HIPAA, SOC 2, an audit, or other regulated data is mentioned.

# Compliance

## Stance

- Map controls to AWS services and evidence. Never attest, certify, or promise an audit outcome.
- End every compliance answer with: "Control mapping only, not a compliance attestation; confirm with your auditor or counsel."
- AWS eligibility or scope ≠ compliance. Configuration and operation are the user's side of the shared responsibility model.

## HIPAA

**Prerequisites**
- A BAA with AWS is accepted (AWS Artifact) for every account that stores or processes PHI. Not confirmed → say so before any design detail.

**Eligibility check (every PHI design, no exceptions)**
1. List every service that stores, processes or transmits PHI, including logging, monitoring, analytics, AI/ML, backup, email and support paths.
2. Check each against the live HIPAA eligible services list (sources.md). Record URL and check date.
3. Check the specific feature or mode too; eligibility can exclude features within an eligible service.
4. Any service not on the list → redesign it out of the PHI path. Never say "probably eligible".
5. List unavailable → mark the design blocked on eligibility, not unverified-and-continue.

**PHI boundary design**
- PHI in dedicated accounts under a regulated OU; non-PHI workloads elsewhere.
- Data flow diagram marks every point where PHI enters, rests and leaves.
- Encryption at rest with customer-managed KMS keys; key policies scoped to PHI workloads.
- TLS on every hop, including internal service-to-service.
- No PHI in logs, metric names or dimensions, tags, resource names, S3 keys, queue attributes or error messages.
- Access logging on PHI stores (CloudTrail data events, S3 server access logs or equivalent) retained per policy.
- Least-privilege, role-based access; break-glass role with alerting.
- Non-prod uses de-identified or synthetic data.
- Backups encrypted, retained per policy, restore tested.

## SOC 2 control map

| Area | AWS controls | Evidence to keep |
|---|---|---|
| Logging and monitoring | org CloudTrail with log file validation; AWS Config recorder; GuardDuty; Security Hub CSPM; CloudWatch alarms | trail and recorder config; finding triage records |
| Encryption | KMS; default encryption on S3, EBS, RDS; TLS via ACM; key rotation | encryption settings per store; key policies |
| Access control | IAM Identity Center; MFA; least-privilege roles; IAM Access Analyzer; no root use | permission set definitions; periodic access review records |
| Change management | IaC in version control; PR review; CI with plan/diff and policy checks; Config drift rules | PR history; pipeline logs; plan artifacts without secrets |
| Availability and backup | Multi-AZ; AWS Backup plans; DR runbook | backup job reports; restore test records |
| Incident response | GuardDuty/Security Hub CSPM routing; on-call runbooks | incident tickets; post-incident reviews |
| Vendor and data management | data classification tags; lifecycle and deletion rules | classification inventory; deletion logs |

## Evidence approach

- Prefer continuous evidence: AWS Config conformance packs and Security Hub CSPM standards over screenshots.
- AWS Audit Manager can collect evidence; check live that it supports the needed framework and region.
- Evidence artifacts must never contain secrets or PHI.
