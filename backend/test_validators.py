"""
Tests for the clusters.json schema validator.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from validators import validate_clusters


# ─── Helpers ──────────────────────────────────────────────

def _valid_cluster(**overrides):
    """Return a single valid cluster dict, with optional overrides."""
    base = {
        "suggested_service": "utils",
        "community_id": 42,
        "size": 2,
        "members": [
            {"function": "utils.diff.apply_diff", "module": "utils.diff"},
            {"function": "utils.diff.create_diff", "module": "utils.diff"},
        ],
    }
    base.update(overrides)
    return base


def _valid_clusters(**overrides):
    """Return a minimal valid clusters dict."""
    return {"cluster_0": _valid_cluster(**overrides)}


# ─── Happy Path ──────────────────────────────────────────

class TestValidClusters:

    def test_valid_single_cluster_passes(self):
        data = _valid_clusters()
        result = validate_clusters(data)
        assert result is data  # same object, pass-through

    def test_valid_multiple_clusters(self):
        data = {
            "cluster_0": _valid_cluster(),
            "cluster_1": _valid_cluster(community_id=99, suggested_service="auth"),
        }
        assert validate_clusters(data) is data

    def test_cluster_with_one_member(self):
        data = {
            "cluster_0": {
                "suggested_service": "auth",
                "community_id": 1,
                "size": 1,
                "members": [{"function": "auth.login", "module": "auth"}],
            }
        }
        assert validate_clusters(data) is data


# ─── Top-Level Errors ────────────────────────────────────

class TestTopLevelErrors:

    def test_not_a_dict(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            validate_clusters([1, 2, 3])

    def test_empty_dict(self):
        with pytest.raises(ValueError, match="empty"):
            validate_clusters({})


# ─── Missing / Wrong-Type Fields ─────────────────────────

class TestFieldErrors:

    @pytest.mark.parametrize("missing_field", [
        "suggested_service", "community_id", "size", "members",
    ])
    def test_missing_required_field(self, missing_field):
        cluster = _valid_cluster()
        del cluster[missing_field]
        with pytest.raises(ValueError, match=f"missing required field '{missing_field}'"):
            validate_clusters({"cluster_0": cluster})

    def test_suggested_service_wrong_type(self):
        with pytest.raises(ValueError, match="suggested_service.*expected str"):
            validate_clusters(_valid_clusters(suggested_service=123))

    def test_community_id_wrong_type(self):
        with pytest.raises(ValueError, match="community_id.*expected int"):
            validate_clusters(_valid_clusters(community_id="not_an_int"))

    def test_size_wrong_type(self):
        with pytest.raises(ValueError, match="size.*expected int"):
            validate_clusters(_valid_clusters(size="two"))

    def test_members_wrong_type(self):
        with pytest.raises(ValueError, match="members.*expected list"):
            validate_clusters(_valid_clusters(members="not_a_list"))


# ─── Size Mismatch ───────────────────────────────────────

class TestSizeMismatch:

    def test_size_too_large(self):
        with pytest.raises(ValueError, match="'size' says 10 but 'members' has 2"):
            validate_clusters(_valid_clusters(size=10))

    def test_size_too_small(self):
        with pytest.raises(ValueError, match="'size' says 1 but 'members' has 2"):
            validate_clusters(_valid_clusters(size=1))


# ─── Member Validation ───────────────────────────────────

class TestMemberErrors:

    def test_member_not_a_dict(self):
        data = _valid_clusters()
        data["cluster_0"]["members"][0] = "not_a_dict"
        with pytest.raises(ValueError, match="members\\[0\\].*expected a dict"):
            validate_clusters(data)

    def test_member_missing_function(self):
        data = _valid_clusters()
        del data["cluster_0"]["members"][0]["function"]
        with pytest.raises(ValueError, match="missing required field 'function'"):
            validate_clusters(data)

    def test_member_missing_module(self):
        data = _valid_clusters()
        del data["cluster_0"]["members"][0]["module"]
        with pytest.raises(ValueError, match="missing required field 'module'"):
            validate_clusters(data)

    def test_member_function_wrong_type(self):
        data = _valid_clusters()
        data["cluster_0"]["members"][0]["function"] = 999
        with pytest.raises(ValueError, match="function.*expected str"):
            validate_clusters(data)

    def test_member_module_wrong_type(self):
        data = _valid_clusters()
        data["cluster_0"]["members"][0]["module"] = None
        with pytest.raises(ValueError, match="module.*expected str"):
            validate_clusters(data)

    def test_cluster_value_not_dict(self):
        with pytest.raises(ValueError, match="expected a dict"):
            validate_clusters({"cluster_0": "not a dict"})
