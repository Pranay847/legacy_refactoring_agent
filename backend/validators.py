def validate_clusters(data: dict) -> dict:
    """
    Validate that `data` conforms to the expected clusters.json schema:

        {
          "cluster_0": {
            "suggested_service": "utils",
            "community_id": 90,
            "size": 4,
            "members": [
              {"function": "utils.diff.apply_diff_suggestion", "module": "utils.diff"},
              ...
            ]
          },
          ...
        }

    Returns the data unchanged on success (pass-through for chaining).
    Raises ValueError with a descriptive message on failure.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"clusters.json must be a JSON object (dict), got {type(data).__name__}"
        )

    if not data:
        raise ValueError("clusters.json is empty — no clusters found")

    for cluster_key, cluster in data.items():
        _prefix = f"clusters['{cluster_key}']"

        if not isinstance(cluster, dict):
            raise ValueError(
                f"{_prefix}: expected a dict, got {type(cluster).__name__}"
            )

        # --- Required top-level fields ---
        required_fields = {
            "suggested_service": str,
            "community_id": int,
            "size": int,
            "members": list,
        }

        for field, expected_type in required_fields.items():
            if field not in cluster:
                raise ValueError(f"{_prefix}: missing required field '{field}'")
            if not isinstance(cluster[field], expected_type):
                raise ValueError(
                    f"{_prefix}.{field}: expected {expected_type.__name__}, "
                    f"got {type(cluster[field]).__name__}"
                )

        # --- Validate size matches member count ---
        actual_size = len(cluster["members"])
        declared_size = cluster["size"]
        if actual_size != declared_size:
            raise ValueError(
                f"{_prefix}: 'size' says {declared_size} but 'members' has "
                f"{actual_size} entries"
            )

        # --- Validate each member ---
        for i, member in enumerate(cluster["members"]):
            _mprefix = f"{_prefix}.members[{i}]"

            if not isinstance(member, dict):
                raise ValueError(
                    f"{_mprefix}: expected a dict, got {type(member).__name__}"
                )

            for member_field in ("function", "module"):
                if member_field not in member:
                    raise ValueError(
                        f"{_mprefix}: missing required field '{member_field}'"
                    )
                if not isinstance(member[member_field], str):
                    raise ValueError(
                        f"{_mprefix}.{member_field}: expected str, "
                        f"got {type(member[member_field]).__name__}"
                    )

    return data
