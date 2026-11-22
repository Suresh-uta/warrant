# ADR 0003 — Security and consistency are separate problems

**Status:** accepted · **Date:** 2026-11-21

## Context

When a document update *narrows* its access rule, both naive orderings fail:

- Write new chunks, then delete old → a window where the old, broader rule is
  still live. **Leaks.**
- Delete old, then write new → a window where the document is invisible. Safe,
  but a visible availability regression on every edit.

Typical search stores offer no multi-document transaction, so a single atomic
update across a document's chunks is not available.

## Decision

Stop treating it as one problem.

**Security — never over-expose.** On any ACL change, apply the new restrictive
rule to the *existing* chunks first, as a partial update touching only ACL
fields, before any content work. Narrowing is monotonically safe: applying it
early cannot expose anything.

**Consistency — never serve mixed versions.** Handled independently by
`pending`/`active` chunk state. Write new chunks as `pending`, flip to
`active`, delete the old. The flip is not atomic, so both versions are briefly
active — deduplicated by `document_id` at rerank time, keeping the higher
version.

## Rationale

The two properties have different costs when violated. A security violation is
unbounded and unrecoverable — restricted content reached someone. A consistency
violation is bounded and cosmetic — a result appears twice for a few hundred
milliseconds.

Treating them as one problem forces the weaker property's solution to carry the
stronger property's guarantee, which is why it leads toward distributed
transactions. Solving them separately lets each use a mechanism proportionate
to its actual cost.

## Alternatives rejected

**Query-time version gate.** Store an authoritative `active_version` per
document in a strongly-consistent store and filter on it at query time. Correct,
but adds a lookup to every query's hot path and a second store to keep
available.

**Accept the leak window as "small".** A window measured in milliseconds is
still a window, it is exercised on every permission narrowing (precisely when
someone has decided content is sensitive), and it is undetectable after the
fact.

**Delete-then-write everywhere.** Safe and simple, but makes every edit a
visible outage for that document, which trains users to distrust the index.

## Consequences

- ACL fields must be independently updatable from content — hence `acl_hash`
  separate from `content_hash` (see `docs/architecture.md`).
- The reranker must deduplicate by `document_id`. This is now load-bearing, not
  a nicety.
- Full reindexes use the same split one level up: build alongside, evaluate,
  swap the alias atomically.
