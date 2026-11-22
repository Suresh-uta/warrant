# Architecture

Warrant is a backend component, not a chat UI. It ingests documents, indexes
them with their access rules attached, and answers questions over only the
subset a given caller is entitled to see.

## Design constraints

1. Access control is a **retrieval** concern. Filtering after retrieval is both
   a security smell and a quality bug.
2. Document structure carries meaning. A table flattened into prose has lost
   the information that made it answerable.
3. Answers must be traceable. An unciteable answer is a guess with good
   grammar.
4. Changes ship on measurement. A retrieval change that isn't evaluated is a
   coin flip with extra steps.

## Document identity

```
document_id      = stable_hash(source_type, source_uri)   # never changes
document_version = monotonic int, bumped per accepted change
content_hash     = hash(raw bytes)
acl_hash         = hash(DocumentACL.acl_hash_input())
config_hash      = hash(parser_ver, chunker_ver, context_model, embed_model)
```

Idempotency falls out of this: if `content_hash`, `acl_hash`, and `config_hash`
all match what is indexed, the event is a no-op. A queue redelivering the same
message five times does nothing four times.

`acl_hash` is separate from `content_hash` on purpose. An ACL-only change must
trigger a cheap ACL-only update, not a full reparse and re-embed.

## Ingest pipeline

Each stage caches its output under a key that includes **only** the config that
affects that stage. This is what prevents one document edit, or one model swap,
from forcing a full corpus rebuild.

| Stage | Cost | Cache key | Re-runs when |
|---|---|---|---|
| Parse → structured blocks | High | `content_hash + parser_ver` | Document edited, parser upgraded |
| Blocks → chunks | Low | `+ chunker_ver` | …also chunking changed |
| Chunks → contextualized | High (LLM) | `+ context_model` | …also context model swapped |
| Contextualized → vectors | Medium | `+ embed_model` | …also embedding model swapped |

A consequence worth stating plainly: **the embedding model is the most
expensive decision to reverse.** Changing it invalidates every vector with no
reuse possible. It belongs in `config_hash` so that a change is at least
*detected* rather than silently producing a mixed-model index.

## The write path: security and consistency are separate problems

A document update that *narrows* its ACL is the subtle case. The naive
approaches both fail:

- Write new chunks, then delete old → a window where the old, broader ACL is
  still live. **Leaks.**
- Delete old, then write new → a window where the document is invisible. Safe,
  but a visible availability regression on every edit.

There is no multi-document transaction available in a typical search store, so
a single atomic mechanism isn't on the table. The way out is to stop treating
it as one problem:

**Security — never over-expose.** When an update changes an ACL, apply the new,
restrictive ACL to the *existing* chunks **first**, as a cheap partial update
touching only ACL fields, before any content work begins. Narrowing is
monotonically safe: applying it early can never expose anything. By the time
content churns, the restrictive rule is already live.

**Consistency — never serve mixed versions.** Handled separately by
`pending`/`active` chunk state. Write new chunks as `pending`, flip to
`active`, then delete the old. The flip is not atomic across chunks, so there
is a brief window where both versions are active — which shows slightly
duplicated content. That is a *quality* issue, deduplicated by `document_id`
at rerank time, keeping the higher version.

Separating the two is what makes this tractable. Trying to solve both with one
mechanism is what drives people toward distributed transactions they cannot
have.

Full-index rebuilds are the same pattern one level up: build a timestamped
index alongside the live one, run the eval suite against it, swap the alias
atomically, keep the old index for one rollback window.

## Source connectors

Heterogeneous sources (uploads, wikis, document stores) need one interface,
and the third operation is the one that gets forgotten:

| Operation | Purpose |
|---|---|
| `fetch(uri)` | Retrieve one document's bytes and metadata |
| `list(since?)` | Enumerate the corpus — required for reconciliation and backfill |
| `resolve_acl(uri)` | Authoritative access rule at read time |

Deletions can only be detected for sources you can enumerate. The reconciler
periodically diffs `list()` against index state and removes anything present
in the index but absent from the source. A source that cannot enumerate cannot
be reconciled — refuse to onboard it rather than silently leaving deletions
unhandled.

`list()` also catches the case where a document's **ACL** changed at the source
without any content change.

## Identity and authorization

```
IdentityResolver (pluggable)          Policy (fixed — see ADR 0002)
──────────────────────────            ─────────────────────────────
SSO token    ─┐
API key       ├─→  Principal   ──→    clearance_ok AND group_ok
directory    ─┘   {subject_id,
                   clearance,
                   groups}
```

`IdentityResolver` expands group membership **upward** through any hierarchy at
resolution time, so membership in a child implies membership in its ancestors
but never the reverse. Expanding once at the edge keeps the hot-path filter a
flat set intersection — fast, and far easier for the eval suite to reason
about.

The expanded group set is therefore a **security-critical cached value**. Short
TTL, and the eval suite includes a "caller changed groups" probe, because that
bug only appears in production and only for one person.

## Query path

```
1. Resolve Principal from a verified credential   (server-side only)
2. Expand groups
3. Build immutable SearchContext {principal, acl_filter}
4. Bounded retrieval loop (≤N iterations, token budget)
     tools: search(query) | fetch_document(id, section?) | list_sections(id)
       each search: ~100 candidates with ACL pre-filter on BOTH legs
                    → rerank → top ~10
5. Synthesize answer with citations
6. Groundedness check (separate, cheaper call)
7. Staleness disclosure — computed in code from metadata
```

Three invariants:

**`SearchContext` is closure-captured, never a parameter.** Tools are
constructed per request with the context already bound. No tool exposed to the
model has a `clearance`, `group`, or `principal` field, so an injected
instruction to "search as an administrator" has no parameter to target. The
defense is structural, not a validation check someone must remember to write.

**Retrieved document text is untrusted data.** It is delimited, the system
prompt says so, and tool arguments are validated. But the real defense is that
authorization lives outside the model entirely — the filter already ran.

**Staleness is computed, not inferred.** Document metadata carries
`effective_date` / `expiry_date` / `last_verified`, indexed alongside content.
At answer time the cited documents' dates are checked against now and the
disclosure is injected deterministically. Leaving the model to notice a date
in chunk text means it will sometimes not.

## Deployment

Storage, queueing, and model access are adapters. The default target is a
single-node setup for development; production adapters are opt-in so that
installing Warrant never forces a particular vector store or model provider.

Heavy document processing does not belong in a short-lived function — parsing
and enriching a large PDF exceeds typical serverless duration and image-size
limits. Request-oriented APIs and the ingest-event receiver are small and
latency-sensitive; parsing, chunking, enrichment, embedding, reconciliation,
and rebuilds are long-running workers. The receiver staying small is what lets
ingestion back-pressure through the queue rather than dropping events when
workers saturate.

## What is deliberately not here yet

See the roadmap in [`../README.md`](../README.md). The honest summary: the
authorization core and its probes are real; parsing, retrieval, and answering
are interfaces awaiting implementations.
