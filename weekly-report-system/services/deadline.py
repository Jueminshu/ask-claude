"""截止时间服务"""
from datetime import datetime, timedelta


def get_deadline_info():
    """
    获取当前周的截止信息。

    返回: {
        'week_start': str,
        'week_end': str,
        'deadline': '周一 10:00',
        'auto_approve': '周一 11:30',
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

    # 截止时间: 本周一 10:00
    deadline = monday.replace(hour=10, minute=0, second=0, microsecond=0)
    auto_approve = monday.replace(hour=11, minute=30, second=0, microsecond=0)

    is_passed = now > deadline
    remaining = None
    message = ""

    if weekday == 0:  # 周一
        if now < deadline:
            delta = deadline - now
            hours = delta.seconds // 3600
            mins = (delta.seconds % 3600) // 60
            remaining = f"{hours}小时{mins}分钟"
            message = f"请在周一 10:00 前提交周报（剩余 {remaining}）"
        elif now < auto_approve:
            delta = auto_approve - now
            mins = delta.seconds // 60
            remaining = f"{mins}分钟"
            message = "提交已截止，Leader 审核中"
        else:
            message = "本周审核已结束，部门领导可查阅"
            is_passed = True
    elif weekday >= 1:  # 周二及以后
        if weekday == 1 and now.hour < 12:  # 周二中午前
            message = "本周审核已完成，部门领导可查阅"
        elif now < monday + timedelta(days=7):
            message = "本周提交已截止"
        is_passed = True

    return {
        "week_start": monday.strftime("%Y-%m-%d"),
        "week_end": sunday.strftime("%Y-%m-%d"),
        "deadline": "周一 10:00",
        "auto_approve": "周一 11:30",
        "is_passed": is_passed,
        "message": message,
        "remaining": remaining,
    }
