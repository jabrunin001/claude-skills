---
type: concept
status: active
tags: [review, standards]
related: []
created: 2026-09-29
date_modified: 2026-09-29
---

# Review Standards

Single source of truth for `/pre-pr-review` and the `pattern-reviewer` / `security-reviewer` agents. Rules derive from `CLAUDE.md`; if they conflict, `CLAUDE.md` wins.

## Severity buckets

| Bucket | Meaning | Blocks merge? |
|---|---|---|
| **Action required** | Violates a hard rule, breaks structure, or leaks a secret | Yes |
| **Review recommended** | Judgment call: weak link, stale metadata, unclear naming | No, author decides |
| **Auto-fixable** | Mechanical: tag casing, spacing, lint | No, fix without discussion |

## Hard rules (Action required)

1. **Frontmatter.** Every note has `type`, `status`, `tags`, `related`, `created`, `date_modified`. `type` ∈ concept | mental-model | project | meeting | source | synthesis | moc | daily | session. `status` ∈ inbox | processed | active | archived.
2. **Protected folders.** No edits under `raw/`, `Archive/`, `_attachments/`, `_templates/`. `Daily/` is append-only (no deletions or rewrites of existing lines).
3. **Broken wikilinks.** Every wikilink resolves to an existing note.
4. **Secrets.** No API keys, tokens, passwords, or credentials in any file (see `security-reviewer`).
5. **MOC reachability.** Every new or moved `wiki/` note is linked from at least one MOC.
6. **Empty notes.** No non-MOC note under the validator's minimum word count.

## Judgment rules (Review recommended)

- **Link discipline.** A link must change how the reader understands the linked concept. Flag link-spam and dense link clusters with no explanatory context.
- **Reciprocal links.** A new note that mentions concepts covered by older notes should link to them in context.
- **Synonyms.** Same concept under two note names → one note plus `aliases:`.
- **`date_modified`** updated on every edited note.
- **Naming.** Descriptive filenames; never `untitled-N`.
- **Status drift.** `status: inbox` outside `Inbox/`, or Inbox items older than 14 days.

## Auto-fixable

- Tags kebab-case with no leading `#`.
- Spacing and other `npm run lint` findings.
- Trailing whitespace, missing final newline.

## Do not flag

- Tone, style, or wording of prose.
- Missing links where no genuine conceptual connection exists.
- Files outside the branch diff, unless the diff breaks them (e.g. a rename that breaks inbound links).
- `.smart-env/` and `.obsidian/` churn, unless it contains secrets.

## Finding format

Each finding: `severity | file:line | issue | evidence (quote or rule number) | suggested fix`. No finding without evidence.
