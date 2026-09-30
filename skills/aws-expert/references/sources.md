Load when: about to state a price, quota, service eligibility, regional availability or launch status.

# Live sources

## Citation format

- Live: `(source: <URL or command>, checked YYYY-MM-DD)`
- Memory: `(unverified, from training data)`
- Estimate built from several prices: cite each unit price once, then the total.

## CLI templates

Fill the `<placeholders>`. `<ro-profile>` = the confirmed read-only profile (tool-boundary.md).

**Price List Query API** (`--region us-east-1` is the API endpoint, not the priced region; filter on `regionCode`. Other endpoints: `eu-central-1`, `ap-south-1`):
```
aws pricing describe-services --service-code <ServiceCode> --region us-east-1 --profile <ro-profile>
aws pricing get-attribute-values --service-code <ServiceCode> --attribute-name <attr> --region us-east-1 --profile <ro-profile>
aws pricing get-products --service-code <ServiceCode> --region us-east-1 --profile <ro-profile> --max-items 3 \
  --filters Type=TERM_MATCH,Field=regionCode,Value=<region> Type=TERM_MATCH,Field=usagetype,Value=<usagetype> \
  Type=TERM_MATCH,Field=operation,Value=<operation> --query 'PriceList[0]'
```
- Unknown service code → `describe-services --max-items 20` without `--service-code`.
- Unknown `usagetype`/`operation` → `get-attribute-values` for that attribute first.
- Each `PriceList` item is a JSON string: `--query` can only select items, not fields. Read `terms.OnDemand.*.priceDimensions.*.pricePerUnit` from the one item. Unsure the first item is the right product → drop `--query` once, tighten filters; never raise `--max-items`.

**Service Quotas** (applied value for this account and region):
```
aws service-quotas list-service-quotas --service-code <code> --region <region> --profile <ro-profile>
aws service-quotas get-service-quota --service-code <code> --quota-code <L-code> --region <region> --profile <ro-profile>
aws service-quotas get-aws-default-service-quota --service-code <code> --quota-code <L-code> --region <region> --profile <ro-profile>
```

**Cost Explorer** (paid per request; call limits in tool-boundary.md; single endpoint in `us-east-1`, covers all regions):
```
aws ce get-cost-and-usage --time-period Start=<YYYY-MM-DD>,End=<YYYY-MM-DD> --granularity MONTHLY \
  --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE --region us-east-1 --profile <ro-profile>
```
Drill down by swapping the group-by key: `USAGE_TYPE`, `LINKED_ACCOUNT`, or `Type=TAG,Key=<tag>`.

## Documentation catalog (WebFetch)

| Fact | Source |
|---|---|
| HIPAA eligible services | https://aws.amazon.com/compliance/hipaa-eligible-services-reference/ |
| SOC and other program scope | https://aws.amazon.com/compliance/services-in-scope/ |
| Service availability by region | https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/ |
| Endpoints and default quotas per service | https://docs.aws.amazon.com/general/latest/gr/aws-service-information.html |
| Service pricing pages | https://aws.amazon.com/pricing/ → service page |
| Savings Plans and coverage | https://aws.amazon.com/savingsplans/ |
| Multi-service estimate | https://calculator.aws/ |
| Launches and feature changes | https://aws.amazon.com/new/ |
| Well-Architected Framework | https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html |

Page moved or not found → WebSearch the fact with `site:aws.amazon.com` or `site:docs.aws.amazon.com`.
