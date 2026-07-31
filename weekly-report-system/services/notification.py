"""通知事件服务"""
import json
from database_v2 import get_db, create_notification_event


def on_leader_reject(submission_id, submitter_user_id, reason):
    """Leader 驳回时触发"""
    create_notification_event(
        "leader_reject", submitter_user_id,
        related_submission_id=submission_id,
        payload={
            "reason": reason,
            "submission_id": submission_id,
            "message": f"您的周报已被驳回，原因：{reason}，请修改后重新提交"
        }
    )


def on_superior_interact(file_id, submitter_user_id, interact_type, superior_name):
    """部门领导互动时触发"""
    create_notification_event(
        "superior_interact", submitter_user_id,
        payload={
            "type": interact_type,
            "file_id": file_id,
            "superior": superior_name,
            "message": f"部门领导{superior_name}{'赞了' if interact_type == 'like' else '评论了'}您的文件"
        }
    )


def on_leader_nudge(leader_id, leader_name, member_id):
    """Leader 催交时触发"""
    from database_v2 import get_current_week
    week_start, _ = get_current_week()
    create_notification_event(
        "leader_nudge", member_id,
        payload={
            "leader_id": leader_id,
            "leader_name": leader_name,
            "week_start": week_start,
            "message": f"{leader_name}提醒您尽快提交本周周报"
        }
    )
