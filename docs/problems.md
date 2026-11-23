# What problems Warrant solves

Retrieval is most valuable exactly where documents are sensitive — and that is
exactly where most systems cannot go.

A question-answering system over public documentation is a convenience. One
over your contracts, runbooks, policies, and personnel records would change how
people work. The second is where the value is, and it is usually blocked.

These are the five reasons it gets blocked.

---

## 1. The system searches documents the asker isn't allowed to read

Think of a librarian.

A careless librarian finds the best book for your question, hands it over, and
*then* checks whether you were allowed to read it. Sometimes they catch it.
Sometimes they don't.

A careful librarian only ever looks at the shelves you're allowed to use. The
wrong book is never in their hands in the first place.

Most retrieval systems are the careless librarian: they search everything, rank
everything, and filter at the end — if at all. By that point the restricted text
has passed through a reranker, a model, and a log file.

**Why it stops a project:** someone builds a demo on the company wiki. It works.
Then a reviewer asks what prevents a new hire retrieving an unreleased financial
result, and there is no answer, because access was never part of the design. The
project stalls after the budget is spent.

**The usual workaround makes it worse.** Teams build one index per sensitivity
level. Now knowledge is fragmented, several systems need maintaining, and no
question can span them. More cost, worse product.

**There is also a quality cost that nobody expects.** Filtering after retrieval
starves the ranker: fetch the top 100 by relevance, drop what the caller may not
see, and a restricted user is left with a handful. Their answers get worse in
direct proportion to how restricted they are — and it arrives as a complaint
about search quality, not as a security report.

→ Warrant applies the access filter *inside* the search query, on every leg,
before anything is scored.

---

## 2. Ingestion destroys the document's structure

A document has shape. Headings say which section you are in. Tables pair things
together — this amount goes with this condition. Page numbers say where
something came from.

Most pipelines throw that away. A PDF becomes one long stream of words, cut into
chunks every few hundred characters.

Consider a refund policy containing this table:

| Amount | Who approves |
|---|---|
| Under 100 | Anyone |
| 100–500 | Team lead |
| Over 500 | Manager |

Flatten it into a word stream, cut it mid-table, and the pairings scatter. One
chunk holds `500`. A different chunk holds `Anyone`.

Ask who approves a 500 refund and the system answers **"Anyone."**

It is not hallucinating. It is reading exactly what it was given. The pairing was
destroyed during ingestion and nothing downstream can detect that.

**Why it matters commercially:** a confident wrong answer is worse than no
answer. A missing answer sends someone to look it up. A confident wrong answer
makes someone act — approving what shouldn't be approved, quoting a policy that
says the opposite of what they think.

**It also breaks citations.** Discard headings and page anchors during parsing
and there is nothing left to cite, so no one can check the answer.

→ Warrant parses into structured blocks and chunks along that structure. Tables
stay whole; chunks don't cross section boundaries.

---

## 3. Answers can't be traced back to a source

If a claim cannot be traced to a document, a section, and a page, nobody can
approve a refund on it, sign off on a control with it, or defend a decision made
because of it.

An answer you cannot verify is only safe for questions that did not matter.
Those are not the questions worth building a system for.

→ Every factual claim carries a citation, and a separate check verifies the
answer is actually supported by what was retrieved.

---

## 4. Expired documents answer as confidently as current ones

An agreement that lapsed last quarter. A policy that was superseded. A runbook
for a system that was decommissioned.

The system does not know these went stale, so it answers in the same confident
voice either way. Someone acts on it. That is a financial or legal event, not a
bug report.

→ Documents carry effective and expiry dates. Staleness is computed in code from
that metadata and disclosed in the answer — never left to the model to notice a
date buried in the text.

---

## 5. Nobody can prove it is safe, so it never gets approved

A reviewer asks how you know restricted content cannot leak. The honest answer
is usually that someone tested it by hand, once, months ago.

Without continuous proof, every change is unreviewed risk, and the reviewer's
correct decision is no.

→ Red-team probes run on every commit: insufficient clearance, wrong group,
hierarchy traversal. They assert *why* access was denied, not merely that it
was, so a test cannot quietly start passing for the wrong reason.

---

## Who this is for

Organizations where the useful documents and the sensitive documents are the
same documents, or at least live in the same store. Finance, healthcare, legal,
regulated industries — and in practice, most large companies' internal
knowledge bases.

## What is actually being sold

Not better retrieval.

**The ability to say yes in a security review.**

The permission model, the red-team probes, the citations, and the staleness
disclosure are the four things a reviewer asks for. Having them is the
difference between a pilot and a deployment.

---

For how these are solved, see [`architecture.md`](architecture.md) and the
[diagrams](https://suresh-uta.github.io/warrant/). For what is built so far, see
the roadmap in the [README](../README.md) — the honest answer today is the
authorization core and its probes, with everything else designed and in
progress.
