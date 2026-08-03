"""截止时间服务"""
from datetime import datetime, timedelta
from database_v2 import get_db


def _get_module_deadline(module_id):
    """从数据库读取模块截止配置。deadline_day 为 0-based (0=周一)。
       返回 (deadline_day, deadline_time, auto_approve_time)"""
    if module_id is None:
        return 0, "10:00", "11:30"  # 默认周一 10:00
    conn = get_db()
    m = conn.execute(
        "SELECT deadline_day, deadline_time, auto_approve_time FROM modules WHERE id = ?",
        (module_id,)
    ).fetchone()
    conn.close()
    if m:
        return m["deadline_day"], m["deadline_time"], m["auto_approve_time"]
    return 0, "10:00", "11:30"


def get_deadline_info(module_id=None):
    """
    获取当前周的截止信息。

    Args:
        module_id: 模块 ID，为 None 时使用默认值（周一 10:00）

    返回: {
        'week_start': str,
        'week_end': str,
        'deadline': str,
        'auto_approve': str,
        'is_passed': bool,
        'message': str,
        'remaining': str or None,
    }
    """
    now = datetime.now()
    weekday = now.weekday()  # 0=周一

    # 计算本周一
    monday = now - timedelta(days=weekday)
    sunday = monday + timedelta(days=6)

    # 从数据库读取模块截止配置
    dl_day, dl_time, auto_time = _get_module_deadline(module_id)
    dl_hour, dl_minute = map(int, dl_time.split(":"))
    auto_hour, auto_minute = map(int, auto_time.split(":"))

    deadline = monday.replace(hour=dl_hour, minute=dl_minute, second=0, microsecond=0)
    if dl_day != 0:
        deadline = monday + timedelta(days=dl_day)
        deadline = deadline.replace(hour=dl_hour, minute=dl_minute, second=0, microsecond=0)

    auto_approve = monday.replace(hour=auto_hour, minute=auto_minute, second=0, microsecond=0)

    # 格式化截止时间描述
    day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    deadline_label = f"{day_names[dl_day]} {dl_time}"
    auto_label = f"{day_names[0] if auto_hour < 13 else day_names[dl_day]} {auto_time}"

    is_passed = now > deadline
    remaining = None
    message = ""

    if now < deadline:
        delta = deadline - now
        hours = delta.seconds // 3600 + delta.days * 24
        mins = (delta.seconds % 3600) // 60
        remaining = f"{hours}小时{mins}分钟"
        message = f"请在 {deadline_label} 前提交周报（剩余 {remaining}）"
    elif now < auto_approve:
        delta = auto_approve - now
        mins = delta.seconds // 60
        remaining = f"{mins}分钟"
        message = "提交已截止，Leader 审核中"
        is_passed = True
    else:
        message = "本周审核已结束，部门领导可查阅"
        is_passed = True

    return {
        "week_start": monday.strftime("%Y-%m-%d"),
        "week_end": sunday.strftime("%Y-%m-%d"),
        "deadline": deadline_label,
        "auto_approve": auto_label,
        "is_passed": is_passed,
        "message": message,
        "remaining": remaining,
    }


def check_deadline_passed(module_id=None):
    """检查是否已过截止时间。返回 (is_passed: bool, message: str)"""
    info = get_deadline_info(module_id)
    return info["is_passed"], info["message"]
