---
name: course-to-setup
description: Turn a course (transcript + notebooks/files) into recommended Claude Code skills and an AI-setup structure. Use when the user gives a course transcript, lesson notebooks, or course files and wants skill recommendations or a setup plan based on them.
---

# course-to-setup

Input: a folder or file paths holding a course transcript (`.docx`, `.txt`, `.md`) and/or lesson files (`.ipynb`).
Output: one `synthesis` note in the vault's `Projects/` folder (the current working directory; ask if it isn't a vault) with ranked skill recommendations and a proposed setup structure. **List skills only — never draft their SKILL.md files** unless the user asks afterward.

## Process

1. **Inventory.** List the input paths. Ignore Office lock files (`~$*`) and `.ipynb_checkpoints/`. Confirm paths with the user if none were given.
2. **Extract text** to the scratchpad directory (no installs needed):
   - `.docx`: `unzip -p "<file>" word/document.xml | python3 -c "import sys,re;x=re.sub(r'</w:p>','\n',sys.stdin.read());print(re.sub(r'<[^>]+>','',x))" > transcript.txt`
   - `.ipynb`: parse with `json`; print markdown + code cells, skip outputs and boilerplate (kernel notices, download tips, warning filters).
3. **Read in chunks.** Grep for lesson boundaries ("In this lesson", "next lesson"), then read one lesson at a time. Never load the whole transcript at once.
4. **Extract techniques.** For each technique the course teaches: name, one-line description, evidence (lesson + timestamp or notebook cell). Separate what the instructor *does* from what they merely *mention*. Notebook code often imports a `src/` folder that is absent: infer concepts from structure and markdown, do not try to run it.
5. **Map to building blocks** using `assets/mapping-guide.md`.
6. **Check existing setup** to avoid duplicates: list `~/.claude/skills/`, the vault's `.claude/commands/`, `~/.claude/commands/`, and the available subagent types. Mark each recommendation as `new`, `extend <existing>`, or `already covered`.
7. **Write the note** from `assets/output-template.md` into `Projects/<Descriptive Title>.md`. Follow the vault's CLAUDE.md: required frontmatter, kebab-case tags, no link spam, flag gaps explicitly rather than filling them. Never write into `raw/`.
8. **Report** in a few lines: top 3 recommendations, the note path, and open gaps. Ask which recommendations to build next.

## Rules

- Be direct and terse; pick a recommendation and rank them.
- Every recommendation cites course evidence. No evidence, no recommendation.
- Prefer fewer, higher-leverage recommendations (aim for 5–8) over an exhaustive list.
- If a technique needs external tooling the user lacks (Jira, Confluence, a code-review SaaS), say so under gaps and give the closest local substitute.
