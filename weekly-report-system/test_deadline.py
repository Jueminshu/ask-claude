"""Test deadline and notification services."""
import sys
import os

# Ensure the parent directory is in the path so database_v2 can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.deadline import get_deadline_info
from services.notification import on_leader_reject, on_superior_interact, on_leader_nudge


def test_get_deadline_info():
    info = get_deadline_info()
    assert "week_start" in info
    assert "is_passed" in info
    assert "deadline" in info
    assert info["deadline"] == "周一 10:00"
    assert info["auto_approve"] == "周一 11:30"
    assert "message" in info
    assert "remaining" in info
    print("get_deadline_info():", info)
    print("PASS")


def test_notification_imports():
    """Verify the three trigger functions exist and are callable."""
    assert callable(on_leader_reject)
    assert callable(on_superior_interact)
    assert callable(on_leader_nudge)
    print("All notification trigger functions are callable")
    print("PASS")


if __name__ == "__main__":
    test_get_deadline_info()
    test_notification_imports()
    print("\nAll tests passed.")
