---
description: Review the current branch locally before opening a PR
argument-hint: [optional one-line goal of this change]
---

Run a pre-PR review of the current branch. Goal (optional): $ARGUMENTS

1. Determine the base (`main`) and collect the change set: `git diff --name-status main...HEAD` plus uncommitted changes from `git status --short`. If there are no changes, say so and stop.
2. Run `npm run validate` and `npm run lint`. Keep the output; treat validator errors as **Action required** findings.
3. Launch `pattern-reviewer` and `security-reviewer` in parallel. Give each: the change list, the goal (if any), and the pointer to `review-standards.md`. Give nothing else; do not paste the whole diff or whole vault.
4. Merge the results:
   - Deduplicate findings that point at the same file and issue.
   - Findings both reviewers raised go first.
   - Drop any finding without evidence, and any covered by "Do not flag" in `review-standards.md`.
5. Present findings in three buckets: **Action required**, **Review recommended**, **Auto-fixable**. Each line: `file:line | issue | evidence | suggested fix`. Start with a two-line TL;DR and counts per bucket.
6. If a goal was given, state whether the changes meet it.
7. Do not fix anything. End by asking which findings to fix. Auto-fixable items can be offered as one batch.
