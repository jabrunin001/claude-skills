# Technique → Claude Code building block

| Technique type | Building block | Use when |
|---|---|---|
| Repeatable procedure the model should follow | **Skill** (`~/.claude/skills/<name>/SKILL.md`) | Multi-step workflow, reused across projects, needs its own instructions/assets |
| Specialist role with its own context/lens (e.g. security reviewer) | **Subagent** | Independent judgment wanted, parallel work, or protecting main context |
| Single prompt you trigger by name | **Slash command** (`.claude/commands/`) | Short, user-invoked, project-specific |
| Must happen every time, no model discretion | **Hook** (`settings.json`) | Pre-commit checks, auto-format, blocking dangerous actions |
| Standing rules/standards the model should always know | **CLAUDE.md** (project or user) | Conventions, patterns, definitions of done |
| Access to an external system (tickets, docs, DB) | **MCP server** | Task context lives in Jira/Linear/Confluence/etc. |
| Retrieval over a large corpus (chunk → embed → search) | **MCP/search tool** or vault search (Seekstone) | Corpus too large for context; want selective context |
| Measuring quality (precision/recall on labeled cases) | **Eval set + script** in a project | Need evidence a change helped |
| Lessons learned over time | **Capture loop**: finding → judge → new rule/skill | Recurring issues worth codifying |

## Ranking heuristic
1. Highest frequency of use × lowest setup cost first.
2. Prefer extending an existing skill/command over adding a new one.
3. Anything needing paid or external systems ranks lower unless the user already has them.
