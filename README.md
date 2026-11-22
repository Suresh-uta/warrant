# Warrant

**Retrieval that respects who's asking.** Permission-aware RAG with grounded citations.

> Status: pre-alpha. The authorization core and its red-team test suite are
> implemented. Parsing, retrieval, and answering are scaffolded interfaces.
> See [Roadmap](#roadmap).

Most RAG frameworks assume every document is equally readable by every user.
That assumption holds for a public docs site and breaks the moment you point
the same pipeline at a document store where some things are restricted — which
is where most internal RAG pilots quietly die.

Warrant treats access control as a retrieval concern rather than a
post-processing step, and treats "did we leak anything?" as a test you run on
every change rather than a question you answer in a review.

## What makes it different

- **Filters applied inside every search leg, before scoring.** Keyword and
  vector both. Restricted content is never a candidate, never reaches a
  reranker, never reaches a model.
- **A fixed authorization policy, not a pluggable one.** Identity resolution is
  yours; the access rule is shared, so eval results actually mean something.
- **Red-team probes on every run.** Insufficient clearance, wrong group,
  hierarchy traversal — asserted as tests, with the denial *reason* checked.
- **Citations as a contract.** Every factual claim traceable to document,
  section, and page.
- **Staleness disclosed, not inferred.** Expired sources are flagged from
  metadata in code, never left to the model to notice.

## The access model

Two orthogonal primitives, both opaque to the engine:

```yaml
access:
  min_clearance: 3                      # optional ordinal tier
  allowed_groups: [finance, legal]      # caller needs at least one
```

They are an **AND**. A caller must clear the tier *and* belong to a listed
group — high clearance is not a master key.

```python
from warrant.authz import DocumentACL, Principal, authorize

caller = Principal.build("user@example.test", groups={"engineering"}, clearance=9)
acl = DocumentACL.build(allowed_groups={"finance"}, min_clearance=3)

authorize(caller, acl)
# Decision(allowed=False, reason='no_group_overlap')
```

Your organization maps its own identity system onto these via an
`IdentityResolver`. No seniority tiers? Never set `min_clearance`. Purely
group-based directory? Use `allowed_groups` alone.

Public is **explicit**: `allowed_groups: ["*"]`. An ACL naming no groups is
treated as malformed metadata and denied, so an uploader who forgets the field
gets an invisible document rather than an exposed one.

## Quickstart

Not yet runnable end to end — the ingest and query paths are the next
milestones. What works today:

```sh
git clone https://github.com/OWNER/warrant && cd warrant
pip install -e ".[dev]"
pytest tests/authz -v        # the red-team probes
```

## Architecture

```
ingest                                  query
──────                                  ─────
SourceConnector                         IdentityResolver
  fetch / list / resolve_acl              → Principal (verified, server-side)
       │                                       │
       ▼                                       ▼
  parse → blocks        (structure kept)   AclFilter
       │                                       │
       ▼                                       ▼
  chunk                 (tables atomic)   hybrid search ── keyword leg ─┐
       │                                   (filter applied            ├─→ rerank
       ▼                                    inside BOTH legs,         │
  enrich                (context prepended) before scoring) ─ vector ─┘
       │                                       │
       ▼                                       ▼
  embed → VectorStore ◄──── same store ──► answer + citations
                                               │
                                               ▼
                                     groundedness + staleness
```

Each ingest stage is cached under its own key
(`content_hash + stage_config_hash`), so swapping the embedding model re-runs
only embedding, and editing one document reprocesses only that document.

**Diagrams: [suresh-uta.github.io/warrant](https://suresh-uta.github.io/warrant/)** — system
overview, the access rule, pre-filter vs post-filter, write-path ordering, and
the AWS deployment.

Full design in prose: [`docs/architecture.md`](docs/architecture.md).
Decisions and their rejected alternatives: [`docs/decisions/`](docs/decisions/).

## Roadmap

**v0.1 — a working, honest core**
- [x] Authorization policy + red-team probes
- [ ] Structure-preserving parsing (PDF, DOCX, Markdown); tables stay atomic
- [ ] Structure-aware chunking that respects section boundaries
- [ ] Hybrid keyword + vector retrieval with pre-filtered ACLs on both legs
- [ ] Cited answers
- [ ] `warrant eval` harness, permission probes included

**v0.2 — quality**
- [ ] Contextual enrichment (per-chunk context, cached per document)
- [ ] Reranking — retrieve ~100, keep the best ~10
- [ ] Staleness disclosure from document metadata

**v0.3 — operations**
- [ ] Incremental reprocessing; only changed documents and affected stages
- [ ] Zero-downtime reindex via alias swap, gated on eval results
- [ ] Source reconciliation so deletions actually disappear
- [ ] Bounded multi-hop retrieval loop

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) first — there are two hard mandates
(no organization-specific vocabulary; authorization stays non-pluggable), both
enforced in CI.

## License

MIT. See [`LICENSE`](LICENSE).
