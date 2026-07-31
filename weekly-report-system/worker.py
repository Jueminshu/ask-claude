"""
后台 Worker 线程
- 文件处理：消费 task_queue
- 定时检查：超时自动通过 + 通知事件
"""
import time
import threading
from datetime import datetime
from database_v2 import (
    get_db, dequeue_task, complete_task, update_file_processing_status,
    get_current_week, create_notification_event
)
from services.file_parser import process_file


_worker_thread = None
_stop_flag = threading.Event()


def _worker_loop():
    """Worker 主循环"""
    last_scheduled_check = None

    while not _stop_flag.is_set():
        try:
            # 1. 处理文件任务
            task = dequeue_task()
            if task:
                _process_task(task)
                continue  # 有任务就连续处理

            # 2. 超时自动通过检查（每分钟一次）
            _check_auto_approve()

            # 3. 定时通知检查（每分钟一次）
            now = datetime.now()
            check_key = f"{now.hour}:{now.minute}"
            if check_key != last_scheduled_check:
                last_scheduled_check = check_key
                check_scheduled_notifications()

            # 没有任务，休眠 2 秒
            time.sleep(2)

        except Exception as e:
            print(f"[Worker] Error: {e}")
            time.sleep(5)


def _process_task(task):
    """处理单个文件任务"""
    task_id = task["id"]
    file_id = task["submission_file_id"]
    task_type = task["task_type"]

    try:
        if task_type == "process_full":
            conn = get_db()
            sf = conn.execute(
                "SELECT * FROM submission_files WHERE id = ?", (file_id,)
            ).fetchone()
            if not sf:
                complete_task(task_id, "file not found")
                conn.close()
                return

            sub = conn.execute(
                "SELECT id, user_id, module_id, week_start FROM submissions WHERE id = ?",
                (sf["submission_id"],)
            ).fetchone()
            module_id = sub["module_id"] if sub else 1
            user_id = sub["user_id"] if sub else 0
            week_start = sub["week_start"] if sub else ""
            conn.close()

            process_file(
                file_id=file_id,
                file_path=sf["original_path"],
                filename=sf["filename"],
                file_type=sf["file_type"],
                module_id=module_id,
            )

            # Phase 2: 风险提取
            try:
                from services.analyzer.risk_extractor import run_risk_extraction
                run_risk_extraction(
                    file_id=file_id,
                    submission_file_id=file_id,
                    module_id=module_id,
                    user_id=user_id,
                    week_start=week_start,
                )
            except Exception as e:
                print(f"[Worker] Risk extraction failed for file {file_id}: {e}")

            complete_task(task_id)
        else:
            complete_task(task_id, f"unknown task type: {task_type}")
    except Exception as e:
        complete_task(task_id, str(e))
        update_file_processing_status(file_id, "error")


def _check_auto_approve():
    """检查并执行超时自动通过"""
    now = datetime.now()
    # 只在周一 11:30-11:35 之间执行
    if now.weekday() != 0:
        return
    if now.hour != 11 or now.minute < 30 or now.minute >= 35:
        return

    conn = get_db()
    week_start, _week_end = get_current_week()

    pending = conn.execute(
        """SELECT id, user_id FROM submissions
           WHERE week_start = ? AND status = 'submitted' AND is_latest = 1""",
        (week_start,)
    ).fetchall()

    if not pending:
        conn.close()
        return

    # 临时关闭外键约束：reviewer_id=0 表示系统自动操作，无对应 users 记录
    conn.execute("PRAGMA foreign_keys = OFF")
    for sub in pending:
        conn.execute(
            """UPDATE submissions
               SET status = 'leader_approved',
                   leader_reviewed_by = 0,
                   leader_reviewed_at = datetime('now','localtime')
               WHERE id = ?""",
            (sub["id"],)
        )
        conn.execute(
            """INSERT INTO review_log (submission_id, reviewer_id, review_level, action, note)
               VALUES (?, 0, 'leader', 'approve', '超时自动通过')""",
            (sub["id"],)
        )
    conn.execute("PRAGMA foreign_keys = ON")

    conn.commit()
    print(f"[Worker] 超时自动通过 {len(pending)} 条")
    conn.close()


def check_scheduled_notifications():
    """检查并生成定时通知事件"""
    now = datetime.now()
    week_start, _week_end = get_current_week()
    conn = get_db()

    # N1: 周一 08:00-08:05 提醒未提交员工
    if now.weekday() == 0 and now.hour == 8 and now.minute < 5:
        users = conn.execute("""
            SELECT u.id, u.display_name FROM users u
            WHERE u.role IN ('member', 'leader') AND u.is_active = 1
            AND u.id NOT IN (
                SELECT s.user_id FROM submissions s
                WHERE s.week_start = ? AND s.is_latest = 1
            )
        """, (week_start,)).fetchall()

        today = now.strftime("%Y-%m-%d")
        for u in users:
            existing = conn.execute(
                """SELECT id FROM notification_events
                   WHERE event_type = 'pre_deadline_remind'
                   AND target_user_id = ? AND date(created_at) = ?""",
                (u["id"], today)
            ).fetchone()
            if not existing:
                create_notification_event(
                    "pre_deadline_remind", u["id"],
                    payload={
                        "week_start": week_start,
                        "deadline": "周一 10:00",
                        "message": "您本周周报尚未提交，请于周一10:00前完成"
                    }
                )

    # N2: 周一 11:00-11:05 提醒 Leader
    if now.weekday() == 0 and now.hour == 11 and now.minute < 5:
        leaders = conn.execute("""
            SELECT DISTINCT u.id, u.module_id, m.name as module_name
            FROM users u JOIN modules m ON u.module_id = m.id
            WHERE u.role = 'leader' AND u.is_active = 1
        """).fetchall()

        today = now.strftime("%Y-%m-%d")
        for leader in leaders:
            pending_count = conn.execute(
                """SELECT COUNT(*) FROM submissions
                   WHERE module_id = ? AND week_start = ?
                   AND status = 'submitted' AND is_latest = 1""",
                (leader["module_id"], week_start)
            ).fetchone()[0]

            if pending_count > 0:
                existing = conn.execute(
                    """SELECT id FROM notification_events
                       WHERE event_type = 'leader_window_remind'
                       AND target_user_id = ? AND date(created_at) = ?""",
                    (leader["id"], today)
                ).fetchone()
                if not existing:
                    create_notification_event(
                        "leader_window_remind", leader["id"],
                        payload={
                            "pending_count": pending_count,
                            "auto_approve_time": "11:30",
                            "message": f"您还有{pending_count}份周报未审核，11:30后自动通过"
                        }
                    )

    conn.close()


def start_worker():
    """启动后台 Worker 线程"""
    global _worker_thread, _stop_flag
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_flag.clear()
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="weekly-report-worker")
    _worker_thread.start()
    print("[Worker] Started")


def stop_worker():
    """停止后台 Worker 线程"""
    global _stop_flag
    _stop_flag.set()
    print("[Worker] Stopping...")
