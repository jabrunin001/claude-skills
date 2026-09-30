# aws-expert

Principal-AWS-architect method (design, FinOps, security, HIPAA/SOC 2, Terraform/CDK) with a read-only boundary on live accounts, plus the agent and guardrails around it.

## Why it exists

Plain model judgment on AWS drifts in three ways: hallucinated prices and eligibility, generic checklists with no decision, and over-engineered designs for small projects. It can also run mutating or data-reading commands. This skill fixes the answer shapes, forces live sources for volatile facts, and pins every account call to a read-only profile.

## When to engage

- Skill auto-loads on AWS design, review, migration to AWS, cost, security/compliance and IaC topics (`when_to_use` in `SKILL.md`). Not for plain CLI syntax or other clouds. Stack-neutral asks ("cheap backend for a hobby app") may not trigger it: say "on AWS" or type `/aws-expert`.
- Same name, two things: `/aws-expert` loads the skill in the main thread; "use the aws-expert agent" delegates to the agent (fresh context, preloads this skill).
- Prereqs for live calls: `SETUP.md` done (CLI, `aws-expert-ro` / `aws-expert-ro-<account>` profiles, guardrails). Without it, the skill falls back to docs and labels account facts unverified.

## How it works

| Piece | Role | Loaded |
|---|---|---|
| `SKILL.md` | stance, intake, answer shapes, freshness, safety summary, reference routing | on trigger, or preloaded by the agent |
| `references/pillars.md`, `platform-patterns.md`, `finops.md`, `compliance.md`, `iac.md`, `sources.md` | domain methods, loaded per the routing table | on demand |
| `references/tool-boundary.md` | full command catalog: allowed reads, paid reads, forbidden mutations, data/secret reads, plan/diff hygiene, file-write scope | before the first `aws`/`terraform`/`cdk` command |
| `~/.claude/agents/aws-expert.md` | persona identity, tools, subagent I/O; returns questions to the caller and stops | on delegation |
| `settings-snippet.json` | static deny/ask/allow rules on command text | harness, every session |
| `aws-guard.py` | PreToolUse hook on every Bash call: profile pinning, verb allowlist, bypass-form parsing, inline SDK code and `curl --aws-sigv4` denial, ask for Athena/Logs Insights and computed command words | harness, every Bash call |
| `SETUP.md` | human runbook; IAM profile and residual risk | never at runtime |

Enforcement layers, weakest to strongest: skill instructions → permission rules → hook → IAM. Only IAM is a hard boundary; the IAM data-read deny is optional hardening in `SETUP.md`.

The hook prints nothing for allowed reads and ordinary commands, so the normal permission rules still decide; it prints `deny` or `ask` JSON otherwise, and denies any command that mentions aws but fails to parse.

**Layer differences (deliberate):**
- Hook has no `if` filter: it must see every Bash call to ask on computed command words (`$CMD`, `"$SHELL" -c`, `$(...)`).
- Hook only: profile pinning (incl. ask on `terraform plan|init` without `AWS_PROFILE=<ro-profile>`), `AWS_*` env overrides (on `aws`, `terraform`, `cdk`, `npx cdk`; `AWS_PROFILE=<ro-profile>` passes), wrappers, `source`/`.` of stdin, brace-expanded command words, `npx -c`, inline SDK code (python, node, bun, ruby, perl, deno), `curl --aws-sigv4`, glue `get-connection(s)` without `--hide-password` (static: ask), data-plane services (`bedrock-runtime`, `iot-data`, ...), name heuristics (`*password*`, `get-*token*`, `*credentials*`). Static rules list specific ops.
- The hook tolerates `AWS_PROFILE=<ro-profile>` on `aws` calls too; `tool-boundary.md` still says `--profile` only (instruction is stricter).
- Static only: `cdk`/`sam` subcommands and arguments (incl. cdk `--app`/`-a`), `~/.aws` file reads, package scripts `npm|pnpm|yarn run deploy*|*deploy*|*destroy*|cdk*`. Both layers deny terraform mutations; the hook also when prefixed with `AWS_PROFILE=`.
- Static `aws * <verb>-*` families (`create-`, `delete-`, `run-`, `test-`, `deploy`, ...) are **ask**, not deny (round 3): resource names that start with a verb (`test-cluster`, `deploy-web`) would hard-deny reads. The hook is the deny authority; if it is missing or crashes, AWS mutations prompt instead. Exact-op rules (s3 rm/cp, secrets, credentials, data reads, `--debug`, terraform/cdk mutations) stay deny.
- Accepted (2026-09-29): `terraform plan` is auto-allowed without `-lock=false`. The `AWS_PROFILE=<ro-profile>` prefix is enforced as an ask: the hook asks on `terraform plan|init` without it (prefix, `env`, or earlier `export`), and wins over the static allow. With the prefix a lock attempt fails (read-only), so only an approved ambient-credential plan can take the lock.
- `aws * start-*` and `sso login`: static ask; the hook denies every `start-*` except Athena/Logs Insights (ask). `tool-boundary.md` says the user runs `sso login`; the ask is the backstop.
- Auto-allowed: `sts get-caller-identity`, `describe-*`, `list-*`, `s3 ls`, `pricing *`, `service-quotas get-*|list-*`, `terraform validate/plan`, `cdk`/`npx cdk`/`npx aws-cdk` `synth`/`diff`. Other `get-*` reads and Cost Explorer prompt. No allow rule starts with `*`.

## Mental hooks & unexpected rules

- "Lead with exactly one recommendation." → no option menus.
- "Before any architecture, get scale." → tier sets depth; small projects stay small.
- "Denied or blocked command → final. Never retry it in another form (wrapper, full path, SDK, other syntax)." → the model reports and stops instead of routing around a block.
- "You cannot ask the user directly. Every question goes back to the caller as your output." (agent) → account confirmation and intake cost one round trip.
- `ssm get-parameter*` is forbidden with or without `--with-decryption`; String parameters often hold secrets.
- `AWS_PROFILE=<ro-profile> terraform plan -lock=false`, never `-out`; `cdk synth/diff` run app code and may call AWS.

## Invariants — do not change

- Profile names `aws-expert-ro` and `aws-expert-ro-<account>` (`<ro-profile>`): `SKILL.md`, `tool-boundary.md`, `sources.md`, `aws-guard.py` (`PROFILE`, `PROFILE_RE`), `SETUP.md`. The hook denies any other profile.
- Label `# MUTATING: run yourself`: `tool-boundary.md`, `iac.md`, hook deny reason.
- Skill name `aws-expert` = folder name = agent `skills:` entry. No `disable-model-invocation` in `SKILL.md`: it blocks agent preload.
- `references/tool-boundary.md` path: linked from `SKILL.md` boundary and routing table.
- Hook output schema: `hookSpecificOutput.permissionDecision` = `deny`/`ask` with `permissionDecisionReason` (code.claude.com/docs/en/hooks).
- `SKILL.md` and references never name the agent, `SETUP.md`, or settings files.

## Editing guide

- New allowed or forbidden AWS operation: update `tool-boundary.md`, then `aws-guard.py` (`ALLOW_*`, `DATA_OPS`, `HIDE_PASSWORD_OPS`, `ASK_OPS`, `MUTATING_VERBS`, `SDK_RE`, `INLINE_FLAGS`, `TF_MUTATING`), then the matching rule in `settings-snippet.json`, then add a `CASES` row. Run `python3 aws-guard.py --selftest`.
- Settings patterns match command text; a mid-pattern `*` spans spaces, so avoid token-like fragments (`*token*`) that hit `--next-token`.
- Prices, quotas, eligibility lists: never hard-code; add the live source to `sources.md`.
- Domain content goes in the matching reference; `SKILL.md` keeps only routing and core rules (<120 lines).
- Unverified: relative reference links when the skill is preloaded into the agent. `SKILL.md` states the fallback base `~/.claude/skills/aws-expert/`; if phase 6 shows links fail, make them absolute.

## Install map (staged `target/` → live)

| Staged | Installed | How |
|---|---|---|
| `agents/aws-expert.md` | `~/.claude/agents/aws-expert.md` | copy |
| `skills/aws-expert/` (SKILL.md, references/, README.md, SETUP.md) | `~/.claude/skills/aws-expert/` | copy folder |
| `hooks/aws-guard.py` | `~/.claude/hooks/aws-guard.py` | copy |
| `settings/settings-snippet.json` | `~/.claude/settings.json` | merge: append `permissions.deny/ask/allow` entries and the `hooks.PreToolUse` entry; keep existing rules |
| (planned edit, no staged file) | `~/.claude/settings.local.json` | move `Bash(python3 *)` from `allow` to `ask`; closes the prompt-free boto3 path |

Conflict: the existing `Bash(npm run *)` and `Bash(npm test *)` allows in `settings.local.json` auto-run package scripts. The snippet's deny rules for `npm|pnpm|yarn run deploy*|*deploy*|*destroy*|cdk*` win over them, so those allows stay; any other script that calls cdk, terraform or boto3 still runs silently.

Claude installs through `update-config` only after the user approves the exact diff. Restart Claude Code afterward; the first file in a new `~/.claude/agents/` directory is not picked up live.
