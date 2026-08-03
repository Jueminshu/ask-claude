# 市场情报模块 设计文档

**日期**: 2026-08-03
**范围**: 销售部周报"市场信息"section 提取 → 总表存储 → 对比与趋势分析

---

## 背景

销售部周报模板（`销售部周报模板.xlsx`）每人一个 sheet，包含"市场信息（每周反馈新增变化部分）"区域，记录竞品厂商/型号/配置/价格情报及我方对标信息（14列）。当前系统未提取此区域。

## 数据提取

**定位策略**: 扫描 column A 找到含"市场信息"的单元格 → 下一行为表头 → 再下一行起为数据行，直至空行或 sheet 结束。找不到该 section 则跳过，不报错。

**提取时机**: Worker 文件处理管线，与风险提取并列（`process_file` → `run_market_intel_extraction`）。

**覆盖策略**: 同周、同人、同文件 → 先删旧后插入（与 `risk_items` 同理）。

## 数据库

### 新表 `market_intel`

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

### CRUD 函数

- `upsert_market_intel(week_start, module_id, user_id, submission_file_id, rows)` — 覆盖式写入
- `get_market_intel(week_start=None, module_id=None, vendor=None, category=None)` — 筛选查询
- `get_model_timeline(model, weeks=8)` — 型号时间线

## 提取逻辑

新增 `services/analyzer/market_intel_extractor.py`：

1. 用 `openpyxl` 打开 xlsx 文件
2. 遍历所有 sheet，在 column A 搜索含"市场信息"的单元格
3. 定位到表头行、解析列映射（序号/更新时间/信息收集人/厂家/分类/型号/主要配置/主要外围配置/对T1-T3价格/对标我司型号/主要配置/主要外围配置/对T1-T3价格/补充说明）
4. 从数据起始行读取至空行或 sheet 尾
5. 返回 `list[dict]`

## 查看与分析

领导查阅页新增 **Tab 3：📊 市场情报**（`superior` + `can_browse_all` leader 可见）

### Tab 3-A：市场情报总表

- 所有数据按周倒序，筛选器：周次 / 厂家 / 分类 / 型号 / 人员
- 本周新增标记：`vendor + model` 组合在上周数据中不存在 → 标"新增"

### Tab 3-B：竞品热力图

- 厂商 × 分类活跃度矩阵（条目数，ECharts heatmap）
- 颜色深浅 → 活跃程度

### Tab 3-C：型号时间线

- 下拉选择型号 → 近 8 周逐周展示记录
- 对比每次出现的配置/价格变化

## 权限

- `superior` 角色
- `can_browse_all = 1` 的 leader

## 涉及文件

- `database_v2.py` — 建表 + CRUD
- `services/analyzer/market_intel_extractor.py` — 新建，提取逻辑
- `services/analyzer/__init__.py` — 导出
- `worker.py` — 调用提取
- `pages/leader_browse.py` — Tab 3 数据准备
- `static/market_intel.html` — 新建，总表/热力图/时间线 UI

## 约束

- 不引入新依赖（已有 openpyxl）
- 复用现有风险热力图视觉风格
- 提取失败不阻塞其他处理
