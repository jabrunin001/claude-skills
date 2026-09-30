# aws-expert setup runbook

Run these steps by hand. Claude never reads this file at runtime and never creates IAM resources.
Result: read-only AWS CLI profiles (`aws-expert-ro`, plus `aws-expert-ro-<account>` per client account), Cost Explorer enabled, and Claude Code guardrails (permission rules plus the `aws-guard` hook) in place.
The command rules the persona follows live in `references/tool-boundary.md`.

## Residual risk (read first)

**IAM allows data reads on this profile, and only Claude-side rules block them.**

- `ReadOnlyAccess` grants content reads: `s3:GetObject`, `dynamodb:GetItem/Query/Scan/PartiQLSelect`, `logs:GetLogEvents/FilterLogEvents/StartLiveTail`, `sqs:ReceiveMessage`, `kinesis:GetRecords`, `ssm:GetParameter*`, `ecr:GetAuthorizationToken`, `sts:GetSessionToken`. You chose not to add an IAM deny for these.
- The Claude-side layers (skill instructions, permission deny rules, `aws-guard` hook) match command text. They do not stop:
  - a boto3 or other SDK **script file** (`python3 report.py`); inline SDK code (`python -c`, `node -e`, `ruby -e`, ...) and `curl --aws-sigv4` are denied by `aws-guard`, script files are not read;
  - package scripts (`npm run <x>`) that call cdk, terraform or an SDK, except the denied `deploy`/`destroy`/`cdk` names; your `Bash(npm run *)` allow runs the rest without a prompt;
  - a renamed or symlinked `aws` binary, or `aws` calls inside a script file (`bash script.sh`);
  - obfuscation the guard cannot see through.
- A command word computed at run time (`$CMD ...`, `"$SHELL" -c ...`, `$(...)`) gets a permission prompt from `aws-guard`, not a block. Approve it only if you can tell what runs.
- `~/.claude/settings.local.json` allows `Bash(python3 *)`: in sessions started from your home directory, a boto3 script runs **without a prompt**. **Planned change (install step, applied with your diff approval):** move `Bash(python3 *)` from `allow` to `ask` in that file. After it, every `python3` call prompts, including the self-test in step 4.
- AWS mutation verbs (`create-*`, `delete-*`, ...) are denied by `aws-guard`; the static rules only ask for them, so reads on resources named like `test-cluster` are not blocked. Keep the hook installed: without it, those mutations prompt instead of being denied.
- The guard trusts the profile name. Every profile named `aws-expert-ro` or `aws-expert-ro-*` must use the `AWSExpertReadOnly` permission set; never give a write-capable profile such a name.
- PHI accounts: the persona warns and waits for your go-ahead before any call there. Safer: do not point an `aws-expert-ro*` profile at an account holding PHI until you add the IAM deny below.
- `terraform plan` without `-lock=false` runs without a prompt (accepted): it can take the state lock and block a teammate's apply until it finishes.
- Terraform credentials: the persona runs `AWS_PROFILE=aws-expert-ro[-<account>] terraform plan -lock=false` and stops if the provider or backend hard-codes another profile or role. `aws-guard` asks before `terraform plan`/`init` without the prefix: it would use whatever credentials your shell has, so approve only if intended.
- Cost Explorer: each API request is billed (rate on the Cost Explorer pricing page). The ~10 calls per session cap is an instruction, not enforced.

### Optional hardening: IAM explicit deny on data reads

Add this as a second inline policy on the `AWSExpertReadOnly` permission set. An explicit deny beats the allows in `ReadOnlyAccess`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyDataPlaneReads",
      "Effect": "Deny",
      "Action": [
        "s3:GetObject*",
        "dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:Scan",
        "dynamodb:PartiQLSelect", "dynamodb:GetRecords",
        "logs:GetLogEvents", "logs:FilterLogEvents", "logs:StartLiveTail", "logs:GetLogRecord",
        "kinesis:GetRecords",
        "sqs:ReceiveMessage",
        "ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath", "ssm:GetParameterHistory",
        "ecr:GetAuthorizationToken",
        "sts:GetSessionToken",
        "codecommit:GitPull", "codecommit:GetBlob", "codecommit:GetFile"
      ],
      "Resource": "*"
    }
  ]
}
```

- `s3:GetObject*` also blocks object ACL, tagging and attribute reads. Accept that or list the actions one by one.
- It also blocks reading Terraform state from an S3 backend under this profile, so `terraform plan` with remote state fails. Scope the deny with a `NotResource` for the state bucket if you need plans.
- To block Logs Insights as well, add `logs:StartQuery` and `logs:GetQueryResults`.
- Test in your own terminal after the change (Claude blocks this command by design): `aws s3 cp s3://<bucket>/<key> - --profile aws-expert-ro` must return `AccessDenied`.

## 0. Prerequisites (macOS)

```sh
brew install awscli
aws --version            # expect aws-cli/2.x
```

Optional tools the persona can use for `synth`/`diff`/`plan`:

```sh
npx aws-cdk@2 --version                                  # CDK without a global install (needs Node)
brew tap hashicorp/tap && brew install hashicorp/tap/terraform
```

## 1. Read-only identity (IAM Identity Center)

In the AWS console, signed in to the management account (or the Identity Center delegated admin):

1. IAM Identity Center → enable it if needed (organization instance).
2. Permission sets → Create permission set → Custom permission set.
   - AWS managed policy: `ReadOnlyAccess`. Add `AWSBillingReadOnlyAccess` only if you want billing console pages under this role.
   - Inline policy (pins cost, pricing and quota reads even if the managed policy changes):
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Sid": "CostPricingQuotaRead",
           "Effect": "Allow",
           "Action": [
             "ce:Get*", "ce:Describe*", "ce:List*",
             "pricing:GetProducts", "pricing:DescribeServices", "pricing:GetAttributeValues",
             "servicequotas:Get*", "servicequotas:List*"
           ],
           "Resource": "*"
         }
       ]
     }
     ```
   - Name: `AWSExpertReadOnly`. Session duration: 4 hours (1 hour if you prefer shorter).
3. AWS accounts → select the target account(s) → Assign users or groups → your user → `AWSExpertReadOnly`.
   Cost Explorer shows organization-wide cost only from the management account; assign it there too if you want that view.

Create the CLI profile in your own terminal:

```sh
aws configure sso --profile aws-expert-ro
```

Answers: session name of your choice; start URL `https://<your-subdomain>.awsapps.com/start`; SSO region = the Identity Center region; scopes = default `sso:account:access`; approve in the browser; pick the account and `AWSExpertReadOnly`; default region; output `json`.
Resulting `~/.aws/config` shape:

```ini
[profile aws-expert-ro]
sso_session = <session-name>
sso_account_id = <account-id>
sso_role_name = AWSExpertReadOnly
region = <default-region>
output = json

[sso-session <session-name>]
sso_start_url = https://<your-subdomain>.awsapps.com/start
sso_region = <identity-center-region>
sso_registration_scopes = sso:account:access
```

- Sign in: `aws sso login --profile aws-expert-ro` (your terminal; Claude asks before running it).

**Profile naming, one per account.** The guard accepts exactly `aws-expert-ro` or `aws-expert-ro-<account>`, where `<account>` is a short client or account slug (letters, digits, `.`, `_`, `-`; starts with a letter or digit), for example `aws-expert-ro-acme-prod`. Give each client account its own profile, all with `AWSExpertReadOnly`, sharing one `sso-session`:

```sh
aws configure sso --profile aws-expert-ro-<account>
```

Keep `aws-expert-ro` for your own default account. Name the profile when you start work ("use aws-expert-ro-acme-prod"); Claude re-runs the identity check on every profile or account change and waits for your confirmation.

## 2. Enable Cost Explorer

1. Management account → Billing and Cost Management → Cost Explorer → launch it. Data can take up to 24 hours to appear.
2. Account → "IAM user and role access to Billing information" → Activate. Needed for billing console pages under SSO roles; whether the Cost Explorer API needs it is unverified.

## 3. Verify the profile

```sh
aws sts get-caller-identity --profile aws-expert-ro
```

Expect your account ID and an ARN containing `assumed-role/AWSReservedSSO_AWSExpertReadOnly_`.

Negative test (no side effects; `--dry-run` only checks permission):

```sh
aws ec2 create-vpc --cidr-block 10.99.0.0/16 --dry-run --profile aws-expert-ro
```

Expect `UnauthorizedOperation`. `DryRunOperation` means the permission set can write: fix it before going further.

Cost and pricing reads (the first is one billed Cost Explorer request; Cost Explorer's only endpoint is `us-east-1`):

```sh
aws ce get-cost-and-usage --time-period Start=<YYYY-MM-01>,End=<YYYY-MM-DD> \
  --granularity MONTHLY --metrics UnblendedCost --region us-east-1 --profile aws-expert-ro
aws pricing describe-services --service-code AmazonEC2 --region us-east-1 --profile aws-expert-ro
```

## 4. Claude guardrails

Claude applies these through `update-config`, only after you approve the exact diff:

- Merge `settings-snippet.json` (permission deny/ask/allow rules plus the hook registration) into `~/.claude/settings.json`.
- Copy `aws-guard.py` to `~/.claude/hooks/aws-guard.py`.
- Move `Bash(python3 *)` from `allow` to `ask` in `~/.claude/settings.local.json` (see Residual risk).
- Install the agent and skill (see `README.md` install map).

Then:

1. Restart Claude Code (the first file in a new `~/.claude/agents/` directory and new hooks need it).
2. `/permissions`: the aws, terraform and cdk rules are listed.
3. `/hooks`: a PreToolUse `Bash` hook runs `aws-guard.py`.
4. `/agents`: `aws-expert` is listed.
5. `python3 ~/.claude/hooks/aws-guard.py --selftest`: all cases pass.
6. Ask Claude to run `aws s3 ls` without a profile: `aws-guard` blocks it and asks for `--profile aws-expert-ro or aws-expert-ro-<account>`.
7. Ask Claude to run `$SHELL -c 'echo hi'`: you get a permission prompt from `aws-guard`.

## 5. Don'ts

- Never paste access keys or session tokens into Claude.
- Don't export an admin `AWS_PROFILE` or `AWS_ACCESS_KEY_ID` in the shell that launches Claude.
- Don't keep long-lived access keys in `~/.aws/credentials`; use SSO.
- Don't add write policies to `AWSExpertReadOnly`. Use a separate profile for changes you run yourself.
