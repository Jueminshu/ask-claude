# 营销运作部周报收集系统 · 重新设计

## 元信息

- **日期**: 2026-07-30
- **版本**: v2.0
- **原系统**: Streamlit + SQLite（v1.0，4 模块/3 角色/5 页面）
- **设计方向**: 方案 A+ — 增强 Streamlit + 关键模块嵌入式前端组件 + 后台异步处理

---

## 一、系统概述

### 1.1 核心变化

| 维度 | v1.0（当前） | v2.0（本设计） |
|------|------------|------------|
| 提交格式 | 仅 Excel | Excel / PPT / Word / PDF / JPG/PNG |
| 提交方式 | 一次一个文件 | 一次多个文件，智能合并 |
| 展示方式 | 合并汇总成 Excel/PPT 下载 | 点击姓名在线查看个人全部文件 |
| 审核流程 | 管理员单层通过/驳回 | Team Leader 审核 + 超时自动通过 |
| 截止时间 | 周日 23:59 | 周一 10:00 |
| 通知 | 无 | CRM 钩子事件通知 |
| 互动 | 无 | 部门领导点赞 + 评论 |
| 分析 | 无 | 6 模块分析看板（分阶段） |

### 1.2 技术架构

```
Streamlit 主线程（页面渲染）
    +
后台 Worker 线程（文件处理 + 定时检查 + AI 分析）
    +
嵌入式前端组件（领导查阅页 + 分析看板，st.components.html）
    +
轻量 FastAPI 端点（可选：CRM API + 静态文件服务）
```

全 Python 技术栈，SQLite 数据库，officecli 文件解析，Claude API AI 分析。

---

## 二、角色与权限

### 2.1 角色定义

| # | 角色 | role 值 | 所属模块 | 特殊说明 |
|---|------|---------|---------|---------|
| 1 | 国内运营商 Leader | `leader` | 国内运营商 | 标准 Leader |
| 2 | 营销运营部 Leader | `leader` | 营销运营部 | 额外开通全模块查阅（can_browse_all=1） |
| 3 | 销售部 Leader | `leader` | 销售部 | 标准 Leader |
| 4 | 海外 BD Leader | `leader` | 海外 BD | 标准 Leader |
| 5 | 部门领导 | `superior` | 全局 | 全模块查阅 + 点赞评论，不审批 |
| 6 | 管理员 | `admin` | 全局 | 纯技术维护（用户/模块/模板管理），不参与业务 |
| 7 | 各模块 Member | `member` | 各自模块 | 提交周报 + 看自己历史 |

### 2.2 页面权限

| 页面 | Member | Leader（标准） | 营销运营 Leader | 部门领导 | 管理员 |
|------|:--:|:--:|:--:|:--:|:--:|
| 上传周报 | ✅ | ✅ | ✅ | — | — |
| 提交历史（自己的） | ✅ | ✅ | ✅ | — | — |
| 团队视图（本团队） | — | ✅ | ✅ | — | — |
| 审核周报（本团队） | — | ✅ | ✅ | — | — |
| 领导查阅（全模块） | — | — | ✅ | ✅ | — |
| 系统管理 | — | — | — | — | ✅ |

### 2.3 数据权限

| 操作 | Member | Leader（标准） | 营销运营 Leader | 部门领导 | 管理员 |
|------|:--:|:--:|:--:|:--:|:--:|
| 看自己周报 | ✅ | ✅ | ✅ | — | — |
| 看本团队周报 | — | ✅ | ✅ | ✅ | — |
| 看所有模块周报 | — | — | ✅ | ✅ | — |
| 点赞/评论 | — | — | — | ✅ | — |
| 审核本团队 | — | ✅ | ✅ | — | — |
| 催交本团队 | — | ✅ | ✅ | — | — |
| 用户/模块/模板管理 | — | — | — | — | ✅ |

### 2.4 特殊规则

- **Leader 自审**：Leader 提交自己的周报后，自己审核自己（走完整 Leader 层审核），保持结构统一
- **超时自动通过**：周一 11:30 未审核则自动通过，reviewer=system
- **多次提交**：截止时间前可多次提交，以最新版为准；被驳回后可在截止前重交
- **提交合并**：同一模板类型以最新替换，不同模板类型累加保留

---

## 三、时间线

```
周一 08:00  系统自动提醒未提交员工（N1）
周一 10:00  截止提交，Leader 审核窗口开启
周一 11:00  提醒 Leader 一次 — 还有未审项的（N2）
周一 11:30  超时自动通过 → 部门领导可查阅
```

---

## 四、数据库 Schema

### 4.1 表清单

| 表名 | 类型 | 说明 |
|------|------|------|
| `modules` | 保留/微调 | 模块信息，增 auto_approve_time 字段 |
| `users` | 保留/扩展 | 增 can_browse_all 字段；role 增 superior |
| `file_templates` | **新增** | 文件模板定义（文件名关键词 + 结构规则） |
| `submissions` | **重构** | 一次提交一条，不再绑定单个文件 |
| `submission_files` | **新增** | 一次提交中的多个文件 |
| `review_log` | **新增** | 审核记录独立表 |
| `interactions` | **新增** | 点赞 + 评论统一表 |
| `notification_events` | **新增** | 通知事件表（CRM 消费） |
| `task_queue` | **新增** | 异步文件处理任务队列 |

### 4.2 DDL

```sql
-- 模块表（微调）
CREATE TABLE IF NOT EXISTS modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    format TEXT NOT NULL DEFAULT 'excel',
    deadline_day INTEGER DEFAULT 1,
    deadline_time TEXT DEFAULT '10:00',
    auto_approve_time TEXT DEFAULT '11:30'
);

-- 用户表（扩展）
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    email TEXT,
    role TEXT NOT NULL DEFAULT 'member',  -- admin / leader / member / superior
    module_id INTEGER,
    can_browse_all INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (module_id) REFERENCES modules(id)
);

-- 文件模板表
CREATE TABLE IF NOT EXISTS file_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    identifier_type TEXT NOT NULL,       -- keyword / structure / both
    filename_keywords TEXT,
    structure_rules TEXT,
    is_weekly_report INTEGER DEFAULT 0,
    FOREIGN KEY (module_id) REFERENCES modules(id)
);

-- 提交记录表（重构）
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    module_id INTEGER NOT NULL,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'submitted',
    leader_reviewed_by INTEGER,
    leader_reviewed_at TEXT,
    leader_review_note TEXT,
    submitted_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    is_latest INTEGER DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (module_id) REFERENCES modules(id),
    FOREIGN KEY (leader_reviewed_by) REFERENCES users(id)
);

-- 提交文件表
CREATE TABLE IF NOT EXISTS submission_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    template_id INTEGER,
    filename TEXT NOT NULL,
    original_path TEXT NOT NULL,
    preview_path TEXT,
    file_type TEXT NOT NULL,
    file_size INTEGER,
    recognition_status TEXT DEFAULT 'pending',
    recognition_confidence REAL,
    extracted_text TEXT,
    parsed_data TEXT,
    processing_status TEXT DEFAULT 'pending',
    FOREIGN KEY (submission_id) REFERENCES submissions(id),
    FOREIGN KEY (template_id) REFERENCES file_templates(id)
);

-- 审核记录表
CREATE TABLE IF NOT EXISTS review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    reviewer_id INTEGER NOT NULL,        -- 0 = system（超时自动通过）
    review_level TEXT NOT NULL,           -- leader
    action TEXT NOT NULL,                 -- approve / reject
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (submission_id) REFERENCES submissions(id),
    FOREIGN KEY (reviewer_id) REFERENCES users(id)
);

-- 互动表
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_file_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,                   -- like / comment
    content TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (submission_file_id) REFERENCES submission_files(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(submission_file_id, user_id, type)
);

-- 通知事件表
CREATE TABLE IF NOT EXISTS notification_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    target_user_id INTEGER NOT NULL,
    related_submission_id INTEGER,
    payload TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    sent_at TEXT,
    FOREIGN KEY (target_user_id) REFERENCES users(id),
    FOREIGN KEY (related_submission_id) REFERENCES submissions(id)
);

-- 任务队列表
CREATE TABLE IF NOT EXISTS task_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_file_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    completed_at TEXT,
    FOREIGN KEY (submission_file_id) REFERENCES submission_files(id)
);
```

---

## 五、文件处理流水线

### 5.1 处理阶段

```
上传 → [阶段1: 保存] → [阶段2: 文本提取] → [阶段3: 模板识别] → [阶段4: PDF转换]
                                                                      ↓
                                                                  就绪可预览
```

| 阶段 | 操作 | 耗时 | 产物 |
|------|------|------|------|
| 1. 保存 | 写磁盘 + 写 submission_files | <1s | 原始文件 |
| 2. 文本提取 | officecli 提取文本内容 | 2-5s | extracted_text |
| 3. 模板识别 | 文件名关键词 + 文本结构匹配 | 1-2s | template_id + 置信度 |
| 4. PDF 转换 | Office 文件转 PDF 预览（图片跳过） | 3-8s | preview_path |

4 个阶段在后台 Worker 线程中串行执行。用户上传后立即可离开页面。

### 5.2 异步架构

- **触发**：用户提交后写 task_queue（每个文件 4 条任务）→ 页面返回"上传成功"
- **执行**：后台 Worker 线程每 2 秒检查 task_queue，取 `status='queued'` 执行
- **反馈**：前端每 3 秒轮询 submission_files.processing_status
  - `pending` → 显示"处理中..."
  - `ready` → 显示"可查看"
  - `error` → 显示错误信息
- **技术选型**：Python 后台线程 + SQLite 任务表（不引入 Celery/RQ）

### 5.3 模板识别规则

```python
def identify_template(file, module_id) -> tuple[Template | None, float]:
    """
    1. 文件名关键词匹配（权重 0.5）
       关键词来自 file_templates.filename_keywords
    2. 文本结构匹配（权重 0.5）
       检查 extracted_text 中是否包含 structure_rules 中定义的必需特征
       （如 required_columns、sheet_name 等）
    3. 置信度 ≥ 0.6 → 匹配成功
       置信度 < 0.6 → 标记为"未识别"，用户可手动指定
    """
```

### 5.4 文件预览策略

| 文件类型 | 预览方式 |
|---------|---------|
| PDF | `<iframe>` 浏览器原生渲染 |
| 图片 (jpg/png) | `<img>` 标签 |
| Office (xlsx/pptx/docx) | 上传时后台转 PDF → iframe 预览 |

---

## 六、页面详细设计

### 6.1 上传页面

**功能**：
- 统一上传区，支持拖拽多文件（Excel/PPT/Word/PDF/图片）
- 文件选择后前端即时预识别（文件名关键词匹配），显示识别结果图标
- 未识别文件提供手动模板选择下拉框
- 提交后秒级反馈"上传成功"，后台异步处理
- 显示处理进度条（每个文件的状态）
- 多次提交智能合并：同模板类型替换，不同模板累加

**截止后行为**：
- 上传按钮置灰，显示"本周提交已截止"
- 补交由 Leader 手动开启

### 6.2 Leader 审核页面

**功能**：
- 统计卡片：应提交 / 已提交 / 待审核 / 已审核
- 待审核列表：展开查看成员所有文件（支持弹窗预览），填写驳回原因，点击通过/驳回
- 已审核列表：审核历史记录
- 未提交列表：催交按钮
- 我的周报卡片：Leader 自审通过
- 催交：写 notification_events（event_type=leader_nudge）

### 6.3 领导查阅页（嵌入式组件）

**技术方案**：独立 `superior_browse.html` 通过 `st.components.html()` 嵌入，原生 JS 实现，约 500-600 行。

**布局**：左栏成员列表 + 右栏文件预览/互动，顶部工具栏（模块切换 + 周切换 + 查阅/看板 Tab 切换）。

**交互**：
- 点击成员 → 右侧加载文件列表，周报置顶
- 点击文件标签 → 切换预览区 iframe
- 点赞：即点即变，异步写库
- 评论：展开评论区，支持员工回复
- 跨周导航：← 上一周 | 下一周 →

**双向通信**：Python 注入初始 JSON 数据 → JS 渲染 → 用户操作通过消息通道回传 → Python 写库并返回结果 → JS 更新 UI。

### 6.4 分析看板（嵌入式组件）

通过查阅页顶部 Tab `[📋 周报查阅] [📊 分析看板]` 切换。

**6 个分析模块**：

① **风险热力图**（Phase 2）— 跨模块风险聚合热力图，区分新增/持续风险，支持下钻
② **项目健康度**（Phase 3）— 拜访频率 + 竞争态势 + 进展综合评分，绿/黄/红三色
③ **进度异常检测**（Phase 3）— 上周"计划" vs 本周"进展"对比，语义匹配
④ **协同盲点**（Phase 3）— 跨模块同一客户/项目描述矛盾检测
⑤ **会议待办追踪**（Phase 3）— Action items 提取 → 看板 → 跨周闭环追踪
⑥ **个人效率概览**（Phase 2）— 提交及时率 + 内容丰富度 + 驳回次数

**分阶段交付**：

| 阶段 | 内容 | 依赖 |
|------|------|------|
| Phase 1 | 看板框架 + KPI 顶栏（纯 SQL 统计） | 无 |
| Phase 2 | ① 风险热力图 v1 + ⑥ 个人效率概览 | Claude API 文本提取 |
| Phase 3 | ② ③ ⑤ ④ | Claude API 深度分析 + 跨文件关联 |

分析看板同样用 ECharts 嵌入式组件实现。

---

## 七、通知系统

### 7.1 通知事件

| # | event_type | 触发条件 | 通知对象 | 时机 |
|---|-----------|---------|---------|------|
| N1 | `pre_deadline_remind` | 截止前 2 小时仍有未提交 | 未提交员工 | 周一 08:00 |
| N2 | `leader_window_remind` | 审核窗口 30 分钟前有未审项 | 各 Leader | 周一 11:00（仅一次） |
| N3 | `leader_reject` | Leader 驳回 | 被驳回员工 | 驳回后立即 |
| N4 | `superior_interact` | 领导点赞/评论 | 被互动员工 | 互动后立即 |
| N5 | `leader_nudge` | Leader 手动催交 | 被催交员工 | 手动触发 |

### 7.2 实现方式

- 定时事件（N1/N2）：后台 Worker 线程每 60 秒检查触发
- 即时事件（N3/N4/N5）：业务操作中同步写入 notification_events 表
- 去重：定时事件同一天只触发一次

### 7.3 CRM 对接

系统不负责消息的实际发送，只负责在正确时间产生正确的通知事件。

CRM 侧对接方式：
- **方式一**：通过 FastAPI 轻量端点轮询 `/api/notifications/pending` → 取待发送事件 → 发送后回写 status=sent
- **方式二**：数据库直连查询 notification_events 表

CRM 团队职责：定期查询未处理事件 → 发消息（站内信/弹窗/推送）→ 回写已发送。

---

## 八、技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| Web 框架 | Streamlit | 主框架，80% 页面 |
| 数据库 | SQLite | 规模适配，零运维 |
| 文件解析 | officecli | 文本提取 + PDF 转换 |
| AI 分析 | Claude API | 风险提取 + 进度对比 + 实体识别 |
| 前端增强 | 原生 HTML/JS + ECharts | 嵌入 Streamlit，领导查阅页 + 分析看板 |
| 异步任务 | Python 后台线程 + SQLite 队列 | 不引入 Celery/RQ |
| API 端点 | FastAPI（可选） | CRM 对接 + 静态文件服务 |

---

## 九、目录结构

```
weekly-report-system/
├── app.py                        # 主入口（重构路由）
├── database.py                   # 数据库（新 Schema + 迁移）
├── config.yaml                   # 配置文件（更新）
├── worker.py                     # 后台 Worker 线程
├── pages/
│   ├── upload.py                 # 多文件上传
│   ├── team_view.py              # 团队视图
│   ├── review.py                 # Leader 审核
│   ├── history.py                # 提交历史
│   └── admin.py                  # 系统管理
├── services/
│   ├── file_handler.py           # 文件存储抽象层
│   ├── file_parser.py            # 多格式解析 + 模板识别
│   ├── deadline.py               # 截止时间 + 超时自动通过
│   ├── notification.py           # 通知事件服务
│   └── analyzer/                 # 分析引擎（Phase 2-3）
│       ├── risk_extractor.py
│       ├── progress_checker.py
│       ├── health_scorer.py
│       ├── blind_spot_detector.py
│       ├── action_tracker.py
│       └── efficiency.py
├── static/
│   ├── superior_browse.html      # 领导查阅嵌入式组件
│   └── analysis_dashboard.html   # 分析看板嵌入式组件
├── output/                       # 文件存储目录
├── data/
│   └── weekly_report.db
└── requirements.txt
```

---

## 十、数据迁移

v1.0 → v2.0 Schema 变化较大，迁移策略：

1. 新建 v2 表（带 `_v2` 后缀）
2. 从旧表迁移兼容数据（modules、users 基础字段）
3. 验证迁移完整性
4. 删除旧表，重命名 v2 表
5. 旧上传文件保留在磁盘，标记为"v1 遗留"，只可下载不可预览

迁移脚本 `migrate_v1_to_v2.py` 在实施阶段编写。

---

## 十一、已知限制与后续规划

| 限制 | 说明 | 计划 |
|------|------|------|
| Leader 自审 | Leader 自我审核缺乏制衡 | 暂接受，管理员可事后抽查 |
| 超时自动通过 | 质量无法保证 | Leader 审核窗口提醒 + 领导查阅发现问题时可通过评论反馈 |
| 用户自助注册 | 无 | 管理员手动创建，符合内部工具定位 |
| 密码安全 | 当前 SHA256 加盐不足 | 后续切换到 bcrypt |
| 文件存储 | 本地磁盘，无备份 | 实施时加入定期备份脚本 |

---

## 十二、自审检查清单

- [x] 无 TBD/TODO 占位
- [x] 角色权限矩阵一致（页面权限与数据权限不矛盾）
- [x] 审核链路完整（提交 → Leader → 超时 → 领导查阅）
- [x] 通知事件去重逻辑明确
- [x] 多次提交合并规则清晰
- [x] 分阶段交付边界明确
- [x] 数据库迁移策略已描述
