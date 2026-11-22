"""Red-team probes for the authorization policy.

These are not ordinary unit tests. They are the evidence that Warrant's central
safety claim holds, and they are expected to run on every change -- not only
when someone touches the authz package.

Each test asserts the denial *reason*, not merely that access was denied. A
test that passes for the wrong reason stops protecting you the moment someone
refactors, and silent protection loss is the failure mode this suite exists to
prevent.
"""

import pytest

from warrant.authz import (
    ALL_GROUPS,
    SERVICE,
    DocumentACL,
    Principal,
    acl_filter_for,
    authorize,
)
from warrant.authz.policy import (
    ALLOW_CLEARANCE_AND_GROUP,
    ALLOW_PUBLIC_GROUP_WILDCARD,
    DENY_ACL_NAMES_NO_GROUPS,
    DENY_CLEARANCE_BELOW_MINIMUM,
    DENY_NO_GROUP_OVERLAP,
    DENY_PRINCIPAL_HAS_NO_CLEARANCE,
    DENY_PRINCIPAL_HAS_NO_GROUPS,
)


def principal(groups=("engineering",), clearance=5, **kw):
    return Principal.build("user@example.test", groups=groups, clearance=clearance, **kw)


def acl(groups=("engineering",), clearance=None):
    return DocumentACL.build(allowed_groups=groups, min_clearance=clearance)


# --- The happy path --------------------------------------------------------


def test_matching_group_and_sufficient_clearance_is_allowed():
    d = authorize(principal(groups=["finance"], clearance=5), acl(["finance"], 3))
    assert d.allowed
    assert d.reason == ALLOW_CLEARANCE_AND_GROUP


def test_no_clearance_requirement_needs_only_group_membership():
    d = authorize(principal(groups=["finance"], clearance=None), acl(["finance"]))
    assert d.allowed


# --- Probe 1: insufficient clearance, correct group ------------------------


def test_clearance_below_minimum_is_denied_despite_correct_group():
    d = authorize(principal(groups=["finance"], clearance=2), acl(["finance"], 7))
    assert not d.allowed
    assert d.reason == DENY_CLEARANCE_BELOW_MINIMUM


# --- Probe 2: high clearance, wrong group ----------------------------------
# The headline case. Clearance is not a master key; the two legs are an AND.


def test_high_clearance_does_not_override_group_membership():
    d = authorize(principal(groups=["engineering"], clearance=99), acl(["executive", "people-ops"], 7))
    assert not d.allowed
    assert d.reason == DENY_NO_GROUP_OVERLAP


# --- Probe 3: group hierarchy ----------------------------------------------
# The resolver expands a caller's groups *upward*, so membership in a child
# implies membership in its ancestors -- but never the reverse.


def test_child_group_member_may_read_parent_group_document():
    caller = principal(groups=["finance-treasury", "finance"], clearance=5)
    d = authorize(caller, acl(["finance"], 3))
    assert d.allowed


def test_parent_group_member_may_not_read_child_group_document():
    caller = principal(groups=["finance"], clearance=5)
    d = authorize(caller, acl(["finance-treasury"], 3))
    assert not d.allowed
    assert d.reason == DENY_NO_GROUP_OVERLAP


# --- Deny by default -------------------------------------------------------


def test_acl_naming_no_groups_is_denied_not_public():
    d = authorize(principal(clearance=99), acl(groups=[]))
    assert not d.allowed
    assert d.reason == DENY_ACL_NAMES_NO_GROUPS


def test_principal_with_no_groups_is_denied():
    d = authorize(principal(groups=[], clearance=99), acl(["finance"]))
    assert not d.allowed
    assert d.reason == DENY_PRINCIPAL_HAS_NO_GROUPS


# --- The public wildcard is explicit, and still clearance-gated ------------


def test_wildcard_group_is_allowed():
    d = authorize(principal(groups=["anything"]), acl([ALL_GROUPS]))
    assert d.allowed
    assert d.reason == ALLOW_PUBLIC_GROUP_WILDCARD


def test_wildcard_group_does_not_bypass_clearance():
    """Regression guard: if someone reorders the checks in authorize() so the
    wildcard is tested first, every public-but-restricted document silently
    becomes fully public. This test is the tripwire for that edit."""
    d = authorize(principal(clearance=1), acl([ALL_GROUPS], 9))
    assert not d.allowed
    assert d.reason == DENY_CLEARANCE_BELOW_MINIMUM


# --- Service principals ----------------------------------------------------


def test_service_principal_without_clearance_cannot_read_clearance_gated_doc():
    caller = Principal.build("svc-indexer", groups=["platform"], clearance=None, kind=SERVICE)
    d = authorize(caller, acl(["platform"], 3))
    assert not d.allowed
    assert d.reason == DENY_PRINCIPAL_HAS_NO_CLEARANCE


def test_service_principal_may_read_ungated_doc_in_its_group():
    caller = Principal.build("svc-indexer", groups=["platform"], clearance=None, kind=SERVICE)
    assert authorize(caller, acl(["platform"])).allowed


# --- Filter / policy equivalence -------------------------------------------
# The retrieval filter and the policy must agree on every case. Drift between
# them either leaks content or silently destroys recall for restricted users.

CASES = [
    (principal(groups=["finance"], clearance=5), acl(["finance"], 3)),
    (principal(groups=["finance"], clearance=2), acl(["finance"], 7)),
    (principal(groups=["engineering"], clearance=99), acl(["executive"], 7)),
    (principal(groups=["finance-treasury", "finance"], clearance=5), acl(["finance"])),
    (principal(groups=["finance"], clearance=5), acl(["finance-treasury"])),
    (principal(groups=["x"], clearance=None), acl(["x"], 3)),
    (principal(groups=["x"], clearance=4), acl([ALL_GROUPS])),
    (principal(groups=["x"], clearance=1), acl([ALL_GROUPS], 9)),
]


def filter_admits(f, document_acl) -> bool:
    """Reference implementation of what every store adapter must enforce."""
    if document_acl.min_clearance is not None:
        if f.excludes_all_clearance_gated:
            return False
        if document_acl.min_clearance > f.clearance_ceiling:
            return False
    return bool(document_acl.allowed_groups & f.group_terms)


@pytest.mark.parametrize("caller,document_acl", CASES)
def test_filter_matches_policy(caller, document_acl):
    expected = authorize(caller, document_acl).allowed
    actual = filter_admits(acl_filter_for(caller), document_acl)
    assert actual == expected, (
        "AclFilter and policy.authorize disagree. One of them leaks or one of "
        "them silently drops authorized results."
    )
