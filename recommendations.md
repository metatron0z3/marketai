# CLAUDE.md Best Practices Guide

## The core principle: CLAUDE.md is for what Claude would get *wrong* without it

Every line in CLAUDE.md competes for attention with the actual work. The file is loaded in full at the start of every session, so bloat has a real cost — it dilutes the instructions that matter.

The key question to ask about any piece of information: **would Claude misunderstand or fail without this, in every session?** If no, it doesn't belong here.

---

## What belongs in CLAUDE.md vs. elsewhere

### ✅ Put in CLAUDE.md
- **Commands Claude needs verbatim** — exact test, build, lint, and deploy strings (e.g. `pnpm test:integration`, `make build-docker`). Claude will use these literally, so precision matters.
- **Project-unique conventions** — things that contradict defaults or that Claude would guess wrong (e.g. "use named exports, not default exports", "use Workspace not Project in all copy").
- **Architecture orientation** — a one-line project description and a map of the repo structure, especially in monorepos where Claude needs to know where to look.
- **Non-obvious constraints** — environment quirks, deployment gotchas, or patterns that differ from framework conventions.

### ❌ Don't put in CLAUDE.md
- Generic instructions like "write clean code" or "follow best practices" — too vague to be useful.
- Anything already in README.md — don't duplicate it. Instead, use a pointer: `@README.md` or `See README.md for project overview.`
- Information only needed for specific tasks — put those in `docs/` and reference them with `@docs/filename.md` when needed. This way, you don't load a bunch of stuff you don't need in every coding session.
- Fast-changing state — if it might change next week, use prompts instead. CLAUDE.md is for durable truths.

---

## The README.md duplication problem

This is the most common CLAUDE.md mistake. The fix is to **point, not copy**. Your CLAUDE.md can simply say:

```markdown
## Project Overview
See README.md for full project description and setup instructions.
```

Then only add the delta — things the README doesn't cover that Claude specifically needs. CLAUDE.md should onboard Claude into your codebase, not replace your existing documentation.

---

## Using the file hierarchy to stay lean

Claude Code uses two distinct mechanisms for loading CLAUDE.md files: ancestor files load at startup (Claude walks up the directory tree), while descendant files load lazily — only when Claude reads files in those subdirectories.

Use this to your advantage as the project grows:

```
/project-root/CLAUDE.md          ← shared repo-wide conventions only
/project-root/frontend/CLAUDE.md ← frontend-specific patterns (lazy loaded)
/project-root/backend/CLAUDE.md  ← backend-specific patterns (lazy loaded)
/project-root/CLAUDE.local.md    ← your personal preferences, gitignored
```

Frontend developers don't need backend-specific instructions cluttering their context, and vice versa. Splitting keeps each file small and the root file minimal.

---

## Target size and maintenance

Target: under 300 lines. Focus on what Claude would get wrong without the file. A root CLAUDE.md that's just 50–80 lines and points to `docs/` for the rest is ideal.

**On maintenance:** Every few weeks, ask Claude to review and optimize your CLAUDE.md. Instructions accumulate, some become redundant, others conflict. You can literally prompt: *"Review CLAUDE.md and remove anything redundant, already in README.md, or too generic to be useful."*

When Claude Code suggests big additions after a project expansion, treat that as a diff to review, not accept wholesale. Ask: does each new section contain something Claude would actually get wrong — or is it just documentation restating what's already elsewhere?

---

## A practical template structure

```markdown
# ProjectName

One sentence: what this is and the core stack.
See README.md for full details.

## Commands
- Build: `npm run build`
- Test: `npm test -- --watch`
- Lint: `npm run lint:fix`

## Architecture
- `src/core/` — domain logic, no framework dependencies
- `src/api/` — Express routes, thin layer only
- `src/workers/` — background jobs (see @docs/workers.md)

## Conventions
- Named exports only, no default exports
- All async functions must handle errors explicitly
- Use `zod` for all external input validation

## Non-obvious constraints
- Never mutate `config` objects — treat as frozen
- The `legacy/` folder is untouched — don't refactor it
```

Everything else — detailed architecture decisions, feature specs, implementation plans — lives in `docs/` and gets referenced on demand.
