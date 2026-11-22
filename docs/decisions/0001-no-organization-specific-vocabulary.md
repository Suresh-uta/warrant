# ADR 0001 — No organization-specific vocabulary

**Status:** accepted · **Date:** 2026-11-21

## Context

Warrant began as an internal tool and is published publicly. Access-control
code is unusually prone to encoding the structure of whichever organization it
was first built for: seniority ladders, team identifiers, internal hostnames,
ticket IDs, system codenames.

Git history is effectively permanent. A rewrite is disruptive, forks are
already cloned, and code search has already indexed the content. A leak here
cannot be fixed by a follow-up commit.

## Decision

The engine's access primitives are opaque and organization-neutral:

- `clearance: int | None` — an ordinal tier, compared but never interpreted
- `groups: set[str]` — opaque identifiers, intersected but never parsed

Real tier values and group names live in deployment configuration, never in
code, tests, docs, or fixtures. Enforced by `scripts/check_vocabulary.py` in
pre-commit and CI.

The checker has two layers: structural patterns (committed, matching the
*shape* of internal vocabulary without naming any organization) and a local
`.vocabulary-denylist` which is **gitignored**.

## Alternatives rejected

**Ship a denylist of internal terms.** This is the obvious approach and it is
self-defeating: a committed list of internal codenames publishes the
codenames. Hence the untracked local file plus a CI secret, and the checker
printing `<redacted>` instead of echoing a matched term into public build logs.

**A style guideline in CONTRIBUTING.md only.** Guidelines are rediscovered
after the violation is already committed. For a permanent, unrewritable
medium, the check has to run before the commit exists.

**Keep the original vocabulary and document the mapping.** Would have required
every reader to mentally translate, and still published the internal structure
this ADR exists to protect.

## Consequences

- Examples read slightly more abstractly (`finance`, not a real team name).
- Deployments must write an `IdentityResolver` mapping their directory onto the
  primitives. This is work, but it is the same work that makes the project
  usable by anyone other than its author.
- False positives need `# vocab-ok: <reason>`. Suppressions are greppable and
  auditable.
