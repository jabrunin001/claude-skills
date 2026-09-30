Load when: estimating cost for a design, reviewing a bill, or answering savings, tagging or commitment questions.

# FinOps

## Cost estimate method (feeds the design answer's cost range)

1. List every billable component, including the ones under "Cost traps".
2. For each, name its pricing dimensions (hours, requests, GB-month, GB transferred, ACU/RCU/WCU).
3. Set low and high usage from the intake scale. High = expected peak month, not a worst case.
4. Fetch unit prices live for the stated region (sources.md).
5. Multiply and sum per bound; round each bound to 2 significant figures.
6. Name the top 3 drivers and the usage assumption behind each.
7. Exclude free tier from production estimates; mention it only for prototypes.
8. Link a Pricing Calculator estimate when one was built.

Safer-option delta: run the method for both variants; report the difference of the ranges.

## Bill review method

1. Cost Explorer is paid per request: plan the queries, announce each one (limits: tool-boundary.md).
2. Drill order: service → usage type → linked account → cost-allocation tag.
3. Compare last full month with the prior one; rank movers by absolute change.
4. Untagged or unallocated share is itself a finding.
5. Output in the review findings shape; tag each finding COST unless another pillar dominates.

## Levers

**Allocation**
- Account per environment is the strongest allocation boundary; tags come second.
- Mandatory tags: `owner`, `env`, `app`, `cost-center`. Enforce with tag policies or IaC default tags; activate them as cost-allocation tags.
- Unit economics: cost per customer, tenant, or request. Needs tags plus a business metric; propose the metric.

**Commitments**
- Buy only against a stable baseline, at least one month of steady usage.
- Commit below the baseline floor; leave peaks on-demand or Spot.
- Savings Plan types and their service coverage change; check live before recommending one.
- Pick the most flexible plan that covers the baseline. Family- or region-locked plans only when the workload is locked too.
- Reserved capacity only where no Savings Plan applies.
- Review coverage and utilization monthly.

**Rightsizing and pricing model**
- Compute Optimizer and CloudWatch utilization before resizing; downsize one step at a time.
- Graviton where the runtime supports it.
- Spot for stateless, interruptible work: CI runners, batch, queue workers.
- Schedule non-prod off outside working hours; scale dev databases to minimum.

**Storage**
- gp3 over gp2; size IOPS and throughput separately.
- S3 Intelligent-Tiering for unknown access patterns; lifecycle to archive tiers for known cold data.
- Delete unattached volumes, idle Elastic IPs, orphaned snapshots and old AMIs.

**Guardrails**
- AWS Budgets per account with actual and forecast alerts.
- Cost Anomaly Detection monitor per account or cost category, routed to email/chat.

## Cost traps

Check each in every estimate and review:
- NAT gateway data processing, especially S3/DynamoDB traffic without gateway endpoints.
- Cross-AZ and internet data transfer.
- CloudWatch Logs ingestion and never-expiring log groups.
- High-cardinality custom metrics.
- Public IPv4 addresses.
- KMS requests at high call volume; use S3 Bucket Keys.
- Idle load balancers, idle provisioned databases, forgotten dev stacks.
- Snapshot and backup retention sprawl.
- Interface endpoints deployed in every AZ of every VPC by default.
- Support plan charges scaling with spend.
