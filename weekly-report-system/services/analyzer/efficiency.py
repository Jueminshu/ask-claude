"""
个人效率概览
- 提交及时率 / 驳回次数 → 纯 SQL 统计
- 内容丰富度 → 基于提取文本长度和文件大小的启发式评分
"""
from database_v2 import get_efficiency_stats, get_db, get_current_week


SCORE_THRESHOLDS = {
    "timely": 50,       # 从周一开始算，50 小时内提交 → 及时
    "acceptable": 100,  # 100 小时内 → 可接受
}


def _score_timeliness(avg_submit_hours):
    """将平均提交时间映射为 0-100 分"""
    if avg_submit_hours is None:
        return 50
    if avg_submit_hours <= SCORE_THRESHOLDS["timely"]:
        return 100
    if avg_submit_hours <= SCORE_THRESHOLDS["acceptable"]:
        return 70
    return 30


def _score_content_richness_from_db(file_id):
    """从 DB 提取的文本估算内容丰富度（0-100）"""
    conn = get_db()
    sf = conn.execute(
        "SELECT extracted_text, file_size FROM submission_files WHERE id = ?",
        (file_id,)
    ).fetchone()
    conn.close()
    if not sf:
        return 50

    score = 50
    if sf["extracted_text"] and len(sf["extracted_text"]) > 200:
        score += 20
    if sf["extracted_text"] and len(sf["extracted_text"]) > 1000:
        score += 15
    if sf["file_size"] and sf["file_size"] > 10240:
        score += 10
    if sf["file_size"] and sf["file_size"] > 51200:
        score += 5
    return min(score, 100)


def compute_efficiency(module_id, week_start):
    """
    计算模块所有成员的效率指标。
    返回: list[dict]
    """
    stats = get_efficiency_stats(module_id, week_start)

    conn = get_db()
    for s in stats:
        sf = conn.execute(
            """SELECT sf.id FROM submission_files sf
               JOIN submissions s2 ON sf.submission_id = s2.id
               WHERE s2.user_id = ? AND s2.week_start = ?
               ORDER BY s2.submitted_at DESC LIMIT 1""",
            (s["user_id"], week_start)
        ).fetchone()
        s["timeliness_score"] = _score_timeliness(s.get("avg_submit_hours"))
        s["timeliness_label"] = (
            "及时" if s["timeliness_score"] >= 90
            else "一般" if s["timeliness_score"] >= 60
            else "偏迟"
        )
        s["content_score"] = _score_content_richness_from_db(sf["id"]) if sf else 50
    conn.close()

    return stats
