Load when: before the first `aws`, `terraform` or `cdk` command in a session.

# Tool boundary

Anything not listed as allowed is forbidden.

## Profile and identity

- `<ro-profile>`: `aws-expert-ro`, or `aws-expert-ro-<account>` for one account per client. The user names none → `aws-expert-ro`. No other profile.
- Identity check: `aws sts get-caller-identity --profile <ro-profile>`. State account ID and profile; wait for the user's confirmation.
- Run it before the first AWS call of a session and again whenever the account or profile changes.

## Invocation form

- One `aws` call per command, `aws` as the literal command word: `aws <service> <operation> ... --profile <ro-profile>`.
- `--profile` on every call except local `--version` and `help`.
- `aws` calls: no `AWS_*` environment overrides (`AWS_PROFILE`, `AWS_CONFIG_FILE`, `AWS_SHARED_CREDENTIALS_FILE`, `AWS_ACCESS_KEY_ID`, ...); use `--profile`. Allowed: `AWS_REGION`, `AWS_DEFAULT_REGION`, `AWS_PAGER`, `AWS_DEFAULT_OUTPUT`. `terraform`/`cdk` take `AWS_PROFILE=<ro-profile>` only (see "Plan and diff").
- Prefer plain `aws ...`. Wrapped reads (`timeout`, `watch`, `sh -c`, `eval`, `find -exec`) get the same checks as plain ones.
- Forbidden: `xargs`/`parallel` feeding `aws`, piping, heredoc, `source <(...)` or `. /dev/stdin` into a shell (`source`/`.` count as shells), `python -m awscli`, credential injectors (`aws-vault exec`, `granted`/`assume`), `--debug` (prints signed headers with the session token).
- Command word from a variable, substitution or brace expansion (`$CMD`, `"$SHELL"`, `$(...)`, `{a,b}`) → the user gets a confirmation prompt. Glob or braces that can yield `aws` (`a?s`, `{aws,}`) → denied. Avoid all of them.
- AWS CLI only. No boto3, SDK scripts, inline SDK code (`python -c`, `node -e`), or `curl --aws-sigv4` against AWS APIs.

## Allowed reads

| Tool | Allowed |
|---|---|
| `aws` any service | `describe-*`, `list-*`, `get-*` returning metadata, minus every item under "Forbidden: data, secrets, credentials" |
| `aws sts` | `get-caller-identity` |
| `aws ce` | `get-*` (paid, see below) |
| `aws pricing` | `describe-services`, `get-attribute-values`, `get-products` |
| `aws service-quotas` | `get-*`, `list-*` |
| `aws s3` | `ls` |
| `aws configure` | `list`, `list-profiles` |
| `aws` local | `--version`, `help` |
| `terraform` | `AWS_PROFILE=<ro-profile>` prefix; `init` (no `-migrate-state`), `validate`, `plan -lock=false` (no `-out`) |
| `cdk` | `synth`, `diff` |

## Paid and exposing reads

- Cost Explorer (`ce get-*`): ≤10 calls per session. Announce each call and its purpose before running it. Unit price: check sources before quoting it.
- Athena `start-query-execution` and CloudWatch Logs Insights `start-query`: ask the user first. State the scanned scope and cost driver. Same for their `get-query-results`: results are data.
- Read-only profile lacks Athena query permission; expect AccessDenied, then give the query as text.
- `aws sso login`: The user runs it themselves; if you run it, they get a prompt.

## Forbidden: mutations

- `aws`: every operation outside "Allowed reads". Includes create, put, update, delete, modify, attach, detach, associate, run, start, stop, reboot, terminate, tag, untag, enable, disable, register, restore, import, export, copy, authorize, revoke, send, publish, invoke, execute, purge, rotate, batch-*.
- `aws s3`: `cp`, `mv`, `rm`, `sync`, `mb`, `rb`, `presign`, `website`.
- `terraform`: `apply`, `destroy`, `import`, `state *`, `taint`, `untaint`, `refresh`, `force-unlock`, `login`, `workspace new|delete`, `plan -out`, `init -migrate-state`; denied even with the `AWS_PROFILE=<ro-profile>` prefix.
- `cdk`: `deploy`, `destroy`, `bootstrap`, `import`, `watch`, `gc`, `rollback`, `refactor`, `migrate`.
- `sam`: `deploy`, `delete`, `sync`, `remote`.
- Package scripts that deploy or destroy (`npm|pnpm|yarn run deploy`, `cdk`, `*destroy*`): never run; give the command as text.
- "Just deploy / apply it" → refuse; give the command as text.

## Forbidden: data, secrets, credentials

These are "get" calls that return content, not metadata.

| Class | Operations |
|---|---|
| Secrets | `secretsmanager get-secret-value`, `batch-get-secret-value`; `ssm get-parameter*` (any, with or without `--with-decryption`); `kms decrypt`; any op containing `password` except `iam get-account-password-policy`; any call with `--include-value*` (`apigateway get-api-key(s)`) |
| Credentials, tokens | `sts assume-role*`, `get-session-token`, `get-federation-token`; any `get-*token*` (`ecr`/`codeartifact get-authorization-token`, `eks get-token`); any op containing `credentials`; `ecr get-login-password`; `ec2 get-password-data`; `rds generate-db-auth-token`; `lightsail get-instance-access-details`; `configure get|set|export-credentials|import|sso` |
| Object and item content | `s3 cp|sync` to local, `s3api get-object*`, `select-object-content`; `dynamodb get-item|batch-get-item|query|scan|execute-statement`; `get-records` (Kinesis, DynamoDB Streams); `glacier get-job-output`; `ebs get-snapshot-block`; `redshift-data get-statement-result*`; `codecommit get-blob|get-file|get-folder` |
| Logs and consoles | `logs get-log-events|get-log-record|filter-log-events|tail|start-live-tail`; `sqs receive-message`; `ec2 get-console-output|get-console-screenshot` |
| Config content | `appconfig get-configuration`, `appconfigdata get-latest-configuration` |
| Data behind list/describe/get | `cognito-idp list-users|list-users-in-group|describe-user-pool-client`; `stepfunctions describe-execution|get-execution-history`; `ssm get-command-invocation`; `glue get-connection|get-connections` (allowed only with `--hide-password`); `appsync list-api-keys` |
| Data-plane services (any op) | `iot-data`, `kinesis-video-media`, `kinesis-video-archived-media`, `mediastore-data`, `sagemaker-runtime`, `bedrock-runtime`, `bedrock-agent-runtime`, `qldb-session` |

- Files: never read `~/.aws/credentials`, `~/.aws/sso/cache/`, `~/.aws/cli/cache/`, `~/.aws/login/cache/`. Never write under `~/.aws/`.
- Metadata that can carry secrets (Lambda and ECS environment values, EC2 user data, CloudFormation parameters, Terraform outputs): prefer `--query` projections that return names only (`keys(Environment.Variables)`). In any output you relay or write, report names and shape only; redact values as `<redacted>`.
- Secrets in files you write: reference by Secrets Manager or SSM name, never by value.

## Plan and diff

Not purely read-only: they run provider and app code, read state, and write local files.

- Say before running: directory, command, what it writes.
- `terraform init`: writes `.terraform/` and `.terraform.lock.hcl`; downloads providers.
- Credentials: run as `AWS_PROFILE=<ro-profile> terraform plan -lock=false` (same prefix for `init`; without it the user gets a prompt). Never `-out`; a saved plan stores sensitive values.
- Provider or backend hard-codes another `profile`, `assume_role` or credentials file → do not run; stop and tell the user.
- `terraform output`, `console`, `show`: ask first; they print state values, including sensitive ones.
- `cdk synth` / `cdk diff`: run the app code; write `cdk.out/`; may call AWS lookups with the ambient profile. Pass `--profile <ro-profile>`.
- Never pass `--app`/`-a` to `cdk`: it runs any command. The app comes from the project's `cdk.json`.
- Never commit `cdk.out/`, `.terraform/`, plan files or state.

## Mutating commands as text

- First line `# MUTATING: run yourself`.
- Then: effect, blast radius, rollback, and `--profile <write-capable-profile>`; never a `<ro-profile>`.
- A denied read that is only outside the allowlist is not a mutation: give it as text without the label.

## File writes

- Only when the user asks. Only inside the current project root.
- No code project open (e.g. a notes vault) → ask the user for the target directory before writing.
- Allowed: Terraform, CDK, design docs, READMEs for them.
- Never: `~/.aws/`, `~/.claude/`, state files, plan files, credentials, secret values, files outside the project.
