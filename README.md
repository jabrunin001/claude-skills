# claude-skills

Claude Code skills, agents, and guardrails.

> **Status: draft.** `aws-expert` is authored, hardened, and simulated. Final validation is still in progress; expect updates.

## aws-expert

A principal-level AWS architect for Claude Code: design, FinOps, security (SOC 2 / HIPAA), and Terraform/CDK. Read-only on live AWS accounts.

| Path | Installs to | What it is |
|---|---|---|
| `skills/aws-expert/` | `~/.claude/skills/aws-expert/` | Auto-loading skill: method, answer shape, references |
| `agents/aws-expert.md` | `~/.claude/agents/aws-expert.md` | Subagent for deep design/review; preloads the skill |
| `hooks/aws-guard.py` | `~/.claude/hooks/aws-guard.py` | PreToolUse hook: read-only profile, blocks mutating/data/secret AWS calls |
| `settings/settings-snippet.json` | merge into `~/.claude/settings.json` | Deny/ask/allow rules + hook registration |

### Install

```bash
git clone https://github.com/jabrunin001/claude-skills.git ~/claude-skills
cd ~/claude-skills
mkdir -p ~/.claude/skills ~/.claude/agents ~/.claude/hooks
cp -R skills/aws-expert ~/.claude/skills/
cp agents/aws-expert.md ~/.claude/agents/
cp hooks/aws-guard.py ~/.claude/hooks/
python3 ~/.claude/hooks/aws-guard.py --selftest
```

Then **merge** `settings/settings-snippet.json` into `~/.claude/settings.json` (don't overwrite existing keys — ask Claude to do it with `/update-config` and review the diff), and restart Claude Code.

Set up the read-only AWS profile by following `skills/aws-expert/SETUP.md`. Read its **Residual risk** section: Claude permission rules are not a security boundary; IAM is.

### Use

- Ask any AWS design, cost, security, or IaC question — the skill loads automatically.
- `/aws-expert` loads the skill explicitly; "use the aws-expert agent" runs the subagent.

## pre-pr-review

Local pre-PR review for an **Obsidian vault run as an LLM wiki**: a `/pre-pr-review` command that runs the vault validator and lint, then fans out to two read-only reviewer agents and merges their findings into Action required / Review recommended / Auto-fixable buckets.

| Path | Installs to (project-level) | What it is |
|---|---|---|
| `pre-pr-review/commands/pre-pr-review.md` | `<repo>/.claude/commands/` | The `/pre-pr-review [goal]` command |
| `pre-pr-review/agents/pattern-reviewer.md` | `<repo>/.claude/agents/` | Frontmatter, linking, naming, MOC reachability, protected folders |
| `pre-pr-review/agents/security-reviewer.md` | `<repo>/.claude/agents/` | Secrets, unsafe scripts, MCP/settings exposure, personal data |
| `pre-pr-review/review-standards.md` | `<repo>/review-standards.md` | Single source of rules for the command and both agents |

```bash
cd /path/to/your/vault
mkdir -p .claude/commands .claude/agents
cp ~/claude-skills/pre-pr-review/commands/pre-pr-review.md .claude/commands/
cp ~/claude-skills/pre-pr-review/agents/*.md .claude/agents/
cp ~/claude-skills/pre-pr-review/review-standards.md .
```

Assumes the vault has `npm run validate` and `npm run lint`, a `main` branch, and the folder conventions named in `review-standards.md` (`raw/`, `Archive/`, `Daily/`, MOCs). Edit `review-standards.md` to match your repo; the agents read it at run time.
