# test_auth.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'weekly-report-system'))
from database_v2 import init_db, seed_data
from services.auth import *

init_db()
seed_data()

def test_member_permissions():
    user = {"role": "member", "module_id": 1, "can_browse_all": 0}
    assert check_page_permission(user, "upload")[0]
    assert check_page_permission(user, "history")[0]
    assert not check_page_permission(user, "review")[0]
    assert not check_page_permission(user, "leader_browse")[0]

def test_leader_permissions():
    user = {"role": "leader", "module_id": 1, "can_browse_all": 0}
    assert check_page_permission(user, "upload")[0]
    assert check_page_permission(user, "review")[0]
    assert not check_page_permission(user, "leader_browse")[0]
    assert check_data_permission(user, "review", target_module_id=1)[0]
    assert not check_data_permission(user, "review", target_module_id=2)[0]

def test_marketing_leader_permissions():
    user = {"role": "leader", "module_id": 2, "can_browse_all": 1}
    assert check_page_permission(user, "leader_browse")[0]
    assert check_data_permission(user, "view_all")[0]

def test_superior_permissions():
    user = {"role": "superior", "module_id": None, "can_browse_all": 0}
    assert check_page_permission(user, "leader_browse")[0]
    assert not check_page_permission(user, "upload")[0]
    assert check_data_permission(user, "interact")[0]
    assert not check_data_permission(user, "review", target_module_id=1)[0]
