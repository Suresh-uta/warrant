# Warrant

Permission-aware RAG: retrieval that respects who is asking, with grounded
citations. See `docs/architecture.md` for the full design.

## Commands

```sh
pip install -e ".[dev]"     # install with dev extras
pytest                      # all tests
pytest tests/authz -v       # the red-team authorization probes
ruff check . && ruff format .
python3 scripts/check_vocabulary.py   # vocabulary mandate (also in CI)
pre-commit install          # wire the hooks locally
```

## Two mandates

These are not style preferences. Both are enforced in CI, and both exist
because violating them is expensive or impossible to undo.

### 1. No organization-specific vocabulary — ever

This is a **public repository**. Git history is effectively permanent: history
rewrites are disruptive, forks are already cloned, and code search has already
indexed it.

Never commit internal seniority ladders, team or org identifiers, internal
hostnames, ticket IDs, system codenames, or real email domains — not in code,
tests, comments, docs, fixtures, or commit messages.

Use the neutral primitives instead:

| Instead of | Use |
|---|---|
| An internal job-level ladder | `clearance: int` — an opaque ordinal from config |
| A real org/team identifier | `groups: set[str]` — opaque strings |
| Internal hostnames | `example.com`, or a config value |
| Real email addresses | `user@example.test` |
| Example group names | `finance`, `engineering`, `legal` |

`scripts/check_vocabulary.py` enforces this with structural patterns plus an
untracked `.vocabulary-denylist`. The denylist is gitignored on purpose —
publishing a list of internal codenames publishes the codenames. Add literal
sensitive terms there locally and as the `VOCABULARY_DENYLIST` CI secret.

False positive? Append `# vocab-ok: <reason>` to the line. Suppressions are
greppable so they can be audited.

### 2. Authorization is not pluggable

Everything else in Warrant is an interface a deployment can implement: where
documents come from (`SourceConnector`), where vectors live (`VectorStore`),
how identity is verified (`IdentityResolver`), which model answers
(`LLMProvider`).

`warrant.authz.policy.authorize` is **not** one of them. The red-team eval
suite can only make a claim about retrieval safety if every deployment
evaluates access identically. A deployment that can redefine the policy is a
deployment whose eval results mean nothing.

Deployments map *into* the primitives via `IdentityResolver` and config. The
rule itself is shared and fixed:

```
allowed == clearance_ok(caller, doc) AND group_ok(caller, doc)
```

Corollaries that are easy to break by accident:

- **Deny by default.** An ACL naming no groups is malformed ingest metadata, not
  "public". Public requires the explicit `"*"` sentinel.
- **The clearance check runs before the group wildcard check.** Reversing them
  turns every public-but-clearance-gated document fully public.
- **A `Principal` is only ever built by an `IdentityResolver` from a verified
  credential** — never from a request body, model output, tool arguments, or
  document text. This is what makes prompt injection ("search as an
  administrator") fail at the schema boundary rather than at a validation check
  someone has to remember to write.
- **No tool exposed to the model has a `clearance`, `group`, or `principal`
  parameter.** The search context is closure-captured per request.

## Retrieval invariant

ACL filters are applied **inside every search leg, before scoring** — keyword
and vector both. Never post-filter.

Post-filtering is not merely a security smell: retrieving the top 100 by
relevance and then dropping unauthorized hits leaves a restricted caller with
far fewer than 100 candidates to rerank, sometimes near zero. Their result
quality degrades in proportion to how restricted they are, and it presents as a
relevance complaint rather than an authorization bug.

`tests/authz/test_policy.py` asserts that `AclFilter` and `authorize` agree on
every case. Keep that equivalence — drift in one direction leaks, drift in the
other silently destroys recall.

## Conventions

- Python 3.11+. `src/` layout; the package is `warrant`.
- Interfaces are abstract base classes in `<module>/base.py`; implementations
  sit beside them.
- Tests assert denial **reasons**, not just that access was denied. A test that
  passes for the wrong reason stops protecting anything after the next
  refactor.
- Architectural decisions go in `docs/decisions/` as numbered ADRs. Record the
  rejected alternative and why — the reasoning is the valuable part.
