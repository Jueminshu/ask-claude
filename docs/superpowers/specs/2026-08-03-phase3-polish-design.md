# Phase 3 — 周报系统完善 设计文档

**日期**: 2026-08-03
**分支**: master
**范围**: 4 项递进完善（D → A → B → C）

---

## D — PPT 上传支持与预览优化

### 目标
使海外BD（PPT 格式模块）的上传体验与预览与 Excel 模块对齐，但复用通用模板字段（不做 PPT 专用模板）。

### 改动

#### D1. 上传页格式感知 (`pages/upload.py`)
- 读取 `modules.format` 字段并展示给用户（"📊 本模块格式: PPT" / "📋 本模块格式: Excel"）
- `st.file_uploader` 的 `type` 参数按格式调整：
  - `excel` → `["xlsx", "xls"]`（默认全部类型仍可接受，仅调整建议列表的首位）
  - `ppt` → `["pptx", "ppt"]`
- 格式提示使用 `st.info()` 而非阻塞

#### D2. PPT 预览降级提示 (`static/superior_browse.html`, `static/analysis_dashboard.html`)
- 当前预览逻辑：PDF 用 iframe，图片用 img，无预览显示通用占位符
- 改进：无预览时按 `file_type` 区分提示文案和图标：
  - `pptx` → "📊 PPT 文件处理中，请稍后刷新或点击下载查看"
  - `xlsx` → "📋 Excel 文件处理中，请稍后刷新或点击下载查看"
  - `other` → "📎 文件处理中，请稍后刷新或点击下载查看"
- 仅在降级占位符处修改，不影响正常 PDF/图片预览

### 涉及文件
- `pages/upload.py`
- `static/superior_browse.html`
- `static/analysis_dashboard.html`

---

## A — 自定义驳回理由

### 目标
Leader 审核驳回时可输入自定义理由，替代当前固定文本。

### 改动

#### A1. 审核页 (`pages/review.py`)
- 驳回操作区增加 `st.text_area("驳回理由", placeholder="请填写驳回原因...")`
- 提交时传入 `note` 参数：用户填了就用，没填默认 "请修改后重新提交"
- `reject_submission()` 已接受 `note` 参数无需改动

#### A2. 上传页驳回展示
- 已展示 `leader_review_note`，无需额外改动

### 涉及文件
- `pages/review.py`

---

## B — 用户 CRUD

### 目标
系统管理页"用户管理" Tab 支持新增、编辑、删除用户。

### 改动

#### B1. 数据库层 (`database_v2.py`)
新增 3 个函数：
- `create_user(username, password_hash, display_name, role, module_id, can_browse_all)` → user_id
- `update_user(user_id, **fields)` — 按字段更新
- `deactivate_user(user_id)` — 软删除（`is_active = 0`）

#### B2. 管理页 (`pages/admin.py`)
用户管理 Tab 改造：
- 列表上方新增"+ 新增用户"按钮
- 新增：弹出 form（用户名、显示名、密码、角色下拉、模块下拉、全模块浏览勾选）
- 编辑：每条用户记录旁放"编辑"按钮，点击后行内编辑（至少可修改 display_name、role、module_id、can_browse_all）
- 删除：每条用户记录旁放"停用"按钮，确认后软删除
- 不展示已停用用户（或可选过滤）

### 约束
- 密码修改：编辑时不直接显示原密码，提供"重置密码"独立操作
- 用户名唯一，重名提示错误

### 涉及文件
- `database_v2.py`
- `pages/admin.py`

---

## C — 截止时间可配置

### 目标
在管理页修改各模块的截止时间，替代当前硬编码的"周一 10:00"。

### 改动

#### C1. 截止时间服务 (`services/deadline.py`)
- `get_deadline_info()` 改为接收 `module_id` 参数
- 从 `modules` 表读取该模块的 `deadline_day`、`deadline_time`
- `check_deadline_passed()` 同理改为按模块判断
- 无 module_id 时回退到默认值（周一 10:00）

#### C2. 管理页 (`pages/admin.py`)
模块设置 Tab 中每个模块增加行内编辑：
- `deadline_day` — 下拉选择（1=周一 ~ 7=周日）
- `deadline_time` — 时间输入（HH:MM 格式）
- 保存按钮 → 调用 `UPDATE modules SET deadline_day=?, deadline_time=? WHERE id=?`

#### C3. 上传页适配 (`pages/upload.py`)
- 调用 `get_deadline_info(user["module_id"])` 传入模块 ID
- 截止判断使用本模块的 deadline

#### C4. Worker 自动通过适配 (`worker.py`)
- `_check_auto_approve()` 改为按各模块的 `auto_approve_time` 判断（`modules` 表已有该字段）

### 涉及文件
- `services/deadline.py`
- `pages/admin.py`
- `pages/upload.py`
- `worker.py`

---

## 执行顺序

D → A → B → C，每项完成后进行验证。
