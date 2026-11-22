"""Translating a Principal into a search-store filter.

Why this is its own module
--------------------------
``policy.authorize`` answers "may this caller see this one chunk?". That is the
right question for an audit check, but it is the wrong question for retrieval,
because it can only be asked about content you have already retrieved.

Retrieval needs the inverse: a predicate the search store can apply *before*
scoring, so unauthorized chunks are never candidates in the first place.

The two must agree. A chunk that ``authorize`` would deny must also be excluded
by ``AclFilter``, and vice versa. ``tests/authz`` asserts that equivalence
directly, because a drift between them is the exact bug class this design
exists to prevent: a filter that is subtly more permissive than the policy
leaks, and one that is subtly more restrictive silently destroys recall.

Why pre-filter, not post-filter
-------------------------------
It is tempting to retrieve the top-k by relevance and then drop whatever the
caller may not see. Do not do this. In a vector leg, post-filtering k=100
candidates leaves a restricted caller with far fewer than 100 to rerank --
sometimes near zero -- so their result quality degrades in proportion to how
restricted they are. The failure presents as a relevance complaint and is
actually an architecture bug. Every adapter MUST apply this filter inside the
query, on every leg (keyword and vector), before scoring.
"""

from dataclasses import dataclass
from typing import FrozenSet, Optional

from .models import ALL_GROUPS, Principal


@dataclass(frozen=True)
class AclFilter:
    """A store-agnostic description of the access predicate for one caller.

    Adapters translate this into their own query language. The predicate is:

        (chunk.min_clearance IS NULL OR chunk.min_clearance <= clearance_ceiling)
        AND
        (chunk.allowed_groups INTERSECTS group_terms)

    Attributes:
        clearance_ceiling: The caller's clearance, or None when the caller has
            none. When None, chunks carrying any ``min_clearance`` at all must
            be excluded -- matching policy.authorize, which denies a
            clearance-less principal against a clearance-gated document.
        group_terms: The caller's expanded groups, plus the public wildcard.
            Non-empty by construction (the wildcard is always present), so the
            intersection clause is always well-formed.
    """

    clearance_ceiling: Optional[int]
    group_terms: FrozenSet[str]

    @property
    def excludes_all_clearance_gated(self) -> bool:
        """True when no clearance-gated chunk may match.

        Adapters must honor this rather than treating a None ceiling as
        'unbounded'. Reading None as 'no limit' inverts the policy and is the
        single most dangerous translation mistake available here.
        """
        return self.clearance_ceiling is None


def acl_filter_for(principal: Principal) -> AclFilter:
    """Build the retrieval filter for a verified caller.

    Takes a Principal rather than loose arguments on purpose: there is no way
    to call this with a clearance or group set that did not come from the
    identity resolver.
    """
    return AclFilter(
        clearance_ceiling=principal.clearance,
        group_terms=frozenset(principal.groups | {ALL_GROUPS}),
    )
