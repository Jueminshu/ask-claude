# 周报系统完整功能 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 4 个模块合并器 + 通用汇总层 + 周报库页面 + 按角色权限的完整周报系统

**Architecture:** 模块合并器层（每种格式独立处理）→ 通用汇总层（跨模块聚合）→ Web 门户（5 页面 + 角色导航）。现有 `excel_merger.py` 改造为配置驱动以复用。

**Tech Stack:** Python 3.12, Streamlit 1.60, SQLite, openpyxl, python-pptx, officecli, PyYAML

## Global Constraints

- 运行环境：Windows 11, Python 3.12
- 前端框架：Streamlit 1.60（不要引入额外前端依赖）
- 数据库：SQLite，文件路径 `data/weekly_report.db`
- Excel 处理：openpyxl（不要引入 pandas 仅用于读写 Excel）
- PPT 处理：python-pptx 或 officecli
- 配置：`config.yaml` 驱动模板差异
- 已有代码风格：遵循 `excel_merger.py` 的命名和注释习惯（中文注释 + 英文变量名）

---

## 文件结构

```
weekly-report-system/
├── app.py                    # [修改] Streamlit 主应用（加周报库页 + 汇总触发）
├── database.py               # [修改] 加 report_archive 表 + 查询函数
├── config.yaml               # [修改] 加各模块列配置
├── main.py                   # [改] CLI 支持多模块
├── merger/
│   ├── __init__.py
│   ├── excel_merger.py       # [修改] 改造为配置驱动（支持多模块列映射）
│   ├── sales_merger.py       # [新建] 三段式销售部合并器
│   ├── ppt_merger.py         # [新建] PPT 合并器（海外BD）
│   └── summary_builder.py    # [新建] 通用汇总层
└── screenshots/              # 已存在，不变
```

App.py 目前 457 行已偏大，本计划中将周报库逻辑拆为独立模块以控制文件大小。

---

### Task 1: 数据库扩展 + 模板配置

**Files:**
- Modify: `weekly-report-system/database.py:90-145`（seed_data 段之后追加）
- Modify: `weekly-report-system/config.yaml`

**Interfaces:**
- Consumes: 现有 `database.py` 的 `get_db()` 已可用
- Produces:
  - `init_db()` 函数需在末尾追加 `report_archive` 表的 CREATE TABLE
  - `get_archive_files(role, user_id, module_id)` — 按角色返回归档文件列表
  - `add_archive_record(week_start, week_end, module_id, file_type, file_path, user_id=None)` — 写入归档
  - `config.yaml` 新增 `module_columns` 节点

- [ ] **Step 1: 给 config.yaml 添加多模块列配置**

在 `config.yaml` 末尾追加：

```yaml
# 模块列映射
module_columns:
  domestic_operator:
    title_pattern: "国内运营商"
    columns:
      A: "序号"
      B: "重点项目"
      C: "子目标/关键举措"
      D: "本周工作进展"
      E: "下周计划"
      F: "风险及求助"
    data_start_row: 3
    header_row: 2

  marketing_ops:
    title_pattern: "营销运营部"
    columns:
      A: "业务模块"
      B: "本周工作进展"
      C: "下周工作计划"
      D: "问题反馈&所需支持"
      E: "备注"
    data_start_row: 3
    header_row: 2

  sales:
    title_pattern: "营销Team"
    sections:
      - name: "日常工作"
        start_row: 2
        end_row: 6
        columns:
          A: "客户"
          B: "本周工作进展"
          C: "下周工作计划"
          D: "需要BU支持事宜"
          E: "市场/竞品信息"
      - name: "质量供应问题"
        start_row: 11
        end_row: 15
        columns:
          A: "客户"
          B: "平台"
          C: "问题描述"
          D: "客户诉求"
          E: "对公司的影响"
          F: "此问题是否重复发生"
      - name: "竞品信息"
        start_row: 21
        end_row: 25
        columns:
          A: "序号"
          B: "更新时间"
          C: "信息收集人"
          D: "厂家"
          E: "分类"
          F: "型号"
          G: "主要配置"
          H: "主要外围配置"
          I: "对T1/T2/T3客户及价格"
          J: "对标我司产品型号"
          K: "主要配置"
          L: "主要外围配置"
          M: "对T1/T2/T3客户及价格"
          N: "补充说明"

  overseas_bd:
    title_pattern: "海外BD"
    format: "ppt"
```

- [ ] **Step 2: 给 database.py 添加 report_archive 表**

在 `database.py` 的 `init_db()` 函数末尾（第 85 行 `conn.close()` 之前），在 `CREATE TABLE IF NOT EXISTS weekly_summaries` 块的 `conn.executescript` 内追加：

```sql
-- 周报库归档索引表
CREATE TABLE IF NOT EXISTS report_archive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    module_id INTEGER,
    file_type TEXT NOT NULL DEFAULT 'individual',
    file_path TEXT NOT NULL,
    user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (module_id) REFERENCES modules(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

- [ ] **Step 3: 添加归档查询函数**

在 `database.py` 末尾追加：

```python
def get_archive_files(role, user_id, module_id=None):
    """
    按角色获取周报库归档文件列表。
    member: 只看本人的 individual 文件
    leader: 本团队 individual + 本模块 module_summary
    admin/superior: 全部
    """
    conn = get_db()
    if role == "member":
        rows = conn.execute(
            """SELECT ra.*, m.name as module_name
               FROM report_archive ra
               LEFT JOIN modules m ON ra.module_id = m.id
               WHERE ra.user_id = ? AND ra.file_type = 'individual'
               ORDER BY ra.week_start DESC, ra.created_at DESC""",
            (user_id,)
        ).fetchall()
    elif role == "leader":
        rows = conn.execute(
            """SELECT ra.*, m.name as module_name
               FROM report_archive ra
               LEFT JOIN modules m ON ra.module_id = m.id
               WHERE ra.module_id = ?
                 AND ra.file_type IN ('individual', 'module_summary')
               ORDER BY ra.week_start DESC, ra.created_at DESC""",
            (module_id,)
        ).fetchall()
    else:  # admin, superior
        rows = conn.execute(
            """SELECT ra.*, m.name as module_name, u.display_name
               FROM report_archive ra
               LEFT JOIN modules m ON ra.module_id = m.id
               LEFT JOIN users u ON ra.user_id = u.id
               ORDER BY ra.week_start DESC, ra.created_at DESC"""
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_archive_record(week_start, week_end, module_id, file_type, file_path, user_id=None):
    """写入归档记录"""
    conn = get_db()
    conn.execute(
        """INSERT INTO report_archive (week_start, week_end, module_id, file_type, file_path, user_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (week_start, week_end, module_id, file_type, file_path, user_id)
    )
    conn.commit()
    conn.close()
```

- [ ] **Step 4: 验证数据库**

```bash
cd weekly-report-system && python -c "
from database import init_db, get_archive_files, add_archive_record
init_db()
# 测试写入
add_archive_record('2026-07-27', '2026-08-02', 1, 'module_summary', 'output/test.xlsx')
records = get_archive_files('admin', 1)
print('Records:', len(records))
for r in records:
    print(dict(r))
"
```

- [ ] **Step 5: Commit**

```bash
git add weekly-report-system/database.py weekly-report-system/config.yaml
git commit -m "feat: 添加report_archive表+多模块列配置+归档查询函数"
```

---

### Task 2: Excel 合并器改造为配置驱动

**Files:**
- Modify: `weekly-report-system/merger/excel_merger.py:20-28`（DOMESTIC_COLUMNS → module_name 参数化）

**Interfaces:**
- Consumes: `config.yaml` 中的 `module_columns` 节点
- Produces:
  - `ExcelMerger(module_id: str)` — 构造函数接受模块 ID 字符串
  - `merge() -> dict` — 返回标准化摘要 dict（含 `module_name`, `total_people`, `submitted_count`, `submission_rate`, `risk_items`, `key_projects`, `output_file`, `deadline_passed`）
  - `merge_from_uploads(module_id, week_start, week_end) -> str` — 从 Web 上传目录合并

- [ ] **Step 1: 改造构造函数，从 config 读取列配置**

```python
def __init__(self, module_id, config_path="config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        self.config = yaml.safe_load(f)
    self.module_id = module_id
    self.module_name = self._get_module_name(module_id)
    all_columns = self.config.get("module_columns", {})
    self.columns = all_columns.get(module_id, {}).get("columns", {})
    self.data_start_row = all_columns.get(module_id, {}).get("data_start_row", 3)
    self.header_row = all_columns.get(module_id, {}).get("header_row", 2)
    if not self.columns:
        raise ValueError(f"模块 {module_id} 未配置列映射")
```

- [ ] **Step 2: 修改 `merge_from_uploads` 方法签名**

当前 `merge_from_uploads(module_id, week_start, week_end)` 已接收 module_id。将内部调用 `self.merge(module_id)` 改为直接使用 `self.module_id`。

- [ ] **Step 3: 修改 merge 方法返回摘要 dict**

当前 `merge()` 返回文件路径字符串。改为返回 dict：

```python
def merge(self) -> dict:
    """合并并返回摘要"""
    output_path = self._do_merge()  # 原 merge 逻辑
    # 从合并结果收集摘要
    summary = self._build_summary(output_path)
    return summary

def _build_summary(self, output_path) -> dict:
    """从合并文件提取摘要数据"""
    wb = load_workbook(output_path)
    # 收集已提交人员名（从目录 Sheet 读取）
    toc_sheet = wb.get("目录")
    submitted_names = []
    if toc_sheet:
        for row in toc_sheet.iter_rows(min_row=2, values_only=True):
            if row[1]:
                submitted_names.append(str(row[1]))
    total = self.total_people if hasattr(self, 'total_people') else len(submitted_names)

    # 收集风险项（从分析 Sheet 或风险列）
    risk_items = []
    for name in submitted_names:
        sheet = wb.get(name)
        if sheet:
            # F 列或 D 列是风险列，根据模块配置判断
            risk_col = self._get_risk_column()
            for row in sheet.iter_rows(min_row=2, values_only=True):
                risk_text = str(row[risk_col]).strip() if row[risk_col] else ""
                if risk_text and risk_text != "None":
                    risk_items.append(f"{name}: {risk_text[:80]}")

    submitted_count = len(submitted_names)
    return {
        "module_name": self.module_name,
        "total_people": total,
        "submitted_count": submitted_count,
        "submission_rate": f"{round(submitted_count / max(total, 1) * 100)}%",
        "risk_items": risk_items,
        "key_projects": [],  # 后续分析阶段填充
        "output_file": output_path,
        "deadline_passed": False,
    }
```

- [ ] **Step 4: 更新 `app.py` 中对 `ExcelMerger` 的调用**

`app.py` 第 303-313 行的 `review_page` 函数中，`ExcelMerger()` 调用改为 `ExcelMerger(module_id)`：

```python
# 原: merger = ExcelMerger()
# 改: 使用 selected_module 实例化
merger = ExcelMerger(str(selected_module))
```

- [ ] **Step 5: 运行测试验证**

```bash
cd weekly-report-system
# 国内运营商模块测试
python -c "
from merger.excel_merger import ExcelMerger
m = ExcelMerger('domestic_operator')
print('模块名:', m.module_name)
print('列配置:', m.columns)
"
```

- [ ] **Step 6: Commit**

```bash
git add weekly-report-system/merger/excel_merger.py weekly-report-system/app.py
git commit -m "refactor: ExcelMerger改造为配置驱动，merge()返回摘要dict"
```

---

### Task 3: 营销运营部合并器（复用引擎）

**Files:**
- Verify: `weekly-report-system/config.yaml`（Task 1 已配置 `marketing_ops` 列）
- Modify: `weekly-report-system/app.py:228-314`（review_page 中模块选择器）

**Interfaces:**
- Consumes: `ExcelMerger('marketing_ops')` 可直接工作
- Produces: 营销运营部模块可以正常合并

- [ ] **Step 1: 验证模块选择器覆盖所有模块**

`app.py` 第 232-239 行 `review_page` 中，确认模块选择器已从数据库动态加载所有模块：

```python
# 已有代码（第 232-239 行）:
modules = conn.execute("SELECT * FROM modules").fetchall()
selected_module = st.selectbox(
    "选择模块",
    [m["id"] for m in modules],
    format_func=lambda x: _get_module_name(x),
)
```

无需改动，已支持动态加载。

- [ ] **Step 2: 端到端测试（营销运营部示例文件）**

```bash
cd weekly-report-system

# 创建测试目录
mkdir -p data/uploads/2026-07-27/2/

# 复制模板作为测试数据
cp "/c/Users/hua'wei/Desktop/营销运营部周报模板.xlsx" \
   data/uploads/2026-07-27/2/成员1_营销运营部周报模板.xlsx

# 用 CLI 合并
python main.py --config config.yaml merge --module marketing_ops 2>&1
# 应生成 output/ 下的汇总文件
```

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/app.py
git commit -m "feat: 营销运营部合并器（复用配置驱动ExcelMerger）"
```

---

### Task 4: 销售部三段式合并器

**Files:**
- Create: `weekly-report-system/merger/sales_merger.py`

**Interfaces:**
- Consumes: `config.yaml` 中 `module_columns.sales.sections` 配置
- Produces:
  - `SalesMerger(module_id='sales', config_path='config.yaml')` — 初始化
  - `merge(upload_dir: str, output_dir: str, week_start, week_end) -> dict` — 三段式合并 + 返回摘要
  - 输出文件：`output/销售部_周报汇总_YYYYMMDD.xlsx`

- [ ] **Step 1: 创建 sales_merger.py 骨架**

```python
"""
销售部合并器
处理三段式 Excel 模板：日常工作 / 质量供应问题 / 竞品信息
每个 Section 独立合并为一张大表
"""
import os
import yaml
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


class SalesMerger:
    """销售部三段式 Excel 合并器"""

    HEADER_FONT = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
    HEADER_FILL = PatternFill(start_color="2B579A", end_color="2B579A", fill_type="solid")
    CELL_ALIGNMENT = Alignment(vertical="top", wrap_text=True)
    THIN_BORDER = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin")
    )

    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        sales_cfg = self.config.get("module_columns", {}).get("sales", {})
        self.sections = sales_cfg.get("sections", [])

    def merge(self, upload_dir, output_dir, week_start, week_end):
        """
        扫描 upload_dir 中的所有 .xlsx 文件，按三段式分段合并。
        返回标准化摘要 dict。
        """
        files = [f for f in os.listdir(upload_dir) if f.endswith((".xlsx", ".xls"))]
        if not files:
            return None

        wb = Workbook()
        wb.remove(wb.active)  # 删除默认 Sheet

        # 创建目录 Sheet
        toc_sheet = wb.create_sheet("📑 目录", 0)
        self._write_toc(toc_sheet, files)

        # 每个 Section 创建一张总表
        person_data = {}  # {section_name: [(person_name, rows)]}

        for section in self.sections:
            section_name = section["name"]
            sheet = wb.create_sheet(section_name)
            self._write_section_header(sheet, section)
            person_data[section_name] = []

            row_offset = 1  # header at row 1
            for fname in files:
                person_name = self._extract_person_name(fname)
                file_path = os.path.join(upload_dir, fname)
                src = load_workbook(file_path, data_only=True)
                src_sheet = src[src.sheetnames[0]]  # 每人一个 Sheet

                data_rows = self._extract_section_rows(
                    src_sheet,
                    section["start_row"],
                    section["end_row"]
                )
                if data_rows:
                    person_data[section_name].append((person_name, data_rows))
                    for dr in data_rows:
                        row_offset += 1
                        sheet.cell(row=row_offset, column=1, value=person_name)
                        for ci, val in enumerate(dr, start=2):
                            sheet.cell(row=row_offset, column=ci, value=val)

        # 分析 Sheet
        self._build_analysis_sheet(wb, files, person_data)

        # 保存
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"销售部_周报汇总_{week_end}.xlsx")
        wb.save(output_path)

        return self._build_summary(files, person_data, output_path, week_start, week_end)
```

- [ ] **Step 2: 实现核心方法**

```python
def _extract_person_name(self, filename):
    """从文件名提取姓名，如 '时间+营销TeamX-weekY-张三周报.xlsx' → '张三'"""
    name = os.path.splitext(filename)[0]
    # 尝试匹配常见模式
    import re
    # 匹配最后的 "XXX周报"
    m = re.search(r'[周报weekly]*([一-龥]{2,4})周报', name)
    if m:
        return m.group(1)
    # 回退：取尾部中文部分
    return name.split("-")[-1].replace("周报", "") if "-" in name else "未知"


def _extract_section_rows(self, sheet, start_row, end_row):
    """
    从 Sheet 中提取指定区块的数据行。
    跳过表头行和空行。
    start_row/end_row 是 1-based（Excel 行号）。
    """
    rows = []
    for row_idx in range(start_row + 1, end_row + 1):  # start_row 是表头
        row_data = []
        all_empty = True
        for col_idx in range(1, sheet.max_column + 1):
            val = sheet.cell(row=row_idx, column=col_idx).value
            if val is not None and str(val).strip():
                all_empty = False
            row_data.append(val)
        if not all_empty:
            rows.append(row_data)
    return rows


def _write_toc(self, sheet, files):
    """写目录 Sheet"""
    sheet.cell(row=1, column=1, value="销售部周报汇总").font = Font(name="微软雅黑", size=14, bold=True)
    sheet.cell(row=2, column=1, value="序号")
    sheet.cell(row=2, column=2, value="提交人员")
    for i, fname in enumerate(files):
        row_idx = 3 + i
        name = self._extract_person_name(fname)
        sheet.cell(row=row_idx, column=1, value=i + 1)
        sheet.cell(row=row_idx, column=2, value=name)


def _write_section_header(self, sheet, section):
    """写 Section 表头"""
    cols = list(section["columns"].values())
    for ci, col_name in enumerate(cols, start=1):
        cell = sheet.cell(row=1, column=ci, value=col_name)
        cell.font = self.HEADER_FONT
        cell.fill = self.HEADER_FILL
        cell.border = self.THIN_BORDER
    # A 列设为「提交人」
    sheet.cell(row=1, column=1, value="提交人").font = self.HEADER_FONT
    sheet.cell(row=1, column=1).fill = self.HEADER_FILL


def _build_analysis_sheet(self, wb, files, person_data):
    """生成分析 Sheet"""
    sheet = wb.create_sheet("📊 本周分析")
    sheet.cell(row=1, column=1, value="销售部本周分析").font = Font(name="微软雅黑", size=14, bold=True)
    submitted = len(files)
    total = self.config.get("modules", {}).get("sales", {}).get("total_people", submitted)
    sheet.cell(row=3, column=1, value=f"提交率: {submitted}/{total}")
    sheet.cell(row=4, column=1, value=f"各Section数据量:")
    for i, (section_name, data) in enumerate(person_data.items()):
        total_rows = sum(len(rows) for _, rows in data)
        sheet.cell(row=5 + i, column=1, value=f"  {section_name}: {total_rows} 条")


def _build_summary(self, files, person_data, output_path, week_start, week_end):
    """构建标准化摘要"""
    total = self.config.get("modules", {}).get("sales", {}).get("total_people", len(files))
    submitted = len(files)
    # 收集风险项（Section 2: 质量供应问题）
    risk_items = []
    section2_data = person_data.get("质量供应问题", [])
    for person_name, rows in section2_data:
        for row in rows:
            desc = str(row[2]) if len(row) > 2 else ""
            if desc.strip():
                risk_items.append(f"{person_name}: {desc[:80]}")
    return {
        "module_name": "销售部",
        "total_people": total,
        "submitted_count": submitted,
        "submission_rate": f"{round(submitted / max(total, 1) * 100)}%",
        "risk_items": risk_items,
        "key_projects": [],
        "output_file": output_path,
        "deadline_passed": False,
    }
```

- [ ] **Step 3: 单元测试（用桌面模板文件）**

```python
# 在终端直接运行
cd weekly-report-system
python -c "
from merger.sales_merger import SalesMerger
import os, tempfile, shutil

# 复制模板做测试
test_dir = tempfile.mkdtemp()
shutil.copy('/c/Users/hua\'wei/Desktop/销售部周报模板.xlsx',
            os.path.join(test_dir, '时间+营销Team1-week27-张三周报.xlsx'))

m = SalesMerger()
result = m.merge(test_dir, 'output', '2026-07-27', '2026-08-02')
if result:
    print('合并成功:', result['output_file'])
    print('提交率:', result['submission_rate'])
    print('风险项:', len(result['risk_items']))
else:
    print('没有找到文件')
shutil.rmtree(test_dir)
"
```

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/merger/sales_merger.py
git commit -m "feat: 销售部三段式合并器（日常工作/质量供应/竞品信息）"
```

---

### Task 5: PPT 合并器（海外 BD）

**Files:**
- Create: `weekly-report-system/merger/ppt_merger.py`

**Interfaces:**
- Consumes: python-pptx 库，`config.yaml` 中 `module_columns.overseas_bd` 配置
- Produces:
  - `PptMerger(config_path='config.yaml')` — 初始化
  - `merge(upload_dir, output_dir, week_start, week_end) -> dict` — 合并 PPT + 返回摘要
  - 输出文件：`output/海外BD_周报汇总_YYYYMMDD.pptx`

- [ ] **Step 1: 确保 python-pptx 已安装**

```bash
pip install python-pptx
# 若已安装则跳过
```

- [ ] **Step 2: 创建 ppt_merger.py**

```python
"""
PPT 合并器（海外 BD）
将多人 PPT 统一字体后合并为单一 PPT，每人幻灯片前插入分隔页
"""
import os
import re
import yaml
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.slide import SlideLayout


class PptMerger:
    """PPT 合并器"""

    CN_FONT = "等线"
    EN_FONT = "Arial"
    FONT_SIZE_BODY = Pt(12)

    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def merge(self, upload_dir, output_dir, week_start, week_end):
        """
        扫描 upload_dir 中的 .pptx 文件，统一字体后合并。
        返回标准化摘要 dict。
        """
        ppt_files = sorted([f for f in os.listdir(upload_dir)
                           if f.endswith((".pptx", ".ppt"))])
        if not ppt_files:
            return None

        merged = Presentation()

        for fname in ppt_files:
            person_name = self._extract_person_name(fname)

            # 插入分隔页
            self._add_divider_slide(merged, person_name)

            # 复制该人的所有幻灯片
            file_path = os.path.join(upload_dir, fname)
            src_prs = Presentation(file_path)
            for src_slide in src_prs.slides:
                self._copy_slide(merged, src_slide)

        # 统一字体
        self._unify_fonts(merged)

        # 保存
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"海外BD_周报汇总_{week_end}.pptx")
        merged.save(output_path)

        return self._build_summary(ppt_files, output_path, week_start, week_end)

    def _extract_person_name(self, filename):
        """从文件名提取姓名"""
        name = os.path.splitext(filename)[0]
        m = re.search(r'([一-龥]{2,4})', name)
        if m:
            return m.group(1)
        return name.split("-")[-1] if "-" in name else name

    def _add_divider_slide(self, prs, person_name):
        """插入分隔页"""
        layout = prs.slide_layouts[6]  # blank layout
        slide = prs.slides.add_slide(layout)

        left = Inches(1)
        top = Inches(2.5)
        width = Inches(8)
        height = Inches(1.5)

        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        p = tf.paragraphs[0]
        p.text = person_name
        p.font.size = Pt(36)
        p.font.bold = True
        p.font.name = self.CN_FONT
        p.alignment = PP_ALIGN.CENTER

    def _copy_slide(self, dest_prs, src_slide):
        """复制幻灯片内容到目标演示文稿"""
        # 使用 blank layout
        layout = dest_prs.slide_layouts[6]
        dest_slide = dest_prs.slides.add_slide(layout)

        # 复制 shapes
        for shape in src_slide.shapes:
            if shape.has_text_frame:
                txBox = dest_slide.shapes.add_textbox(
                    shape.left, shape.top, shape.width, shape.height
                )
                tf = txBox.text_frame
                tf.word_wrap = shape.text_frame.word_wrap
                for i, src_para in enumerate(shape.text_frame.paragraphs):
                    if i == 0:
                        p = tf.paragraphs[0]
                    else:
                        p = tf.add_paragraph()
                    p.text = src_para.text
                    p.alignment = src_para.alignment

    def _unify_fonts(self, prs):
        """统一所有幻灯片字体"""
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        for run in para.runs:
                            current_font = run.font.name or ""
                            # 检测中文字符 → 等线
                            if re.search(r'[一-龥]', run.text):
                                run.font.name = self.CN_FONT
                            else:
                                run.font.name = self.EN_FONT
                            run.font.size = self.FONT_SIZE_BODY

    def _build_summary(self, files, output_path, week_start, week_end):
        return {
            "module_name": "海外BD",
            "total_people": len(files),
            "submitted_count": len(files),
            "submission_rate": f"{len(files)}/{len(files)}",
            "risk_items": [],
            "key_projects": [],
            "output_file": output_path,
            "deadline_passed": False,
        }
```

- [ ] **Step 3: 验证导入**

```bash
cd weekly-report-system
python -c "from merger.ppt_merger import PptMerger; m = PptMerger(); print('PptMerger loaded')"
```

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/merger/ppt_merger.py
git commit -m "feat: PPT合并器（海外BD，统一字体+分隔页+拼接）"
```

---

### Task 6: 通用汇总层

**Files:**
- Create: `weekly-report-system/merger/summary_builder.py`

**Interfaces:**
- Consumes: 4 个合并器的标准化摘要 dict（`get_summary()` 返回值）
- Produces:
  - `SummaryBuilder(output_dir='output')` — 初始化
  - `build_total_summary(summaries: list[dict], week_start, week_end) -> str` — 生成总汇总 Excel，返回文件路径

- [ ] **Step 1: 创建 summary_builder.py**

```python
"""
通用汇总层
输入：4 个模块的摘要数据
输出：四模块总汇总 Excel（含执行摘要首页）
"""

import os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side


class SummaryBuilder:
    """通用汇总构建器"""

    HEADER_FONT = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
    HEADER_FILL = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
    CELL_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)
    TITLE_FONT = Font(name="微软雅黑", size=16, bold=True)
    THIN_BORDER = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin")
    )
    WARN_FILL = PatternFill(start_color="FFE0E0", end_color="FFE0E0", fill_type="solid")

    def __init__(self, output_dir="output"):
        self.output_dir = output_dir

    def build_total_summary(self, summaries, week_start, week_end):
        """
        summaries: list[dict]，每个 dict 是一个模块的合并摘要
        返回输出文件路径
        """
        if not summaries:
            return None

        wb = Workbook()
        ws = wb.active
        ws.title = "📊 执行摘要"

        self._write_executive_header(ws, week_start, week_end)
        self._write_module_table(ws, summaries)
        self._write_risk_section(ws, summaries)
        self._write_key_projects_section(ws, summaries)

        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, f"四模块周报总汇总_{week_end}.xlsx")
        wb.save(output_path)
        return output_path

    def _write_executive_header(self, ws, week_start, week_end):
        """写执行摘要标题"""
        ws.merge_cells("A1:F1")
        title_cell = ws.cell(row=1, column=1, value=f"营销运作部 周报总汇总")
        title_cell.font = self.TITLE_FONT
        title_cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.merge_cells("A2:F2")
        ws.cell(row=2, column=1, value=f"周期: {week_start} ~ {week_end}").font = Font(size=11)

    def _write_module_table(self, ws, summaries):
        """写四模块提交一览表"""
        headers = ["模块", "应提交", "已提交", "提交率", "风险数"]
        for ci, h in enumerate(headers, start=1):
            cell = ws.cell(row=4, column=ci, value=h)
            cell.font = self.HEADER_FONT
            cell.fill = self.HEADER_FILL
            cell.border = self.THIN_BORDER
            cell.alignment = self.CELL_ALIGNMENT

        for ri, s in enumerate(summaries):
            row_idx = 5 + ri
            ws.cell(row=row_idx, column=1, value=s["module_name"]).border = self.THIN_BORDER
            ws.cell(row=row_idx, column=2, value=s["total_people"]).border = self.THIN_BORDER
            ws.cell(row=row_idx, column=3, value=s["submitted_count"]).border = self.THIN_BORDER
            rate_cell = ws.cell(row=row_idx, column=4, value=s["submission_rate"])
            rate_cell.border = self.THIN_BORDER
            # 提交率低于 80% 标红
            rate_num = int(s["submission_rate"].replace("%", ""))
            if rate_num < 80:
                rate_cell.fill = self.WARN_FILL
            ws.cell(row=row_idx, column=5, value=len(s["risk_items"])).border = self.THIN_BORDER

        # 总提交率
        total_row = 5 + len(summaries)
        total_people = sum(s["total_people"] for s in summaries)
        total_submitted = sum(s["submitted_count"] for s in summaries)
        ws.cell(row=total_row, column=1, value="合计").font = Font(bold=True)
        ws.cell(row=total_row, column=2, value=total_people)
        ws.cell(row=total_row, column=3, value=total_submitted)
        rate = f"{round(total_submitted / max(total_people, 1) * 100)}%"
        ws.cell(row=total_row, column=4, value=rate)
        ws.cell(row=total_row, column=5, value=sum(len(s["risk_items"]) for s in summaries))

    def _write_risk_section(self, ws, summaries):
        """汇集所有风险项"""
        start_row = 5 + len(summaries) + 3
        ws.merge_cells(f"A{start_row}:E{start_row}")
        ws.cell(row=start_row, column=1, value="⚠️ 风险关注").font = Font(size=13, bold=True)

        all_risks = []
        for s in summaries:
            for r in s["risk_items"]:
                all_risks.append(f"[{s['module_name']}] {r}")

        if all_risks:
            for i, risk in enumerate(all_risks):
                row_idx = start_row + 1 + i
                ws.cell(row=row_idx, column=1, value=f"{i+1}. {risk}")
        else:
            ws.cell(row=start_row + 1, column=1, value="本周无风险项").font = Font(color="999999")

    def _write_key_projects_section(self, ws, summaries):
        """汇集重点项目"""
        # 在风险区之后
        risk_count = sum(len(s["risk_items"]) for s in summaries) + 2
        start_row = 5 + len(summaries) + 3 + risk_count
        ws.merge_cells(f"A{start_row}:E{start_row}")
        ws.cell(row=start_row, column=1, value="📋 本周重点事项").font = Font(size=13, bold=True)

        all_projects = []
        for s in summaries:
            for p in s["key_projects"]:
                all_projects.append(f"[{s['module_name']}] {p}")

        if all_projects:
            for i, proj in enumerate(all_projects):
                ws.cell(row=start_row + 1 + i, column=1, value=f"{i+1}. {proj}")
        else:
            ws.cell(row=start_row + 1, column=1, value="暂无记录").font = Font(color="999999")
```

- [ ] **Step 2: 单元测试**

```bash
cd weekly-report-system
python -c "
from merger.summary_builder import SummaryBuilder

summaries = [
    {'module_name': '国内运营商', 'total_people': 10, 'submitted_count': 9, 'submission_rate': '90%', 'risk_items': ['风险A', '风险B'], 'key_projects': ['项目X']},
    {'module_name': '营销运营部', 'total_people': 15, 'submitted_count': 12, 'submission_rate': '80%', 'risk_items': [], 'key_projects': []},
    {'module_name': '销售部', 'total_people': 35, 'submitted_count': 22, 'submission_rate': '63%', 'risk_items': ['供应问题1'], 'key_projects': []},
    {'module_name': '海外BD', 'total_people': 10, 'submitted_count': 8, 'submission_rate': '80%', 'risk_items': [], 'key_projects': []},
]

builder = SummaryBuilder()
output = builder.build_total_summary(summaries, '2026-07-27', '2026-08-02')
print('总汇总生成:', output)
"
```

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/merger/summary_builder.py
git commit -m "feat: 通用汇总层（四模块总汇总Excel+执行摘要首页）"
```

---

### Task 7: 周报库页面

**Files:**
- Create: `weekly-report-system/archive_page.py`（独立模块避免 app.py 进一步膨胀）
- Modify: `weekly-report-system/app.py:110-119`（导航路由加入周报库）

**Interfaces:**
- Consumes: `database.py` 中的 `get_archive_files()`, `add_archive_record()`
- Produces: `render_archive_page(user)` — 可复用的 Streamlit 页面函数

- [ ] **Step 1: 创建 archive_page.py**

```python
"""
周报库页面
按角色展示归档周报，支持按周筛选和下载
"""
import os
import streamlit as st
from database import get_archive_files, get_db


def render_archive_page(user):
    """渲染周报库页面"""
    st.title("📚 周报库")

    role = user["role"]
    module_id = user.get("module_id")

    # 获取所有历史周期（从 archive 表和 submissions 表）
    conn = get_db()
    weeks = conn.execute(
        """SELECT DISTINCT week_start, week_end FROM report_archive
           UNION
           SELECT DISTINCT week_start, week_end FROM submissions
           ORDER BY week_start DESC"""
    ).fetchall()
    conn.close()

    if not weeks:
        st.info("暂无归档数据")
        return

    # 周期筛选
    week_options = [f"{w['week_start']} ~ {w['week_end']}" for w in weeks]
    selected_week = st.selectbox("选择周期", week_options)

    if selected_week:
        week_start, week_end = selected_week.split(" ~ ")

        # 按角色加载归档文件
        records = get_archive_files(role, user["id"], module_id)

        # 过滤当前选中的周期
        filtered = [r for r in records
                    if r["week_start"] == week_start and r["week_end"] == week_end]

        if not filtered:
            st.info(f"该周期暂无归档文件")
            return

        # 分组展示
        individual_files = [r for r in filtered if r["file_type"] == "individual"]
        summary_files = [r for r in filtered if r["file_type"] == "module_summary"]
        total_files = [r for r in filtered if r["file_type"] == "total_summary"]

        # 个人周报
        if individual_files:
            st.subheader("📄 个人周报")
            for r in individual_files:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    col1.markdown(f"**{r.get('display_name', '成员')}** — {r.get('module_name', '')}")
                    col1.caption(f"上传时间: {r['created_at']}")
                    _file_download_button(col2, r["file_path"])

        # 团队汇总
        if summary_files:
            st.subheader("📊 模块汇总")
            for r in summary_files:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    col1.markdown(f"**{r.get('module_name', '')}** — 周期: {r['week_start']}~{r['week_end']}")
                    _file_download_button(col2, r["file_path"])

        # 总汇总
        if total_files:
            st.subheader("📋 四模块总汇总")
            for r in total_files:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    col1.markdown(f"**营销运作部总汇总** — {r['week_start']}~{r['week_end']}")
                    _file_download_button(col2, r["file_path"])


def _file_download_button(col, file_path):
    """渲染下载按钮（如果文件存在）"""
    if os.path.exists(file_path):
        fname = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            col.download_button(
                label="📥 下载",
                data=f,
                file_name=fname,
                key=f"dl_{file_path}",
            )
    else:
        col.caption("文件已删除")
```

- [ ] **Step 2: 在 app.py 中集成周报库页面**

在 `app.py` 的 `main_app()` 函数（第 110-119 行）中加入周报库路由，同时在 `_get_pages()` 中为所有角色添加周报库入口：

`_get_pages()` 修改（第 126-138 行）：

```python
def _get_pages(role):
    pages = []
    pages.append("📤 上传周报")
    pages.append("📚 周报库")     # 新增，所有角色可见
    pages.append("📋 提交历史")

    if role == "admin":
        pages.append("✅ 审核周报")
        pages.append("👥 团队周报")
        pages.append("🔧 系统管理")
    elif role == "leader":
        pages.append("👥 团队周报")

    return pages
```

`main_app()` 中的路由（第 110-119 行）追加：

```python
if "周报库" in page:
    from archive_page import render_archive_page
    render_archive_page(user)
elif "上传周报" in page:
    ...
```

- [ ] **Step 3: 验证页面加载**

启动 Streamlit（或使用已有运行实例 `http://localhost:8501`），刷新页面，登录 admin 确认「周报库」出现在导航中。

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/archive_page.py weekly-report-system/app.py
git commit -m "feat: 周报库页面（按角色查看归档，周期筛选+下载）"
```

---

### Task 8: 管理员汇总触发 + app.py 集成

**Files:**
- Modify: `weekly-report-system/app.py:228-314`（review_page → 汇总触发逻辑）
- Modify: `weekly-report-system/main.py`（CLI 支持多模块）

**Interfaces:**
- Consumes: 四个合并器 + `SummaryBuilder` + `add_archive_record()`
- Produces: 管理员点击「生成本周汇总」→ 跑完所有合并器 → 生成总汇总 → 写入归档

- [ ] **Step 1: 重写 app.py 中 review_page 的「生成本周汇总」按钮逻辑**

替换 `app.py` 第 300-314 行：

```python
# 生成汇总按钮
st.divider()
if st.button("📊 生成本周汇总", type="primary", use_container_width=True):
    with st.spinner("正在生成汇总..."):

        # 1. 运行所有模块合并器
        from merger.excel_merger import ExcelMerger
        from merger.sales_merger import SalesMerger
        from merger.ppt_merger import PptMerger
        from merger.summary_builder import SummaryBuilder
        from database import add_archive_record
        import os

        summaries = []
        upload_base = os.path.join(os.path.dirname(__file__), "data", "uploads", week_start)

        # Excel 模块
        for module_id, module_key in [(1, "domestic_operator"), (2, "marketing_ops")]:
            upload_dir = os.path.join(upload_base, str(module_id))
            if os.path.isdir(upload_dir) and os.listdir(upload_dir):
                merger = ExcelMerger(module_key)
                result = merger.merge_from_uploads(str(module_id), week_start, week_end)
                if result:
                    summaries.append(result)
                    add_archive_record(week_start, week_end, module_id, "module_summary", result["output_file"])

        # 销售部（模块3）
        upload_dir = os.path.join(upload_base, "3")
        if os.path.isdir(upload_dir) and os.listdir(upload_dir):
            sales_merger = SalesMerger()
            result = sales_merger.merge(
                upload_dir=upload_dir,
                output_dir=os.path.join(os.path.dirname(__file__), "output"),
                week_start=week_start,
                week_end=week_end
            )
            if result:
                summaries.append(result)
                add_archive_record(week_start, week_end, 3, "module_summary", result["output_file"])

        # 海外BD（模块4）
        upload_dir = os.path.join(upload_base, "4")
        if os.path.isdir(upload_dir) and os.listdir(upload_dir):
            ppt_merger = PptMerger()
            result = ppt_merger.merge(
                upload_dir=upload_dir,
                output_dir=os.path.join(os.path.dirname(__file__), "output"),
                week_start=week_start,
                week_end=week_end
            )
            if result:
                summaries.append(result)
                add_archive_record(week_start, week_end, 4, "module_summary", result["output_file"])

        # 2. 生成总汇总
        if summaries:
            builder = SummaryBuilder()
            total_path = builder.build_total_summary(
                summaries, week_start, week_end
            )
            if total_path:
                add_archive_record(week_start, week_end, None, "total_summary", total_path)
                st.success(f"✅ 总汇总生成完毕: {total_path}")
        else:
            st.warning("本周暂无提交数据，无法生成汇总")
```

- [ ] **Step 2: 确认 Streamlit 运行正常**

访问 `http://localhost:8501`，以 admin 登录 → 审核周报页 → 点击「生成本周汇总」。

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/app.py
git commit -m "feat: 管理员一键生成四模块汇总+总汇总+归档"
```

---

### Task 9: 端到端集成测试 + 收尾

**Files:**
- Modify: `weekly-report-system/requirements.txt`（追加 python-pptx）

- [ ] **Step 1: 更新 requirements.txt**

```bash
cd weekly-report-system
echo "python-pptx>=0.6.21" >> requirements.txt
```

- [ ] **Step 2: 全局导入测试**

```bash
cd weekly-report-system
python -c "
# 验证所有模块可导入
from database import init_db, seed_data, get_archive_files, add_archive_record
from merger.excel_merger import ExcelMerger
from merger.sales_merger import SalesMerger
from merger.ppt_merger import PptMerger
from merger.summary_builder import SummaryBuilder
from archive_page import render_archive_page

init_db()
seed_data()
print('All modules imported successfully')
"
```

- [ ] **Step 3: 全流程端到端测试（模拟数据）**


```bash
python -c "
from merger.summary_builder import SummaryBuilder
summaries = [
    {'module_name': '国内运营商', 'total_people': 10, 'submitted_count': 9, 'submission_rate': '90%', 'risk_items': ['资源不足'], 'key_projects': ['项目A']},
    {'module_name': '营销运营部', 'total_people': 15, 'submitted_count': 12, 'submission_rate': '80%', 'risk_items': [], 'key_projects': []},
    {'module_name': '销售部', 'total_people': 35, 'submitted_count': 22, 'submission_rate': '63%', 'risk_items': ['芯片交付'], 'key_projects': []},
    {'module_name': '海外BD', 'total_people': 10, 'submitted_count': 8, 'submission_rate': '80%', 'risk_items': [], 'key_projects': []},
]
b = SummaryBuilder()
out = b.build_total_summary(summaries, '2026-07-27', '2026-08-02')
print('PASS: 总汇总生成完成', out)
"
```

- [ ] **Step 4: 最终 Commit**

```bash
git add .
git commit -m "feat: 端到端集成（四模块合并+总汇总+周报库+归档），更新requirements.txt"
```

---

## Plan Summary

| Task | 产出 | 新建/修改文件 |
|------|------|-------------|
| 1 | DB + Config | `database.py`, `config.yaml` |
| 2 | 配置驱动 | `merger/excel_merger.py`, `app.py` |
| 3 | 营销运营部 | 复用引擎，仅验证 |
| 4 | 销售部 | `merger/sales_merger.py` |
| 5 | 海外BD | `merger/ppt_merger.py` |
| 6 | 通用汇总层 | `merger/summary_builder.py` |
| 7 | 周报库 | `archive_page.py`, `app.py` |
| 8 | 汇总触发 | `app.py` 汇总按钮逻辑 |
| 9 | 集成测试 | `requirements.txt`, 验证 |
