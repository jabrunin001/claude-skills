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
git clone https://github.com/jabrunin001/claude-skills.git
cd claude-skills
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
