# ADR 0002 — Authorization is not pluggable

**Status:** accepted · **Date:** 2026-11-21

## Context

Warrant is built to be extended. Document sources, vector stores, identity
providers, and model providers are all interfaces, because no single choice
suits every deployment.

The obvious next step is to make the access policy pluggable too — every
organization has its own rules, so let them supply the rule.

## Decision

`warrant.authz.policy.authorize` is fixed and shared by every deployment:

```
allowed == clearance_ok(caller, doc) AND group_ok(caller, doc)
```

Deployments control the *mapping into* the primitives via `IdentityResolver`
and configuration. They do not control the rule.

## Rationale

The red-team eval suite is Warrant's central safety claim. It can only make
that claim if every deployment evaluates access identically. A deployment that
can redefine the policy is a deployment whose eval results mean nothing — the
suite would be testing a rule nobody is actually running.

A pluggable policy also moves the most security-critical code in the project
from one well-reviewed, well-tested implementation to N implementations written
under deadline by people who are not primarily thinking about authorization.
That is the exact defect the project exists to prevent, relocated rather than
solved.

## Alternatives rejected

**A policy hook or strategy parameter.** Same problem; the escape hatch is the
problem.

**A policy DSL.** More expressive, and now the project owns a language plus its
evaluator plus its own injection surface — with the eval suite still unable to
reason about arbitrary policies.

**Expose the primitives only, with no opinion about combining them.** This was
genuinely tempting. Rejected because the AND is the security property: letting
deployments choose OR reintroduces "a sufficiently senior caller sees
everything", which is the single most common real-world access bug in this
space.

## Consequences

- Deployments whose rules don't fit `clearance AND groups` must either model
  their rules into those primitives or propose a change to the shared rule.
  That friction is intentional.
- Policy changes are breaking changes for everyone, so they need an ADR and a
  version bump.
- The red-team probes transfer unchanged to every deployment, which is the
  entire point.
