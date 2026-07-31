"""角色权限服务"""
from database_v2 import get_db

# 角色中文标签
ROLE_LABELS = {
    "admin": "🔧 管理员",
    "leader": "👤 团队负责人",
    "member": "👤 成员",
    "superior": "👔 部门领导",
}

# 页面 → 允许的角色
PAGE_PERMISSIONS = {
    "upload": ["member", "leader"],
    "history": ["member", "leader"],
    "team_view": ["leader"],
    "review": ["leader"],
    "leader_browse": ["superior"],  # 部门领导 + 营销运营部 Leader 特殊处理
    "admin": ["admin"],
}


def can_browse_all_modules(user):
    """是否可查看所有模块周报"""
    return user["role"] == "superior" or user.get("can_browse_all") == 1


def can_browse_module(user, module_id):
    """是否可查看指定模块"""
    if can_browse_all_modules(user):
        return True
    return user.get("module_id") == module_id


def check_page_permission(user, page):
    """
    检查用户是否有某页面权限。

    page: 'upload' | 'history' | 'team_view' | 'review' | 'leader_browse' | 'admin'

    返回: (allowed: bool, reason: str)
    """
    role = user["role"]
    allowed_roles = PAGE_PERMISSIONS.get(page, [])

    if role == "admin" and page != "leader_browse":
        return True, "ok"

    if role in allowed_roles:
        return True, "ok"

    # 营销运营部 Leader 额外权限
    if page == "leader_browse" and role == "leader" and user.get("can_browse_all") == 1:
        return True, "ok"

    return False, f"角色 {role} 无权访问页面 {page}"


def check_data_permission(user, action, target_module_id=None):
    """
    检查数据操作权限。

    action: 'view_own' | 'view_team' | 'view_all' | 'review' | 'interact' | 'manage'

    返回: (allowed: bool, reason: str)
    """
    role = user["role"]

    if action == "view_own":
        return True, "ok"

    if action == "view_team":
        if role in ("leader",):
            return can_browse_module(user, target_module_id), "无权查看该模块"
        return can_browse_all_modules(user), "无权查看团队周报"

    if action == "view_all":
        return can_browse_all_modules(user), "无权查看所有模块"

    if action == "review":
        if role != "leader":
            return False, "仅团队负责人可审核"
        return can_browse_module(user, target_module_id), "无权审核该模块"

    if action == "interact":
        return role == "superior", "仅部门领导可互动"

    if action == "manage":
        return role == "admin", "仅管理员可系统管理"

    return False, f"未知操作: {action}"


def get_user_accessible_modules(user):
    """获取用户可访问的模块列表"""
    conn = get_db()
    if can_browse_all_modules(user):
        modules = conn.execute("SELECT * FROM modules ORDER BY id").fetchall()
    elif user.get("module_id"):
        modules = conn.execute(
            "SELECT * FROM modules WHERE id = ?", (user["module_id"],)
        ).fetchall()
    else:
        modules = []
    conn.close()
    return [dict(m) for m in modules]
