"""The authorization policy.

This module is intentionally small, intentionally boring, and intentionally
NOT pluggable.

Every other boundary in Warrant is an interface a deployment can implement:
where documents come from, where vectors live, how identity is verified. The
policy is not, because the red-team eval suite can only make a claim about
retrieval safety if every deployment evaluates access the same way. A
deployment that can redefine ``authorize`` is a deployment whose eval results
mean nothing.

What a deployment *does* control is the mapping into these types: which
credential proves identity, how group hierarchies expand, what integer a
clearance tier corresponds to. That mapping lives in IdentityResolver and in
configuration. The rule below is shared.

The rule
--------
    allowed  ==  clearance_ok(caller, doc)  AND  group_ok(caller, doc)

with deny-by-default on anything malformed or absent.
"""

from .models import ALL_GROUPS, Decision, DocumentACL, Principal

# --- Denial reasons (stable identifiers; assert on these in tests) ----------

DENY_ACL_NAMES_NO_GROUPS = "acl_names_no_groups"
DENY_PRINCIPAL_HAS_NO_GROUPS = "principal_has_no_groups"
DENY_PRINCIPAL_HAS_NO_CLEARANCE = "principal_has_no_clearance"
DENY_CLEARANCE_BELOW_MINIMUM = "clearance_below_minimum"
DENY_NO_GROUP_OVERLAP = "no_group_overlap"

ALLOW_PUBLIC_GROUP_WILDCARD = "clearance_ok_and_group_wildcard"
ALLOW_CLEARANCE_AND_GROUP = "clearance_ok_and_group_overlap"


def authorize(principal: Principal, acl: DocumentACL) -> Decision:
    """Decide whether ``principal`` may see content governed by ``acl``.

    Order matters here for one reason worth stating: the clearance check runs
    before the group wildcard check, so a document marked public
    (groups=["*"]) that also carries a min_clearance is still clearance-gated.
    The wildcard satisfies only the group half of the AND. Reversing these two
    blocks would silently turn every public-but-restricted document into a
    fully public one.
    """
    # Deny by default: an ACL that names no groups is treated as malformed
    # ingest metadata, not as "visible to everyone". An uploader who forgets
    # the field gets an invisible document, never an exposed one.
    if not acl.allowed_groups:
        return Decision.deny(DENY_ACL_NAMES_NO_GROUPS)

    # --- clearance leg -----------------------------------------------------
    if acl.min_clearance is not None:
        if principal.clearance is None:
            # Typically a service principal against a clearance-gated
            # document. Denying is the safe reading: an identity with no
            # expressible clearance has not cleared the bar, so it does not
            # pass.
            return Decision.deny(DENY_PRINCIPAL_HAS_NO_CLEARANCE)
        if principal.clearance < acl.min_clearance:
            return Decision.deny(DENY_CLEARANCE_BELOW_MINIMUM)

    # --- group leg ---------------------------------------------------------
    if ALL_GROUPS in acl.allowed_groups:
        return Decision.allow(ALLOW_PUBLIC_GROUP_WILDCARD)

    if not principal.groups:
        return Decision.deny(DENY_PRINCIPAL_HAS_NO_GROUPS)

    if not (principal.groups & acl.allowed_groups):
        return Decision.deny(DENY_NO_GROUP_OVERLAP)

    return Decision.allow(ALLOW_CLEARANCE_AND_GROUP)


def assert_authorized(principal: Principal, acl: DocumentACL) -> None:
    """Raise if not permitted.

    Used as a belt-and-suspenders check on any path that handles a chunk the
    search filter was supposed to have excluded. If this ever raises in
    production it means a filter was not applied, which is a bug worth paging
    about rather than swallowing: it is the signature of restricted content
    having escaped the search store.
    """
    decision = authorize(principal, acl)
    if not decision.allowed:
        raise PermissionError(
            f"principal={principal.subject_id} denied: {decision.reason}"
        )
