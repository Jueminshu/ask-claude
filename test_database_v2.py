# test_database_v2.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'weekly-report-system'))
from database_v2 import *


def test_init_and_seed():
    init_db()
    seed_data()
    conn = get_db()
    modules = conn.execute("SELECT COUNT(*) as c FROM modules").fetchone()
    assert modules["c"] == 4
    users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()
    assert users["c"] >= 7
    templates = conn.execute("SELECT COUNT(*) as c FROM file_templates").fetchone()
    assert templates["c"] == 16  # 4 modules x 4 templates
    conn.close()


def test_create_submission_and_files():
    init_db()
    sub_id = create_submission(5, 1, "2026-07-27", "2026-08-02")
    assert sub_id > 0
    file_id = add_submission_file(sub_id, "test.xlsx", "/tmp/test.xlsx", "xlsx", 1024)
    assert file_id > 0
    sub = get_submission_with_files(sub_id)
    assert sub is not None
    assert len(sub["files"]) == 1
    assert sub["files"][0]["filename"] == "test.xlsx"


def test_review_flow():
    init_db()
    sub_id = create_submission(5, 1, "2026-07-27", "2026-08-02")
    approve_submission(sub_id, 3)  # reviewer=leader_domestic
    conn = get_db()
    sub = conn.execute("SELECT * FROM submissions WHERE id = ?", (sub_id,)).fetchone()
    assert sub["status"] == "leader_approved"
    log = conn.execute("SELECT * FROM review_log WHERE submission_id = ?", (sub_id,)).fetchone()
    assert log["action"] == "approve"
    conn.close()


def test_interactions():
    init_db()
    sub_id = create_submission(5, 1, "2026-07-27", "2026-08-02")
    file_id = add_submission_file(sub_id, "test.xlsx", "/tmp/test.xlsx", "xlsx", 1024)
    ok, _ = add_interaction(file_id, 2, "like")  # user 2 = superior
    assert ok
    ok, _ = add_interaction(file_id, 2, "like")  # duplicate
    assert not ok
    interactions = get_file_interactions(file_id)
    assert interactions["likes_count"] == 1
