# 市场情报模块 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task.

**Goal:** 从销售部周报中提取"市场信息"区域，汇入 `market_intel` 总表，提供总表查询 + 竞品热力图 + 型号时间线三种分析视图

**Architecture:** 新建提取器模块 → 挂入 Worker 管线 → 新建数据库表+CRUD → 新建 HTML 组件 → 挂入领导查阅页 Tab 3

**Tech Stack:** Python/openpyxl (提取), SQLite (存储), ECharts (热力图), vanilla HTML/CSS/JS (UI), Streamlit bridge

## Global Constraints

- 不引入新依赖（已有 openpyxl）
- 复用现有风险热力图视觉风格
- 提取失败不阻塞其他处理
- 权限：superior + can_browse_all leader
- 提取定位：扫描 column A 找到"市场信息"单元格，非硬编码行号
- 覆盖策略：同周同人同文件先删旧后插入

---

### Task 1: 数据库层 — market_intel 表 + CRUD

**Files:**
- Modify: `weekly-report-system/database_v2.py`

**Interfaces:**
- Produces: `upsert_market_intel(week_start, module_id, user_id, submission_file_id, rows)`, `get_market_intel(week_start=None, module_id=None, vendor=None, category=None, model=None, user_id=None) -> list[dict]`, `get_model_timeline(model, weeks=8) -> list[dict]`

- [ ] **Step 1: 在 `init_db()` 中创建 `market_intel` 表和索引**

在 `init_db()` 的 `executescript` 块中添加：

```sql
CREATE TABLE IF NOT EXISTS market_intel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    module_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    submission_file_id INTEGER NOT NULL,
    seq INTEGER,
    update_time TEXT,
    collector TEXT,
    vendor TEXT,
    category TEXT,
    model TEXT,
    config TEXT,
    peripheral TEXT,
    price_tier TEXT,
    our_model TEXT,
    our_config TEXT,
    our_peripheral TEXT,
    our_price_tier TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (module_id) REFERENCES modules(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (submission_file_id) REFERENCES submission_files(id)
);

CREATE INDEX IF NOT EXISTS idx_market_intel_week ON market_intel(week_start, module_id);
CREATE INDEX IF NOT EXISTS idx_market_intel_vendor ON market_intel(vendor, category);
CREATE INDEX IF NOT EXISTS idx_market_intel_model ON market_intel(model);
```

- [ ] **Step 2: 实现 `upsert_market_intel`**

```python
def upsert_market_intel(week_start, module_id, user_id, submission_file_id, rows):
    """
    覆盖写入某文件的当周市场情报（先删旧，再插入）。
    rows: list[dict], keys: seq, update_time, collector, vendor, category, model,
          config, peripheral, price_tier, our_model, our_config, our_peripheral,
          our_price_tier, notes
    """
    conn = get_db()
    conn.execute(
        "DELETE FROM market_intel WHERE submission_file_id = ?",
        (submission_file_id,)
    )
    for r in rows:
        conn.execute(
            """INSERT INTO market_intel
               (week_start, module_id, user_id, submission_file_id,
                seq, update_time, collector, vendor, category, model,
                config, peripheral, price_tier,
                our_model, our_config, our_peripheral, our_price_tier, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                week_start, module_id, user_id, submission_file_id,
                r.get("seq"), r.get("update_time"), r.get("collector"),
                r.get("vendor"), r.get("category"), r.get("model"),
                r.get("config"), r.get("peripheral"), r.get("price_tier"),
                r.get("our_model"), r.get("our_config"), r.get("our_peripheral"),
                r.get("our_price_tier"), r.get("notes"),
            )
        )
    conn.commit()
    conn.close()
```

- [ ] **Step 3: 实现 `get_market_intel`**

```python
def get_market_intel(week_start=None, module_id=None, vendor=None, category=None, model=None, user_id=None):
    """筛选查询市场情报，返回 list[dict]（含 module_name, display_name）"""
    conn = get_db()
    query = """SELECT mi.*, m.name as module_name, u.display_name
               FROM market_intel mi
               JOIN modules m ON mi.module_id = m.id
               JOIN users u ON mi.user_id = u.id
               WHERE 1=1"""
    params = []
    if week_start:
        query += " AND mi.week_start = ?"
        params.append(week_start)
    if module_id:
        query += " AND mi.module_id = ?"
        params.append(module_id)
    if vendor:
        query += " AND mi.vendor LIKE ?"
        params.append(f"%{vendor}%")
    if category:
        query += " AND mi.category LIKE ?"
        params.append(f"%{category}%")
    if model:
        query += " AND mi.model LIKE ?"
        params.append(f"%{model}%")
    if user_id:
        query += " AND mi.user_id = ?"
        params.append(user_id)
    query += " ORDER BY mi.week_start DESC, mi.vendor, mi.model"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: 实现 `get_model_timeline`**

```python
def get_model_timeline(model, weeks=8):
    """查询某个型号的时间线（近N周）"""
    import datetime
    cutoff = (datetime.datetime.now() - datetime.timedelta(weeks=weeks)).strftime("%Y-%m-%d")
    conn = get_db()
    rows = conn.execute(
        """SELECT mi.*, m.name as module_name, u.display_name
           FROM market_intel mi
           JOIN modules m ON mi.module_id = m.id
           JOIN users u ON mi.user_id = u.id
           WHERE mi.model = ? AND mi.week_start >= ?
           ORDER BY mi.week_start DESC""",
        (model, cutoff)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

- [ ] **Step 5: 测试 DB 函数**

```python
from database_v2 import *
init_db()
# 测试 upsert
rows = [{"vendor": "华为", "category": "服务器", "model": "KunLun", "config": "128核", "notes": "测试"}]
upsert_market_intel("2026-08-03", 3, 1, 999, rows)
# 测试查询
result = get_market_intel(vendor="华为")
assert len(result) >= 1
assert result[0]["model"] == "KunLun"
# 测试时间线
tl = get_model_timeline("KunLun")
assert len(tl) >= 1
# 清理
conn = get_db()
conn.execute("DELETE FROM market_intel WHERE submission_file_id = 999")
conn.commit()
conn.close()
print("All market_intel tests passed!")
```

- [ ] **Step 6: Commit**

```bash
git add weekly-report-system/database_v2.py
git commit -m "feat: market_intel table + CRUD functions"
```

---

### Task 2: 市场情报提取器

**Files:**
- Create: `weekly-report-system/services/analyzer/market_intel_extractor.py`
- Modify: `weekly-report-system/services/analyzer/__init__.py`

**Interfaces:**
- Produces: `extract_market_intel(file_path, module_id) -> list[dict]`
- Consumes: `openpyxl`

- [ ] **Step 1: 创建提取器模块**

```python
"""
市场情报提取器
从销售部周报 Excel 中提取"市场信息（每周反馈新增变化部分）"区域
"""
import openpyxl


def extract_market_intel(file_path, module_id):
    """
    从 Excel 文件中提取市场情报数据。

    定位策略：遍历所有 sheet，在 column A 搜索含"市场信息"的单元格，
    下一行为表头，再下一行起为数据行。

    Args:
        file_path: Excel 文件路径
        module_id: 模块 ID（用于过滤，仅销售部=3）

    Returns:
        list[dict]: 每条记录的字段字典，提取失败返回 []
    """
    if module_id != 3:  # 仅销售部
        return []

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
    except Exception:
        return []

    all_rows = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]

        # 1. 定位"市场信息"section
        header_row = None
        data_start_row = None

        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=1, values_only=True):
            cell_val = str(row[0]) if row[0] else ""
            if "市场信息" in cell_val:
                header_row = row[0].row if hasattr(row[0], 'row') else None
                break

        # 重新定位（使用 cell 对象获取行号）
        header_row = None
        for row_idx in range(1, ws.max_row + 1):
            cell_val = str(ws.cell(row=row_idx, column=1).value or "")
            if "市场信息" in cell_val:
                header_row = row_idx
                break

        if header_row is None:
            continue

        # 2. 表头行 = header_row + 1, 数据起始行 = header_row + 2
        if header_row + 1 > ws.max_row:
            continue

        # 3. 读取数据行
        data_start = header_row + 2
        for row_idx in range(data_start, ws.max_row + 1):
            row_vals = []
            for col_idx in range(1, 15):  # 14 列
                v = ws.cell(row=row_idx, column=col_idx).value
                row_vals.append(str(v).strip() if v is not None else None)

            # 判断空行：前3列全空则停止
            if not any(row_vals[:3]):
                break

            record = {
                "seq": row_vals[0],
                "update_time": row_vals[1],
                "collector": row_vals[2],
                "vendor": row_vals[3],
                "category": row_vals[4],
                "model": row_vals[5],
                "config": row_vals[6],
                "peripheral": row_vals[7],
                "price_tier": row_vals[8],
                "our_model": row_vals[9],
                "our_config": row_vals[10],
                "our_peripheral": row_vals[11],
                "our_price_tier": row_vals[12],
                "notes": row_vals[13],
            }
            all_rows.append(record)

    wb.close()
    return all_rows
```

- [ ] **Step 2: 更新 `__init__.py`**

```python
from .risk_extractor import run_risk_extraction
from .efficiency import compute_efficiency
from .market_intel_extractor import extract_market_intel
```

- [ ] **Step 3: 测试提取器**

```python
from services.analyzer.market_intel_extractor import extract_market_intel
# 用桌面模板文件测试
import os
desktop = os.path.expanduser('~') + '/Desktop'
template = os.path.join(desktop, '销售部周报模板.xlsx')
rows = extract_market_intel(template, 3)
print(f"Extracted {len(rows)} rows")
assert len(rows) == 0  # 模板只有表头无数据
# 用 actual data file if available
print("Extractor test passed!")
```

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/services/analyzer/market_intel_extractor.py weekly-report-system/services/analyzer/__init__.py
git commit -m "feat: market intel extractor — smart section location + 14-column parsing"
```

---

### Task 3: Worker 集成

**Files:**
- Modify: `weekly-report-system/worker.py`

- [ ] **Step 1: 在 `_process_task` 中添加市场情报提取调用**

在 `_process_task` 函数中，风险提取之后（`run_risk_extraction` 调用块之后），添加：

```python
            # Phase 4: 市场情报提取（仅销售部 module_id=3）
            try:
                from services.analyzer.market_intel_extractor import extract_market_intel
                rows = extract_market_intel(sf["original_path"], module_id)
                if rows:
                    from database_v2 import upsert_market_intel
                    upsert_market_intel(
                        week_start=week_start,
                        module_id=module_id,
                        user_id=user_id,
                        submission_file_id=file_id,
                        rows=rows,
                    )
            except Exception as e:
                print(f"[Worker] Market intel extraction failed for file {file_id}: {e}")
```

- [ ] **Step 2: 验证**

```bash
python -m py_compile weekly-report-system/worker.py
```

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/worker.py
git commit -m "feat: integrate market intel extraction into worker pipeline"
```

---

### Task 4: 市场情报 HTML 组件

**Files:**
- Create: `weekly-report-system/static/market_intel.html`

依赖 ECharts CDN，三 Tab 结构（复用 analysis_dashboard 样式模式）。

- [ ] **Step 1: 创建 HTML 组件**

完整的独立 HTML 文件，包含：

**结构:**
- 顶部: 模块筛选下拉 + 周次筛选
- Tab A 总表: 可筛选表格（厂商/分类/型号搜索 + 人员下拉），本周新增标记
- Tab B 热力图: 厂商 × 分类 ECharts heatmap
- Tab C 时间线: 型号下拉 → 近 8 周逐周卡片

**数据注入:**
```javascript
window.addEventListener('message', function(e) {
  if (e.data.type === 'marketIntelData') {
    state = { ...state, ...e.data.payload };
    renderAll();
  }
});
```

**交互:**
- 筛选器联动（选择厂商 → 表+热力图+时间线同步更新）
- 本周新增判定：`vendor + model` 组合在当前周存在但在上周数据中不存在 → "新增"标记
- 型号下拉选项从数据中动态提取去重

**HTML 组件详细规格:**

1. **CSS 样式**: 复用 `analysis_dashboard.html` 的设计语言 — 相同字体、卡片阴影、KPI 色值、表格样式。新增 `.mi-tabs`（子Tab导航）、`.mi-filter-row`（筛选器行）、`.new-badge`（新增标记蓝色标签）、`.timeline-card`（时间线周卡片）

2. **子 Tab 切换**: 三个按钮 `总表 | 热力图 | 型号时间线`，点击切换对应面板显示/隐藏

3. **Tab A 总表**:
   - 筛选行: 周次下拉(searchable)、厂商文本搜索、分类下拉、型号文本搜索、人员下拉、🔍搜索按钮
   - 表格列: 周次 | 人员 | 厂家 | 分类 | 型号 | 主要配置 | 价格 | 对标型号 | 新增标记(蓝色badge) | 备注
   - `is_new` 判定: 后端已计算，前端只渲染

4. **Tab B 热力图**:
   - ECharts heatmap, X轴=分类, Y轴=厂商, 值=条目数
   - 颜色渐变: 浅蓝(1条) → 深红(10+条)
   - 点击热力图格子 → 自动切换到总表并按该厂商+分类筛选

5. **Tab C 型号时间线**:
   - 型号下拉(从数据中提取去重型号列表，按出现次数降序)
   - 选型号后展示近8周记录，每周一张 `.timeline-card` (周标签+表格列出该周该型号所有记录)
   - 周之间用竖线连接形成时间线视觉

6. **数据注入**: `window.postMessage` 接收 `{type: 'marketIntelData', payload: {intel, modules, weekStart}}`
   - `intel`: 全量 `get_market_intel()` 结果 (含 `is_new` 字段由后端预计算)
   - `modules`: 模块列表用于筛选下拉
   - `weekStart`: 当前周起始日期

7. **响应式**: 表格水平滚动，热力图自适应宽度，时间线卡片固定宽度左对齐

- [ ] **Step 2: Commit**

```bash
git add weekly-report-system/static/market_intel.html
git commit -m "feat: market intel HTML component — total table, heatmap, model timeline"
```

---

### Task 5: 领导查阅页 Tab 3 集成

**Files:**
- Modify: `weekly-report-system/pages/leader_browse.py`

- [ ] **Step 1: 添加数据准备函数**

```python
def _prepare_market_intel_data(week_start):
    """准备市场情报数据"""
    conn = get_db()
    all_modules = conn.execute("SELECT id, name FROM modules ORDER BY id").fetchall()
    conn.close()
    
    intel_data = get_market_intel()
    
    # 计算本周新增
    from database_v2 import get_current_week
    current_week, _ = get_current_week()
    prev_week_start = _get_prev_week(current_week)
    prev_data = get_market_intel(week_start=prev_week_start) if prev_week_start else []
    prev_keys = {(r["vendor"] or "", r["model"] or "") for r in prev_data}
    
    for r in intel_data:
        key = (r["vendor"] or "", r["model"] or "")
        r["is_new"] = 1 if (key not in prev_keys and r["week_start"] == current_week) else 0
    
    return {
        "intel": intel_data,
        "modules": [{"id": m["id"], "name": m["name"]} for m in all_modules],
        "weekStart": current_week,
    }


def _get_prev_week(week_start_str):
    """计算前一周的周一日期"""
    from datetime import datetime, timedelta
    dt = datetime.strptime(week_start_str, "%Y-%m-%d")
    prev = dt - timedelta(days=7)
    return prev.strftime("%Y-%m-%d")
```

- [ ] **Step 2: 添加 Tab 3 渲染**

在 `render_leader_browse_page` 中，Tab 2 之后添加：

```python
    with tab3:
        st.caption(f"数据周期: {week_start} ~ {week_end}")
        mi_data = _prepare_market_intel_data(week_start)
        
        html_path = os.path.join(STATIC_DIR, "market_intel.html")
        if os.path.exists(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                mi_html = f.read()
        else:
            st.warning("市场情报组件文件未找到")
            return
        
        inject_script = f"""
        <script>
        window.addEventListener('DOMContentLoaded', function() {{
            window.postMessage({{type: 'marketIntelData', payload: {json.dumps(mi_data, ensure_ascii=False, default=str)}}}, '*');
        }});
        </script>
        """
        full_html = mi_html.replace("</body>", inject_script + "</body>")
        st.components.v1.html(full_html, height=900)
```

同时修改 Tab 定义行：`tab1, tab2, tab3 = st.tabs(["📋 周报查阅", "📊 分析看板", "📡 市场情报"])`

- [ ] **Step 3: 验证**

```bash
python -m py_compile weekly-report-system/pages/leader_browse.py
```

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/pages/leader_browse.py
git commit -m "feat: market intel Tab 3 in leader browse page"
```

---

### Task 6: 端到端验证

- [ ] **Step 1: 启动应用**

```bash
cd weekly-report-system && streamlit run app.py
```

- [ ] **Step 2: 验证流程**
  1. `superior` 登录 → 领导查阅 → 应出现三个 Tab（周报查阅 / 分析看板 / 市场情报）
  2. 切换到"市场情报"Tab → 确认组件加载
  3. 确认总表/热力图/时间线三个子 Tab 可切换
  4. 如无数据：确认数据库 `market_intel` 表存在

- [ ] **Step 3: Commit（如有遗漏修复）**

```bash
git add -A && git commit -m "chore: market intel E2E fixes"
```
