# Contributing to Warrant

## Setup

```sh
pip install -e ".[dev]"
pre-commit install
pytest
```

Python 3.11+ is required.

## Two mandates

Both are enforced in CI and neither is negotiable in review. They exist
because violating them is expensive or impossible to undo.

### 1. No organization-specific vocabulary

This is a public repository, and git history is effectively permanent —
rewriting it is disruptive, forks are already cloned, and code search has
already indexed the content. A leak here cannot be fixed by a follow-up commit.

Access-control code is unusually prone to this, because the natural way to
write it is to encode whichever organization it was first built for.

**Never commit:** internal seniority ladders, real team or org identifiers,
internal hostnames, ticket IDs, system codenames, or real email domains. Not in
code, tests, comments, docs, fixtures, example config, or commit messages.

**Use the neutral primitives:**

| Instead of | Use |
|---|---|
| An internal job-level ladder | `clearance: int` — an opaque ordinal from config |
| A real org or team identifier | `groups: set[str]` — opaque strings |
| Internal hostnames | `example.com`, or a config value |
| Real email addresses | `user@example.test` |
| Example group names | `finance`, `engineering`, `legal` |

#### How it's enforced

`scripts/check_vocabulary.py` runs in pre-commit and CI. It has two layers:

1. **Structural patterns**, committed in the script. These match the *shape* of
   internal vocabulary without naming any organization, so the checker itself
   leaks nothing.

2. **A local denylist** at `.vocabulary-denylist`, which is **gitignored on
   purpose**. Put literal terms there that must never escape.

That second point is the one people get backwards: a committed denylist of
internal codenames *publishes the codenames*. Keeping it untracked means the
list of what you're protecting isn't itself published. In CI, provide it as the
`VOCABULARY_DENYLIST` repository secret; the workflow writes it to disk before
scanning, and the script prints `<redacted>` rather than echoing a matched term
into public build logs.

```sh
cp .vocabulary-denylist.example .vocabulary-denylist   # then edit locally
python3 scripts/check_vocabulary.py
```

Genuine false positive? Append `# vocab-ok: <reason>` to the line.
Suppressions are greppable so they can be audited.

### 2. Authorization stays non-pluggable

Everything else here is an interface: `SourceConnector`, `VectorStore`,
`IdentityResolver`, `LLMProvider`. Implement whatever you need.

`warrant.authz.policy.authorize` is different. The red-team suite can only
make a claim about retrieval safety if every deployment evaluates access
identically — a deployment that can redefine the policy is one whose eval
results mean nothing.

Map *into* the primitives via `IdentityResolver` and configuration. Don't add
a hook, a strategy parameter, or a subclass point to the policy itself.

If you believe the rule is genuinely wrong or insufficient, that's a
conversation worth having — open an issue proposing a change to the shared
rule. Adding an escape hatch is not the answer.

## Changes that touch authorization or retrieval filtering

Extra care, because the failure mode is silent:

- `tests/authz/test_policy.py` asserts that `AclFilter` and `authorize` agree
  on every case. Keep that equivalence. Drift one way leaks content; drift the
  other silently destroys recall for restricted users.
- Tests assert denial **reasons**, not just that access was denied. A test
  passing for the wrong reason stops protecting anything after the next
  refactor.
- New store adapters must apply the ACL filter **inside the query, on every
  leg, before scoring**. Post-filtering is not acceptable even when it appears
  to work — see `src/warrant/authz/filters.py` for why it degrades recall in
  proportion to how restricted a caller is.
- Adding a tool the model can call? It must not have a `clearance`, `group`, or
  `principal` parameter. Bind the search context per request instead.

## Architectural decisions

Significant decisions go in `docs/decisions/` as numbered ADRs. Record the
alternative you rejected and why — six months later the reasoning is the part
nobody can reconstruct.

## Commit and PR style

- Present tense, imperative: "add staleness disclosure", not "added".
- Say *why* in the body when the change isn't self-evident.
- Keep PRs scoped to one concern.
