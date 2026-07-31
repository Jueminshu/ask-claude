"""轻量 API 端点 — CRM 通知查询（可选，独立启动）"""
from fastapi import FastAPI
from database_v2 import get_db, get_pending_notifications as db_get_pending

app = FastAPI(title="周报系统通知 API")


@app.get("/api/notifications/pending")
def get_pending(user_id: int):
    """查询用户未处理的通知"""
    events = db_get_pending(user_id)
    return {"count": len(events), "events": events}


@app.post("/api/notifications/{event_id}/ack")
def ack_notification(event_id: int):
    """确认通知已发送"""
    conn = get_db()
    conn.execute(
        "UPDATE notification_events SET status = 'sent', sent_at = datetime('now','localtime') WHERE id = ?",
        (event_id,)
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}
