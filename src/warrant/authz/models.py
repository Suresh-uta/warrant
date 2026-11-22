"""Identity and access-control value types.

These types are deliberately immutable. A ``Principal`` is the only
representation of "who is asking" that the rest of Warrant accepts, and it can
only be built by an ``IdentityResolver`` from a credential the server has
already verified.

It is never constructed from:
  - request body fields
  - model output
  - tool call arguments
  - document content

That restriction is the structural defense against a retrieved document
instructing the model to "search as an administrator": there is no code path
that turns text into a Principal.

Vocabulary
----------
Warrant expresses access with two orthogonal primitives, both opaque to the
engine:

  clearance  an optional ordinal tier (higher == more access)
  groups     an optional set of opaque membership identifiers

Deployments map their own identity system onto these. A company with no
seniority tiers simply never sets ``clearance``. A company whose directory is
purely group-based uses ``groups`` alone. The engine never interprets the
*meaning* of a clearance number or a group name -- only the comparison and the
set intersection.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import FrozenSet, Iterable, Optional

# Explicit sentinel meaning "every group". Must be written deliberately into a
# document's ACL. There is no implicit path to public visibility -- an ACL that
# simply omits groups is denied, not opened (see policy.authorize).
ALL_GROUPS = "*"

HUMAN = "human"
SERVICE = "service"


@dataclass(frozen=True)
class Principal:
    """A verified caller.

    Attributes:
        subject_id: Stable identifier for the caller. Used for audit logs.
        clearance: Ordinal clearance tier, or None if the identity system does
            not express one for this caller (common for service principals).
            A None clearance cannot satisfy any ``min_clearance`` requirement
            -- see policy.authorize.
        groups: The caller's group membership, **already expanded** through any
            group hierarchy by the IdentityResolver. Expanding at resolution
            time keeps the search-time filter a flat set intersection.
        resolved_at: When this Principal was built. Callers that cache
            Principals must treat this as a freshness bound; group membership
            is security-critical state and goes stale when people change teams.
        kind: HUMAN or SERVICE.
    """

    subject_id: str
    clearance: Optional[int]
    groups: FrozenSet[str]
    resolved_at: datetime
    kind: str = HUMAN

    @staticmethod
    def build(
        subject_id: str,
        groups: Iterable[str],
        clearance: Optional[int] = None,
        kind: str = HUMAN,
        resolved_at: Optional[datetime] = None,
    ) -> "Principal":
        if not subject_id:
            raise ValueError("Principal requires a subject_id")
        if kind not in (HUMAN, SERVICE):
            raise ValueError("Principal.kind must be 'human' or 'service'")
        normalized = frozenset(g.strip() for g in groups if g and g.strip())
        return Principal(
            subject_id=subject_id,
            clearance=clearance,
            groups=normalized,
            resolved_at=resolved_at or datetime.now(timezone.utc),
            kind=kind,
        )

    def age_seconds(self, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (now - self.resolved_at).total_seconds()


@dataclass(frozen=True)
class DocumentACL:
    """The access rule attached to a document, and denormalized onto every
    chunk derived from that document.

    ``min_clearance`` and ``allowed_groups`` are an AND condition. A caller
    must clear the clearance bar *and* belong to at least one listed group. A
    high clearance is not a master key.
    """

    min_clearance: Optional[int]
    allowed_groups: FrozenSet[str]

    @staticmethod
    def build(
        allowed_groups: Iterable[str],
        min_clearance: Optional[int] = None,
    ) -> "DocumentACL":
        normalized = frozenset(g.strip() for g in allowed_groups if g and g.strip())
        return DocumentACL(min_clearance=min_clearance, allowed_groups=normalized)

    def is_public(self) -> bool:
        return ALL_GROUPS in self.allowed_groups

    def acl_hash_input(self) -> str:
        """Canonical string form, used to compute the document's acl_hash.

        Sorted so that reordering the group list does not look like a change
        and trigger needless reprocessing.
        """
        clearance = "-" if self.min_clearance is None else str(self.min_clearance)
        return f"clearance={clearance};groups={','.join(sorted(self.allowed_groups))}"


@dataclass(frozen=True)
class Decision:
    """The outcome of an authorization check, with a machine-readable reason.

    The reason exists so that denials are auditable and so that the red-team
    eval suite can assert *why* something was denied, not merely that it was.
    A test that passes because of the wrong denial reason is a test that will
    stop protecting you after the next refactor.
    """

    allowed: bool
    reason: str

    @staticmethod
    def allow(reason: str) -> "Decision":
        return Decision(allowed=True, reason=reason)

    @staticmethod
    def deny(reason: str) -> "Decision":
        return Decision(allowed=False, reason=reason)

    def __bool__(self) -> bool:
        return self.allowed
