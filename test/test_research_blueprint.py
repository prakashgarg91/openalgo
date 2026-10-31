"""The Research page reads one JSON file; its shape must match what the page expects."""

from blueprints import research


def test_the_shipped_results_file_loads_and_has_the_shape_the_page_reads():
    data = research._load_linkage()
    assert data is not None
    for key in ("generated", "meta", "groups", "nodes", "links", "joint_model", "range_model"):
        assert key in data
    ids = {n["id"] for n in data["nodes"]}
    assert {"gap", "intraday", "range", "close_to_close"} <= ids
    statuses = {"verified", "weak", "flipped", "not_selected"}
    assert all(link["status"] in statuses for link in data["links"])
    assert all(link["source"] in ids and link["target"] in ids for link in data["links"])
    group_ids = {g["id"] for g in data["groups"]}
    assert all(n["group"] in group_ids | {"target"} for n in data["nodes"])
    meta = data["meta"]
    assert meta["verified"] == sum(link["status"] == "verified" for link in data["links"])


def test_a_missing_file_gives_none_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "LINKAGE_FILE", tmp_path / "missing.json")
    assert research._load_linkage() is None
