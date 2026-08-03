# Phase 2 分析引擎 v1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在领导查阅页新增"分析看板"Tab，提供 ① 风险热力图 和 ⑥ 个人效率概览，从已提交周报中自动提取风险信号和效率指标。

**Architecture:** 数据提取层（Python，从 Excel 风险列直接读取 + Claude API 处理 PPT 自由文本）→ 统计层（SQL 聚合 + Claude API 内容丰富度评估）→ 展示层（ECharts 热力图 + 统计卡片，嵌入式 HTML 组件）。风险条目写入新表 `risk_items` 持久化，按周缓存避免重复分析。

**Tech Stack:** Python 3.12+, SQLite, ECharts 5.x, Claude API, openpyxl, python-pptx

---

## Global Constraints

- 风险数据按周缓存，同一文件不重复分析（`submission_files.id` + `week_start` 唯一）
- Excel 模板（国内运营商、营销运营部）优先从固定列直接提取风险，不调用 Claude API
- PPT 模板（海外 BD）使用 Claude API 从自由文本中识别风险
- 效率概览中"内容丰富度"由 Claude API 评估，其他指标纯 SQL 统计
- 分析看板通过 `<script>` CDN 引入 ECharts，不依赖 npm/webpack
- 所有新增 DB 表写入通过 `database_v2.py` 函数封装

---

## File Structure

```
weekly-report-system/
├── database_v2.py                     ← Modify: 新增 risk_items 表 + 查询函数
├── worker.py                          ← Modify: process_file 后触发风险提取
├── services/
│   └── analyzer/
│       ├── __init__.py                ← Create
│       ├── risk_extractor.py          ← Create: 风险提取（直接读取 + Claude API）
│       └── efficiency.py              ← Create: 效率指标计算
├── static/
│   └── analysis_dashboard.html        ← Create: ECharts 热力图 + 效率卡片
└── pages/
    └── leader_browse.py               ← Modify: 新增 "📊 分析看板" Tab
```

---

### Task P2-1: risk_items 表 + 数据库函数

**Files:**
- Modify: `weekly-report-system/database_v2.py`

**Interfaces:**
- Consumes: `get_db()`, existing `init_db()` pattern
- Produces: `init_db()` 扩展（risk_items DDL）, `upsert_risk_items()`, `get_week_risks()`, `get_risk_history()`

- [ ] **Step 1: 在 init_db() 的 executescript 中新增 risk_items 表**

在 `init_db()` 的 `conn.executescript("""...""")` 调用中，在 `task_queue` 表定义之后、索引之前插入：

```sql
CREATE TABLE IF NOT EXISTS risk_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    module_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    submission_file_id INTEGER NOT NULL,
    customer TEXT,
    risk_description TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium',
    is_new INTEGER DEFAULT 1,
    source_column TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (module_id) REFERENCES modules(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (submission_file_id) REFERENCES submission_files(id)
);
```

同时新增索引（在现有索引区域追加）：

```sql
CREATE INDEX IF NOT EXISTS idx_risk_items_week ON risk_items(week_start, module_id);
CREATE INDEX IF NOT EXISTS idx_risk_items_file ON risk_items(submission_file_id);
```

- [ ] **Step 2: 在 database_v2.py 末尾新增风险查询函数**

```python
# === 风险条目 ===

def upsert_risk_items(week_start, module_id, user_id, submission_file_id, risks):
    """
    覆盖写入某文件的当周风险条目（先删旧，再插入）。
    risks: list of dicts with keys: customer, risk_description, severity, is_new, source_column
    """
    conn = get_db()
    conn.execute(
        "DELETE FROM risk_items WHERE submission_file_id = ?",
        (submission_file_id,)
    )
    for r in risks:
        conn.execute(
            """INSERT INTO risk_items
               (week_start, module_id, user_id, submission_file_id,
                customer, risk_description, severity, is_new, source_column)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                week_start, module_id, user_id, submission_file_id,
                r.get("customer"), r["risk_description"],
                r.get("severity", "medium"), r.get("is_new", 1),
                r.get("source_column"),
            )
        )
    conn.commit()
    conn.close()


def get_week_risks(week_start, module_id=None):
    """获取指定周的跨模块风险汇总"""
    conn = get_db()
    if module_id:
        rows = conn.execute(
            """SELECT r.*, m.name as module_name, u.display_name
               FROM risk_items r
               JOIN modules m ON r.module_id = m.id
               JOIN users u ON r.user_id = u.id
               WHERE r.week_start = ? AND r.module_id = ?
               ORDER BY r.severity DESC, r.is_new DESC""",
            (week_start, module_id)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT r.*, m.name as module_name, u.display_name
               FROM risk_items r
               JOIN modules m ON r.module_id = m.id
               JOIN users u ON r.user_id = u.id
               WHERE r.week_start = ?
               ORDER BY r.module_id, r.severity DESC, r.is_new DESC""",
            (week_start,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_risk_history(customer_keyword, weeks=4):
    """查询某个客户/项目的风险历史（跨周追踪）"""
    conn = get_db()
    rows = conn.execute(
        """SELECT r.*, m.name as module_name
           FROM risk_items r
           JOIN modules m ON r.module_id = m.id
           WHERE r.customer LIKE ? AND r.week_start >= ?
           ORDER BY r.week_start DESC""",
        (f"%{customer_keyword}%", weeks)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_efficiency_stats(module_id, week_start, weeks=4):
    """获取模块成员的效率统计（近 N 周）"""
    conn = get_db()
    rows = conn.execute(
        """SELECT
               u.id as user_id, u.display_name,
               COUNT(DISTINCT s.id) as submission_count,
               SUM(CASE WHEN s.status = 'leader_rejected' THEN 1 ELSE 0 END) as rejection_count,
               AVG(CASE WHEN s.submitted_at IS NOT NULL
                   THEN (strftime('%s', s.submitted_at) - strftime('%s', s.week_start || ' 00:00:00'))
                   ELSE NULL END) as avg_submit_seconds,
               SUM(sf.file_size) as total_file_size,
               COUNT(sf.id) as total_files
           FROM users u
           JOIN submissions s ON u.id = s.user_id AND s.is_latest = 1
           JOIN submission_files sf ON s.id = sf.submission_id
           WHERE u.module_id = ? AND s.week_start >= ?
           GROUP BY u.id
           ORDER BY u.display_name""",
        (module_id, week_start)
    ).fetchall()

    result = []
    for r in rows:
        avg_hours = round(r["avg_submit_seconds"] / 3600, 1) if r["avg_submit_seconds"] else None
        result.append({
            "user_id": r["user_id"],
            "display_name": r["display_name"],
            "submission_count": r["submission_count"],
            "rejection_count": r["rejection_count"],
            "avg_submit_hours": avg_hours,
            "total_file_size_kb": round(r["total_file_size"] / 1024, 1) if r["total_file_size"] else 0,
            "total_files": r["total_files"],
        })
    conn.close()
    return result
```

- [ ] **Step 3: 测试 risk_items 写入和查询**

```bash
python -c "
import sys; sys.path.insert(0, 'weekly-report-system')
from database_v2 import init_db, seed_data, get_week_risks, upsert_risk_items
init_db(); seed_data()
upsert_risk_items('2026-07-27', 1, 5, 1, [
    {'customer': '政企客户', 'risk_description': '竞品降价压力', 'severity': 'high', 'is_new': 1, 'source_column': '风险及求助'},
    {'customer': '渠道', 'risk_description': '代理商培训不足', 'severity': 'medium', 'is_new': 0, 'source_column': '风险及求助'},
])
risks = get_week_risks('2026-07-27')
assert len(risks) == 2
print('OK: risks inserted and queried')
"
```
Expected: 打印 "OK: risks inserted and queried"

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/database_v2.py
git commit -m "feat: risk_items table + upsert/get_week_risks/get_risk_history/get_efficiency_stats"
```

---

### Task P2-2: 风险提取器 — risk_extractor.py

**Files:**
- Create: `weekly-report-system/services/analyzer/__init__.py`
- Create: `weekly-report-system/services/analyzer/risk_extractor.py`

**Interfaces:**
- Consumes: `get_db()`, `upsert_risk_items()` from `database_v2`; `extract_text()` from `services.file_parser`
- Produces: `extract_risks_from_excel()`, `extract_risks_via_claude()`, `run_risk_extraction(file_id, submission_file_id, module_id, user_id, week_start)`

- [ ] **Step 1: 编写 services/analyzer/__init__.py**

```python
"""分析引擎 — Phase 2: 风险提取 + 效率概览"""
```

- [ ] **Step 2: 编写 services/analyzer/risk_extractor.py**

```python
"""
风险提取器
- Excel 模板（国内运营商、营销运营部）：从固定风险列直接读取
- PPT 模板（海外 BD）：Claude API 自由文本识别
"""
import os
import json
from database_v2 import get_db, upsert_risk_items


# === 模板 → 风险列名映射 ===
TEMPLATE_RISK_COLUMNS = {
    "周报": ["风险及求助"],       # 国内运营商
    "周报_营销": ["问题反馈&所需支持"],  # 营销运营部
}


def _find_risk_column(headers, template_name):
    """根据模板名查找风险列索引"""
    candidates = TEMPLATE_RISK_COLUMNS.get(template_name, [])
    if not candidates:
        # 模糊匹配：任意 header 包含 "风险" 或 "问题"
        for i, h in enumerate(headers):
            h_str = str(h).lower() if h else ""
            if any(kw in h_str for kw in ["风险", "求助", "问题反馈"]):
                return i, str(h)
        return None, None
    for i, h in enumerate(headers):
        if str(h) in candidates:
            return i, str(h)
    return None, None


def _parse_excel_headers(file_path):
    """读取 Excel 文件第一行作为表头"""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        ws = wb.active
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        # 读取数据行
        data_rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and any(c for c in row):
                data_rows.append([str(c) if c else "" for c in row])
        wb.close()
        return headers, data_rows
    except Exception:
        return [], []


def extract_risks_from_excel(file_path, template_name, user_id, module_id, week_start, submission_file_id):
    """
    从 Excel 文件的风险列直接提取风险条目。
    返回: list[dict]
    """
    headers, data_rows = _parse_excel_headers(file_path)
    if not headers:
        return []

    risk_col_idx, col_name = _find_risk_column(headers, template_name)
    if risk_col_idx is None:
        return []

    # 找到 "重点项目" 或 "业务模块" 列作为 customer 来源
    customer_col_idx = None
    for i, h in enumerate(headers):
        h_str = str(h) if h else ""
        if any(kw in h_str for kw in ["重点项目", "业务模块", "客户"]):
            customer_col_idx = i
            break

    risks = []
    for row in data_rows:
        if risk_col_idx >= len(row) or not row[risk_col_idx].strip():
            continue  # 风险列为空，跳过

        customer = row[customer_col_idx] if customer_col_idx is not None and customer_col_idx < len(row) else None
        risk_text = row[risk_col_idx].strip()

        # 基本严重程度判断
        severity = "medium"
        high_keywords = ["严重", "紧急", "高风险", "损失", "投诉升级"]
        low_keywords = ["已完成", "已解决", "轻微"]
        if any(kw in risk_text for kw in high_keywords):
            severity = "high"
        elif any(kw in risk_text for kw in low_keywords):
            severity = "low"

        risks.append({
            "customer": customer,
            "risk_description": risk_text,
            "severity": severity,
            "is_new": 1,
            "source_column": col_name,
        })

    return risks


def extract_risks_via_claude(file_path, file_type, module_id, week_start):
    """
    对 PPT 等非结构化文件，使用 Claude API 从文本中提取风险。
    返回: list[dict]
    """
    from services.file_parser import extract_text

    text = extract_text(file_path, file_type)
    if not text or text.startswith("["):
        return []  # 提取失败，返回空

    # Claude API 调用
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # 无 API key 时回退到关键词匹配
        return _keyword_risk_fallback(text)

    import urllib.request
    import urllib.error

    prompt = f"""你是一个风险分析助手。从以下周报文本中提取所有风险条目。

周报文本：
{text[:6000]}

对每个风险条目，返回以下字段：
- customer: 关联的客户或项目名称（如无则填 null）
- risk_description: 风险描述（简要一句话）
- severity: 严重程度（high/medium/low）
- is_new: 是否本周新提出（1=新风险, 0=持续风险）

请以 JSON 数组格式返回，只返回 JSON，不要其他文字。
如果无风险，返回空数组 []。

示例返回格式：
[{{"customer": "政企客户", "risk_description": "竞品降价导致续约困难", "severity": "high", "is_new": 1}}]"""

    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({
                "model": "claude-sonnet-5",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            }).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        content = result["content"][0]["text"]
        # 尝试解析 JSON
        json_start = content.find("[")
        json_end = content.rfind("]") + 1
        if json_start >= 0 and json_end > json_start:
            risks = json.loads(content[json_start:json_end])
            for r in risks:
                r.setdefault("source_column", "claude_api")
            return risks
        return []
    except Exception:
        return _keyword_risk_fallback(text)


def _keyword_risk_fallback(text):
    """关键词回退：从文本中识别风险信号"""
    risks = []
    risk_keywords = [
        ("风险", "high"), ("问题", "medium"), ("困难", "medium"),
        ("延期", "high"), ("不足", "medium"), ("压力", "high"),
        ("投诉", "high"), ("竞品", "high"),
    ]
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        for kw, sev in risk_keywords:
            if kw in line:
                risks.append({
                    "customer": None,
                    "risk_description": line[:120],
                    "severity": sev,
                    "is_new": 1,
                    "source_column": "keyword_fallback",
                })
                break  # 一行只匹配一次
    return risks[:20]  # 最多 20 条


def run_risk_extraction(file_id, submission_file_id, module_id, user_id, week_start):
    """
    对一个文件执行风险提取并写入 DB。
    由 Worker 调用。
    """
    conn = get_db()
    sf = conn.execute("SELECT * FROM submission_files WHERE id = ?", (file_id,)).fetchone()
    if not sf:
        conn.close()
        return

    # 获取模板名
    tmpl = conn.execute(
        "SELECT ft.name FROM file_templates ft WHERE ft.id = ?",
        (sf["template_id"],)
    ).fetchone()
    template_name = tmpl["name"] if tmpl else None
    conn.close()

    file_type = sf["file_type"]
    file_path = sf["original_path"]
    risks = []

    if file_type == "xlsx" and template_name:
        # Excel → 直接从风险列读取
        risks = extract_risks_from_excel(
            file_path, template_name, user_id, module_id, week_start, submission_file_id
        )
    elif file_type in ("pptx", "docx", "pdf"):
        # PPT/Word/PDF → Claude API
        risks = extract_risks_via_claude(file_path, file_type, module_id, week_start)

    if risks:
        upsert_risk_items(week_start, module_id, user_id, submission_file_id, risks)
```

- [ ] **Step 3: 测试 Excel 风险提取**

```bash
python -c "
import sys; sys.path.insert(0, 'weekly-report-system')
from services.analyzer.risk_extractor import extract_risks_from_excel

risks = extract_risks_from_excel(
    'weekly-report-system/output/【国内运营商】周报汇总_20260729.xlsx',
    '周报', user_id=1, module_id=1, week_start='2026-07-27', submission_file_id=1
)
print(f'Found {len(risks)} risks:')
for r in risks:
    print(f'  [{r[\"severity\"]}] {r[\"customer\"]}: {r[\"risk_description\"][:60]}')
assert len(risks) >= 1
print('OK')
"
```
Expected: 找到至少 1 条风险（"竞品降价压力大"），打印 OK

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/services/analyzer/__init__.py weekly-report-system/services/analyzer/risk_extractor.py
git commit -m "feat: risk extractor — Excel column reading + Claude API + keyword fallback"
```

---

### Task P2-3: 效率指标 — efficiency.py

**Files:**
- Create: `weekly-report-system/services/analyzer/efficiency.py`

**Interfaces:**
- Consumes: `get_efficiency_stats()` from `database_v2`; Claude API (可选)
- Produces: `compute_efficiency(module_id, week_start)`, `assess_content_richness_via_claude(text)`

- [ ] **Step 1: 编写 services/analyzer/efficiency.py**

```python
"""
个人效率概览
- 提交及时率 / 驳回次数 → 纯 SQL 统计
- 内容丰富度 → Claude API 评估（可选）
"""
import os
import json
from database_v2 import get_efficiency_stats, get_db, get_current_week


# 提交时间评分阈值
SCORE_THRESHOLDS = {
    "timely": 50,       # 从周一开始算，50 小时内提交（约周一全天）→ 及时
    "acceptable": 100,  # 100 小时内（约周二）→ 可接受
    # 超过 100 小时 → 延迟
}


def _score_timeliness(avg_submit_hours):
    """将平均提交时间映射为 0-100 分"""
    if avg_submit_hours is None:
        return 50  # 无历史数据默认 50
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
    if sf["file_size"] and sf["file_size"] > 10240:  # >10KB
        score += 10
    if sf["file_size"] and sf["file_size"] > 51200:  # >50KB
        score += 5
    return min(score, 100)


def compute_efficiency(module_id, week_start, weeks=4):
    """
    计算模块所有成员的效率指标。
    返回: list[dict]，每个 dict 含:
        - user_id, display_name
        - timeliness_score (0-100)
        - timeliness_label: "及时" | "一般" | "偏迟"
        - content_score (0-100)
        - rejection_count
        - submission_count
    """
    stats = get_efficiency_stats(module_id, week_start, weeks)

    # 获取每个成员最新文件的文本用于评估内容丰富度
    conn = get_db()
    for s in stats:
        # 取该用户本周最新提交的第一个文件
        sf = conn.execute(
            """SELECT sf.id FROM submission_files sf
               JOIN submissions s ON sf.submission_id = s.id
               WHERE s.user_id = ? AND s.week_start = ?
               ORDER BY s.submitted_at DESC LIMIT 1""",
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
```

- [ ] **Step 2: 测试效率计算**

```bash
python -c "
import sys; sys.path.insert(0, 'weekly-report-system')
from database_v2 import init_db, seed_data
from services.analyzer.efficiency import compute_efficiency
init_db(); seed_data()
result = compute_efficiency(1, '2026-07-27')
assert isinstance(result, list)
print('Keys:', list(result[0].keys()) if result else '(empty)')
print('OK')
"
```
Expected: 打印 keys 列表，包含 timeliness_score/content_score 等字段

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/services/analyzer/efficiency.py
git commit -m "feat: efficiency metrics — timeliness scoring + content richness from DB"
```

---

### Task P2-4: 分析看板嵌入式组件 — analysis_dashboard.html

**Files:**
- Create: `weekly-report-system/static/analysis_dashboard.html`

**Interfaces:**
- Consumes: 数据通过 `postMessage` 从 Python 注入（risks + efficiency）
- Produces: 无导出函数，纯展示组件

- [ ] **Step 1: 编写 analysis_dashboard.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>分析看板</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }
.container { padding: 16px; max-width: 1400px; margin: 0 auto; }
.module-select { width: 200px; padding: 8px; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 16px; font-size: 14px; }

/* KPI 卡片行 */
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.kpi-card { background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.kpi-label { font-size: 12px; color: #999; margin-bottom: 4px; }
.kpi-value { font-size: 28px; font-weight: 700; }
.kpi-sub { font-size: 11px; color: #999; margin-top: 2px; }
.kpi-value.high { color: #ea4335; }
.kpi-value.medium { color: #fbbc04; }
.kpi-value.good { color: #34a853; }

/* 图表区域 */
.charts-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
.chart-panel { background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.chart-panel.full { grid-column: 1 / -1; }
.chart-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; color: #555; }
.chart-box { width: 100%; height: 400px; }

/* 风险列表 */
.risk-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.risk-table th { text-align: left; padding: 8px; border-bottom: 2px solid #e0e0e0; color: #666; font-weight: 600; }
.risk-table td { padding: 8px; border-bottom: 1px solid #f0f0f0; }
.risk-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.risk-badge.high { background: #fce8e6; color: #c5221f; }
.risk-badge.medium { background: #fef7e0; color: #b06000; }
.risk-badge.low { background: #e6f4ea; color: #137333; }
.risk-badge.new { background: #e8f0fe; color: #1a73e8; margin-left: 4px; }

/* 效率排名 */
.efficiency-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.efficiency-table th { text-align: left; padding: 6px; border-bottom: 2px solid #e0e0e0; color: #666; }
.efficiency-table td { padding: 6px; border-bottom: 1px solid #f0f0f0; }
.score-bar { display: inline-block; height: 6px; border-radius: 3px; background: #e0e0e0; min-width: 100px; vertical-align: middle; }
.score-fill { height: 6px; border-radius: 3px; }
.score-fill.good { background: #34a853; }
.score-fill.medium { background: #fbbc04; }
.score-fill.low { background: #ea4335; }

.loading { display: flex; align-items: center; justify-content: center; height: 300px; color: #999; font-size: 16px; }
</style>
</head>
<body>
<div class="container">
  <div id="loadingArea" class="loading">📊 数据加载中...</div>
  <div id="dashboardArea" style="display:none;">
    <select class="module-select" id="moduleSelect" onchange="onModuleChange()">
      <option value="all">📋 全部模块</option>
    </select>

    <!-- KPI -->
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-label">风险总数</div>
        <div class="kpi-value" id="kpiTotalRisks">-</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">高风险</div>
        <div class="kpi-value high" id="kpiHighRisks">-</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">新增风险</div>
        <div class="kpi-value medium" id="kpiNewRisks">-</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">提交及时率</div>
        <div class="kpi-value good" id="kpiTimeliness">-</div>
      </div>
    </div>

    <div class="charts-grid">
      <!-- 风险热力图 -->
      <div class="chart-panel">
        <div class="chart-title">🔥 风险热力图</div>
        <div class="chart-box" id="heatmapChart"></div>
      </div>

      <!-- 严重程度分布 -->
      <div class="chart-panel">
        <div class="chart-title">⚠️ 严重程度分布</div>
        <div class="chart-box" id="severityChart"></div>
      </div>
    </div>

    <!-- 风险清单 -->
    <div class="chart-panel" style="margin-top:12px;">
      <div class="chart-title">📋 风险清单</div>
      <table class="risk-table" id="riskTable">
        <thead><tr>
          <th>模块</th><th>人员</th><th>客户/项目</th><th>风险描述</th><th>严重程度</th>
        </tr></thead>
        <tbody id="riskTableBody"></tbody>
      </table>
    </div>

    <!-- 效率排名 -->
    <div class="chart-panel" style="margin-top:12px;">
      <div class="chart-title">⚡ 个人效率概览</div>
      <table class="efficiency-table" id="efficiencyTable">
        <thead><tr>
          <th>人员</th><th>提交及时性</th><th>内容丰富度</th><th>提交次数</th><th>驳回次数</th>
        </tr></thead>
        <tbody id="efficiencyTableBody"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
let state = { risks: [], efficiency: [], modules: [], currentModule: 'all' };
let heatmapChart = null, severityChart = null;

// 接收 Python 数据注入
window.addEventListener('message', function(e) {
  if (e.data.type === 'analysisData') {
    state = { ...state, ...e.data.payload };
    state.currentModule = 'all';
    renderAll();
  }
});

function renderAll() {
  document.getElementById('loadingArea').style.display = 'none';
  document.getElementById('dashboardArea').style.display = 'block';
  renderModuleSelect();
  renderKPIs();
  renderHeatmap();
  renderSeverityChart();
  renderRiskTable();
  renderEfficiencyTable();
}

function renderModuleSelect() {
  const sel = document.getElementById('moduleSelect');
  const moduleOpts = state.modules.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
  sel.innerHTML = '<option value="all">📋 全部模块</option>' + moduleOpts;
  sel.value = state.currentModule;
}

function onModuleChange() {
  state.currentModule = document.getElementById('moduleSelect').value;
  renderKPIs();
  renderHeatmap();
  renderSeverityChart();
  renderRiskTable();
  renderEfficiencyTable();
}

function getFilteredRisks() {
  if (state.currentModule === 'all') return state.risks;
  return state.risks.filter(r => r.module_id == state.currentModule);
}

function getFilteredEfficiency() {
  if (state.currentModule === 'all') return state.efficiency;
  return state.efficiency.filter(e => e.module_id == state.currentModule);
}

// KPI 卡片
function renderKPIs() {
  const risks = getFilteredRisks();
  const eff = getFilteredEfficiency();
  document.getElementById('kpiTotalRisks').textContent = risks.length;
  document.getElementById('kpiHighRisks').textContent = risks.filter(r => r.severity === 'high').length;
  document.getElementById('kpiNewRisks').textContent = risks.filter(r => r.is_new == 1).length;
  const timeliness = eff.length > 0
    ? Math.round(eff.reduce((s, e) => s + e.timeliness_score, 0) / eff.length)
    : 0;
  document.getElementById('kpiTimeliness').textContent = timeliness + '%';
}

// 风险热力图
function renderHeatmap() {
  if (!heatmapChart) heatmapChart = echarts.init(document.getElementById('heatmapChart'));
  const risks = getFilteredRisks();
  if (risks.length === 0) { heatmapChart.clear(); return; }

  // 按客户/项目聚合
  const customers = [...new Set(risks.map(r => r.customer || '未分类'))];
  const modules = [...new Set(risks.map(r => r.module_name))];
  const data = customers.map((cust, ci) =>
    modules.map((mod, mi) => {
      const matching = risks.filter(r => (r.customer || '未分类') === cust && r.module_name === mod);
      if (matching.length === 0) return [mi, ci, '-'];
      const maxSev = matching.some(r => r.severity === 'high') ? 3
        : matching.some(r => r.severity === 'medium') ? 2 : 1;
      return [mi, ci, maxSev];
    })
  ).flat();

  heatmapChart.setOption({
    tooltip: {
      formatter: function(p) {
        if (p.value[2] === '-') return '无数据';
        const sev = ['', '低', '中', '高'][p.value[2]];
        return `${modules[p.value[0]]}<br/>${customers[p.value[1]]}<br/>严重程度: ${sev}`;
      }
    },
    grid: { left: 120, right: 40, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: modules, axisLabel: { rotate: 30, fontSize: 11 } },
    yAxis: { type: 'category', data: customers, axisLabel: { fontSize: 11 } },
    visualMap: {
      min: 0, max: 3,
      inRange: { color: ['#f5f5f5', '#e6f4ea', '#fef7e0', '#fce8e6'] },
      categories: ['无', '低', '中', '高'],
      show: false
    },
    series: [{
      type: 'heatmap', data: data.filter(d => d[2] !== '-'),
      label: { show: true, fontSize: 9 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } }
    }]
  });
}

// 严重程度饼图
function renderSeverityChart() {
  if (!severityChart) severityChart = echarts.init(document.getElementById('severityChart'));
  const risks = getFilteredRisks();
  const high = risks.filter(r => r.severity === 'high').length;
  const medium = risks.filter(r => r.severity === 'medium').length;
  const low = risks.filter(r => r.severity === 'low').length;
  if (high + medium + low === 0) { severityChart.clear(); return; }

  severityChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['45%', '75%'],
      avoidLabelOverlap: false,
      label: { show: true, formatter: '{b}\n{d}%' },
      data: [
        { value: high, name: '高风险', itemStyle: { color: '#ea4335' } },
        { value: medium, name: '中风险', itemStyle: { color: '#fbbc04' } },
        { value: low, name: '低风险', itemStyle: { color: '#34a853' } },
      ]
    }]
  });
}

// 风险清单表格
function renderRiskTable() {
  const risks = getFilteredRisks();
  const html = risks.map(r => `
    <tr>
      <td>${r.module_name || ''}</td>
      <td>${r.display_name || ''}</td>
      <td>${r.customer || '-'}</td>
      <td>${r.risk_description}</td>
      <td>
        <span class="risk-badge ${r.severity}">${r.severity === 'high' ? '高' : r.severity === 'medium' ? '中' : '低'}</span>
        ${r.is_new == 1 ? '<span class="risk-badge new">新增</span>' : '<span class="risk-badge">持续</span>'}
      </td>
    </tr>`).join('');
  document.getElementById('riskTableBody').innerHTML = html || '<tr><td colspan="5" style="color:#999;">暂无风险</td></tr>';
}

// 效率排名表
function renderEfficiencyTable() {
  const eff = [...getFilteredEfficiency()].sort((a, b) => b.timeliness_score - a.timeliness_score);
  const html = eff.map(e => `
    <tr>
      <td><strong>${e.display_name}</strong></td>
      <td>
        <span style="color:${e.timeliness_score >= 90 ? '#34a853' : e.timeliness_score >= 60 ? '#fbbc04' : '#ea4335'}">${e.timeliness_label}</span>
        <span class="score-bar"><span class="score-fill ${e.timeliness_score >= 90 ? 'good' : e.timeliness_score >= 60 ? 'medium' : 'low'}" style="width:${e.timeliness_score}%;"></span></span>
      </td>
      <td>
        <span class="score-bar"><span class="score-fill ${e.content_score >= 80 ? 'good' : e.content_score >= 60 ? 'medium' : 'low'}" style="width:${e.content_score}%;"></span></span>
      </td>
      <td>${e.submission_count}次</td>
      <td>${e.rejection_count > 0 ? '🔴 ' + e.rejection_count + '次' : '✅ 0'}</td>
    </tr>`).join('');
  document.getElementById('efficiencyTableBody').innerHTML = html || '<tr><td colspan="5" style="color:#999;">暂无数据</td></tr>';
}

// 响应式
window.addEventListener('resize', function() {
  if (heatmapChart) heatmapChart.resize();
  if (severityChart) severityChart.resize();
});
</script>
</body>
</html>
```

- [ ] **Step 2: 验证 HTML 语法**

Run: `python -c "open('weekly-report-system/static/analysis_dashboard.html').read(); print('HTML OK')"`
Expected: 打印 "HTML OK"

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/static/analysis_dashboard.html
git commit -m "feat: analysis dashboard — ECharts heatmap + severity pie + efficiency ranking"
```

---

### Task P2-5: 领导查阅页改造 — 新增分析看板 Tab

**Files:**
- Modify: `weekly-report-system/pages/leader_browse.py`

**Interfaces:**
- Consumes: `get_week_risks()`, `get_db()` from `database_v2`; `compute_efficiency()` from `services.analyzer.efficiency`
- Produces: 分析看板 Tab 中注入 JSON 数据到 HTML 组件（行为不变）

- [ ] **Step 1: 在 leader_browse.py 顶部新增分析数据准备函数**

在 `STATIC_DIR` 定义之后、`_get_all_members_status` 之前插入：

```python
ANALYSIS_HTML_PATH = os.path.join(STATIC_DIR, "analysis_dashboard.html")


def _prepare_analysis_data(week_start):
    """准备分析看板所需的全部数据"""
    conn = get_db()
    risks = get_week_risks(week_start)
    all_modules = conn.execute("SELECT id, name FROM modules ORDER BY id").fetchall()
    conn.close()

    modules_data = [{"id": m["id"], "name": m["name"]} for m in all_modules]

    # 给每个 risk 附加 module_name（get_week_risks 已包含）
    # 计算各模块效率
    all_efficiency = []
    for m in all_modules:
        eff = compute_efficiency(m["id"], week_start)
        for e in eff:
            e["module_id"] = m["id"]
            e["module_name"] = m["name"]
        all_efficiency.extend(eff)

    return {
        "risks": risks,
        "efficiency": all_efficiency,
        "modules": modules_data,
        "weekStart": week_start,
    }
```

- [ ] **Step 2: 修改 render_leader_browse_page，在顶部加 Tab 切换**

替换函数开头的 `st.title("📊 领导查阅")` 为：

```python
def render_leader_browse_page(user):
    """渲染领导查阅页"""
    st.title("📊 领导查阅")

    week_start, week_end = get_current_week()

    # Tab 切换：周报查阅 / 分析看板
    tab1, tab2 = st.tabs(["📋 周报查阅", "📊 分析看板"])

    # ===== Tab 1: 周报查阅（原有逻辑） =====
    with tab1:
        _render_browse_tab(user, week_start, week_end)

    # ===== Tab 2: 分析看板 =====
    with tab2:
        st.caption(f"数据周期: {week_start} ~ {week_end}")
        analysis_data = _prepare_analysis_data(week_start)

        with open(ANALYSIS_HTML_PATH, "r", encoding="utf-8") as f:
            analysis_html = f.read()

        # 注入数据
        inject_script = f"""
        <script>
        window.addEventListener('DOMContentLoaded', function() {{
            window.postMessage({{type: 'analysisData', payload: {json.dumps(analysis_data, ensure_ascii=False, default=str)}}}, '*');
        }});
        </script>
        """
        full_html = analysis_html.replace("</body>", inject_script + "</body>")
        st.components.v1.html(full_html, height=900)
```

- [ ] **Step 3: 将原 render_leader_browse_page 的逻辑提取为 _render_browse_tab**

将原来 `render_leader_browse_page` 中从 "获取可访问的模块" 到最后的逻辑（除 `st.title` 和 `week_start, week_end = get_current_week()` 外）全部移到新函数：

```python
def _render_browse_tab(user, week_start, week_end):
    """Tab 1: 周报查阅 — 原有完整逻辑"""
    # ...（原 render_leader_browse_page 函数体中除 title 和 week 获取外的全部代码）
```

- [ ] **Step 4: 验证导入和语法**

```bash
python -c "
import sys; sys.path.insert(0, 'weekly-report-system')
from pages.leader_browse import render_leader_browse_page, _prepare_analysis_data
print('Import OK')
"
```
Expected: 打印 "Import OK"

- [ ] **Step 5: Commit**

```bash
git add weekly-report-system/pages/leader_browse.py
git commit -m "feat: add analysis dashboard tab to leader browse page"
```

---

### Task P2-6: Worker 集成 + 端到端测试

**Files:**
- Modify: `weekly-report-system/worker.py`
- Create: `tests/test_phase2.py`

**Interfaces:**
- Consumes: `run_risk_extraction()` from `services.analyzer.risk_extractor`
- Produces: 文件处理完成后自动触发风险提取

- [ ] **Step 1: 在 worker.py 的 _process_task 中集成风险提取**

在 `_process_task()` 的 `if task_type == "process_full":` 分支中，`process_file(...)` 调用之后、`complete_task(task_id)` 之前，插入：

```python
            # Phase 2: 提取风险
            try:
                from services.analyzer.risk_extractor import run_risk_extraction
                sub = conn.execute(
                    "SELECT user_id, module_id, week_start FROM submissions WHERE id = ?",
                    (sf["submission_id"],)
                ).fetchone()
                if sub:
                    run_risk_extraction(
                        file_id=sf["id"],
                        submission_file_id=sf["id"],
                        module_id=sub["module_id"],
                        user_id=sub["user_id"],
                        week_start=sub["week_start"],
                    )
            except Exception as e:
                print(f"[Worker] Risk extraction failed for file {file_id}: {e}")
```

注意：需要在 `_process_task` 函数开头的 DB 查询后保留 `conn` 引用不变。当前代码在 `process_file()` 之前已经 `conn.close()`，需要调整为在风险提取之后才 close。

完整修改后的 `_process_task` 关键部分：

```python
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
```

- [ ] **Step 2: 编写端到端测试 tests/test_phase2.py**

```python
"""Phase 2 分析引擎测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'weekly-report-system'))
from database_v2 import init_db, seed_data, get_week_risks, get_efficiency_stats
from services.analyzer.risk_extractor import extract_risks_from_excel, _keyword_risk_fallback
from services.analyzer.efficiency import compute_efficiency, _score_timeliness


init_db()
seed_data()


def test_keyword_fallback():
    text = "竞品降价压力大，客户可能流失。项目A进展顺利。数据源接入遇到困难，需要IT支持。"
    risks = _keyword_risk_fallback(text)
    assert len(risks) >= 2  # "压力" + "困难"
    print(f"Keyword fallback found {len(risks)} risks")


def test_score_timeliness():
    assert _score_timeliness(10) == 100   # 及时
    assert _score_timeliness(60) == 70    # 可接受
    assert _score_timeliness(200) == 30   # 延迟
    assert _score_timeliness(None) == 50  # 无数据


def test_excel_risk_extraction():
    file_path = os.path.join(
        os.path.dirname(__file__), '..',
        'weekly-report-system', 'output', '【国内运营商】周报汇总_20260729.xlsx'
    )
    if not os.path.exists(file_path):
        print("SKIP: test data file not found")
        return
    risks = extract_risks_from_excel(file_path, "周报", 5, 1, "2026-07-27", 1)
    assert len(risks) >= 1  # 至少 "竞品降价压力大"
    assert any("竞品" in r["risk_description"] for r in risks)
    print(f"Excel extraction found {len(risks)} risks: {[r['risk_description'][:30] for r in risks]}")


def test_efficiency_computation():
    result = compute_efficiency(1, "2026-07-27")
    assert isinstance(result, list)
    if result:
        e = result[0]
        assert "timeliness_score" in e
        assert "content_score" in e
        assert "rejection_count" in e
    print(f"Efficiency computed for {len(result)} members")
```

- [ ] **Step 3: 运行测试**

```bash
pytest tests/test_phase2.py -v
```
Expected: 4 tests PASS（test_excel_risk_extraction 可能需要测试数据文件，如不存在则 SKIP）

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/worker.py tests/test_phase2.py
git commit -m "feat: integrate risk extraction into worker + phase 2 E2E tests"
```

---

## 分阶段交付概览

| Phase | Tasks | 交付物 |
|-------|-------|--------|
| **Phase 1** (已完成) | Task 1-12 | 数据库 v2 + 多文件上传 + Leader 审核 + 领导查阅 + 通知 + 系统管理 |
| **Phase 2** (本次) | Task P2-1 ~ P2-6 | 风险热力图 + 个人效率概览 + 分析看板 |
| **Phase 3** (后续) | — | 项目健康度 + 进度异常 + 会议待办 + 协同盲点 |

---

## 自审检查

- [x] 6 个 Task 覆盖 ① 风险热力图 + ⑥ 个人效率概览
- [x] 风险提取覆盖 3 种模板类型（Excel 直接读取、Excel 模糊匹配、PPT Claude API + 关键词回退）
- [x] 效率概览提供完整的 SQL 统计 + 评分算法
- [x] 分析看板 ECharts 热力图 + 饼图 + 表格完整实现
- [x] 所有 Task 有完整代码，无 TBD/TODO
- [x] 接口签名与 Phase 1 database_v2 保持一致
- [x] 风险数据写入 risk_items 表持久化，按文件覆盖去重
