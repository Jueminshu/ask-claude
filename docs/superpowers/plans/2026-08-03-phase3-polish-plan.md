# Phase 3 完善实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善周报系统的 PPT 支持、用户管理、截止时间配置三项功能

**Architecture:** 在现有 Streamlit + SQLite 架构上增量修改，不改动核心工作流。每项独立，通过数据库层共享接口。

**Tech Stack:** Streamlit 1.60+, SQLite, Python 3, officecli (PPT→PDF), vanilla HTML/CSS/JS (嵌入式组件)

## Global Constraints

- 不引入新依赖（使用已有 officecli 做 PPT 转换）
- 密码使用 SHA256 哈希
- 用户删除为软删除（is_active=0）
- deadline_day 使用 Python weekday 语义（0=周一）
- 海外BD 不创建 PPT 专用模板，复用现有模板字段

---

### Task 1: 上传页格式感知

**Files:**
- Modify: `weekly-report-system/pages/upload.py:33-99`

**Interfaces:**
- Consumes: `get_db()` from database_v2, `ALLOWED_EXTENSIONS` from file_handler
- Produces: (no new exports, internal UI change)

- [ ] **Step 1: 在 render_upload_page 中读取模块 format 并展示提示**

在获取 module_name 之后（约第 46 行），添加格式提示：

```python
# 获取模块名和格式
conn = get_db()
m = conn.execute("SELECT name, format FROM modules WHERE id = ?", (module_id,)).fetchone()
module_name = m["name"] if m else "未分配"
module_format = m["format"] if m else "excel"
conn.close()

st.markdown(f"**模块**: {module_name} | **周期**: {week_start} ~ {week_end}")

# 格式提示
format_label = "📊 PPT" if module_format == "ppt" else "📋 Excel"
st.info(f"📌 本模块格式: {format_label}，请上传对应类型的文件")
```

- [ ] **Step 2: 根据格式调整 file_uploader 的 type 参数**

```python
# 根据模块格式确定上传类型建议
if module_format == "ppt":
    upload_types = ["pptx", "ppt"] + [e for e in ALLOWED_EXTENSIONS if e not in ("pptx", "ppt")]
else:
    upload_types = ["xlsx", "xls"] + [e for e in ALLOWED_EXTENSIONS if e not in ("xlsx", "xls")]

uploaded_files = st.file_uploader(
    "拖拽或选择文件（支持多文件）",
    type=upload_types,
    accept_multiple_files=True,
    help="支持 Excel / Word / PPT / PDF / 图片，可一次选择多个文件",
    key=f"upload_{week_start}",
)
```

- [ ] **Step 3: 运行应用确认格式提示正确**

Run: `cd weekly-report-system && streamlit run app.py`
- 用 `user41`（海外BD 成员）登录 → 上传页应显示"📌 本模块格式: 📊 PPT"
- 用 `user11`（国内运营商成员）登录 → 上传页应显示"📌 本模块格式: 📋 Excel"

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/pages/upload.py
git commit -m "feat: upload page shows module format and adjusts file type suggestions"
```

---

### Task 2: PPT 预览降级提示优化

**Files:**
- Modify: `weekly-report-system/static/superior_browse.html:232-244`

**Interfaces:**
- Consumes: `file.file_type`, `file.processing_status`, `file.filename` from Streamlit data bridge
- Produces: (visual change only, no API changes)

- [ ] **Step 1: 修改预览降级提示，按文件类型区分**

将 `superior_browse.html` 中约 240-243 行的降级占位符替换为：

```javascript
  if (file.file_type === 'pdf' || (previewUrl && previewUrl.endsWith('.pdf'))) {
    previewArea.innerHTML = `<iframe src="${previewUrl}"></iframe>`;
  } else if (file.file_type === 'image') {
    previewArea.innerHTML = `<img src="${previewUrl}" alt="${file.filename}" />`;
  } else if (file.processing_status !== 'ready') {
    // 按文件类型显示不同提示
    const typeHints = {
      'pptx': '📊 PPT 文件处理中',
      'xlsx': '📋 Excel 文件处理中',
      'docx': '📝 Word 文件处理中',
    };
    const hint = typeHints[file.file_type] || '📎 文件处理中';
    previewArea.innerHTML = `<div class="placeholder">${hint}<br><small>请稍后刷新或点击下载查看</small></div>`;
  } else {
    const typeIcons = {
      'pptx': '📊', 'xlsx': '📋', 'docx': '📝', 'pdf': '📄'
    };
    const icon = typeIcons[file.file_type] || '📎';
    previewArea.innerHTML = `<div class="placeholder">${icon} ${file.filename}<br><small>点击下载查看</small></div>`;
  }
```

- [ ] **Step 2: 确认分析看板无需修改**

`analysis_dashboard.html` 不包含文件预览逻辑（仅图表），确认跳过。

- [ ] **Step 3: 运行应用确认预览提示正确**

Run: `cd weekly-report-system && streamlit run app.py`
- 用 `superior` 登录 → 领导查阅 → 查看一个处理中的 PPT 文件 → 应显示 "📊 PPT 文件处理中"

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/static/superior_browse.html
git commit -m "feat: file-type-aware preview placeholder icons in leader browse"
```

---

### Task 3: 用户 CRUD 数据库层

**Files:**
- Modify: `weekly-report-system/database_v2.py` (append new functions at end)

**Interfaces:**
- Produces:
  - `create_user(username, password_hash, display_name, role, module_id=None, can_browse_all=0) -> user_id`
  - `update_user(user_id, **fields) -> bool`
  - `deactivate_user(user_id) -> bool`
  - `get_all_users(include_inactive=False) -> list[dict]`

- [ ] **Step 1: 新增 create_user 函数**

在 `database_v2.py` 末尾添加：

```python
def create_user(username, password_hash, display_name, role, module_id=None, can_browse_all=0):
    """创建新用户，返回 user_id；用户名重复返回 None"""
    conn = get_db()
    try:
        cursor = conn.execute(
            """INSERT INTO users (username, password_hash, display_name, role, module_id, can_browse_all)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (username, password_hash, display_name, role, module_id, can_browse_all)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None
```

- [ ] **Step 2: 新增 update_user 函数**

```python
def update_user(user_id, **fields):
    """按字段更新用户信息。fields 可包含: display_name, role, module_id, can_browse_all, password_hash, email"""
    if not fields:
        return False
    allowed = {"display_name", "role", "module_id", "can_browse_all", "password_hash", "email", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [user_id]
    conn = get_db()
    conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True
```

- [ ] **Step 3: 新增 deactivate_user 函数**

```python
def deactivate_user(user_id):
    """软删除用户（设置 is_active=0）"""
    conn = get_db()
    conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True
```

- [ ] **Step 4: 新增 get_all_users 函数**

```python
def get_all_users(include_inactive=False):
    """获取所有用户列表（含模块名）"""
    conn = get_db()
    if include_inactive:
        rows = conn.execute(
            """SELECT u.*, m.name as module_name
               FROM users u LEFT JOIN modules m ON u.module_id = m.id
               ORDER BY u.id"""
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT u.*, m.name as module_name
               FROM users u LEFT JOIN modules m ON u.module_id = m.id
               WHERE u.is_active = 1 ORDER BY u.id"""
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

- [ ] **Step 5: 测试数据库函数**

```python
# 在 Python 中快速验证
from database_v2 import *
init_db()
# 测试创建
uid = create_user("test_user", "hash123", "测试用户", "member", 1, 0)
assert uid is not None
# 测试更新
assert update_user(uid, display_name="新名字", role="leader")
# 测试获取
users = get_all_users()
assert any(u["id"] == uid for u in users)
# 测试停用
assert deactivate_user(uid)
users = get_all_users()
assert not any(u["id"] == uid for u in users)
# 含停用
users = get_all_users(include_inactive=True)
assert any(u["id"] == uid for u in users)
# 清理
conn = get_db()
conn.execute("DELETE FROM users WHERE username = 'test_user'")
conn.commit()
conn.close()
print("All assertions passed!")
```

- [ ] **Step 6: Commit**

```bash
git add weekly-report-system/database_v2.py
git commit -m "feat: add user CRUD functions — create, update, deactivate, get_all"
```

---

### Task 4: 用户管理页 CRUD UI

**Files:**
- Modify: `weekly-report-system/pages/admin.py:1-70`

**Interfaces:**
- Consumes: `create_user`, `update_user`, `deactivate_user`, `get_all_users` from database_v2
- Produces: (UI changes only)

- [ ] **Step 1: 重写用户管理 Tab — 加入新增表单**

将 `admin.py` 的用户管理 Tab（约第 12-38 行）替换为：

```python
from database_v2 import get_db, create_user, update_user, deactivate_user, get_all_users
import hashlib

# 在 render_admin_page() 的 with tab1: 内

st.subheader("用户列表")

# === 新增用户表单 ===
with st.expander("➕ 新增用户", expanded=False):
    with st.form("new_user_form"):
        col1, col2 = st.columns(2)
        new_username = col1.text_input("用户名 *", key="new_username")
        new_display = col2.text_input("显示名 *", key="new_display")
        new_password = col1.text_input("密码 *", type="password", key="new_password")
        new_role = col2.selectbox("角色 *", ["member", "leader", "superior"], key="new_role")
        
        conn = get_db()
        modules = conn.execute("SELECT id, name FROM modules ORDER BY id").fetchall()
        conn.close()
        module_options = {m["name"]: m["id"] for m in modules}
        new_module = col1.selectbox("所属模块", list(module_options.keys()), key="new_module")
        new_can_browse = col2.checkbox("全模块浏览权限", key="new_can_browse")
        
        if st.form_submit_button("创建用户", use_container_width=True):
            if not new_username or not new_display or not new_password:
                st.error("用户名、显示名、密码为必填项")
            else:
                pw_hash = hashlib.sha256(new_password.encode()).hexdigest()
                uid = create_user(
                    new_username, pw_hash, new_display, new_role,
                    module_options[new_module], 1 if new_can_browse else 0
                )
                if uid:
                    st.success(f"用户 {new_display} 创建成功")
                    st.rerun()
                else:
                    st.error("用户名已存在")
```

- [ ] **Step 2: 用户列表改为可编辑/停用**

在新增表单之后：

```python
# === 用户列表 ===
users = get_all_users(include_inactive=False)
role_labels = {
    "admin": "🔧 管理员", "leader": "👤 Leader",
    "member": "👤 Member", "superior": "👔 部门领导",
}

for u in users:
    with st.container(border=True):
        if st.session_state.get(f"editing_{u['id']}", False):
            # 编辑模式
            with st.form(f"edit_user_{u['id']}"):
                col1, col2, col3 = st.columns(3)
                new_display = col1.text_input("显示名", value=u["display_name"], key=f"ed_name_{u['id']}")
                new_role = col2.selectbox("角色", ["member", "leader", "superior"],
                    index=["member", "leader", "superior"].index(u["role"]) if u["role"] in ["member", "leader", "superior"] else 0,
                    key=f"ed_role_{u['id']}")
                new_module_name = col3.selectbox("模块", list(module_options.keys()),
                    index=list(module_options.values()).index(u["module_id"]) if u["module_id"] in module_options.values() else 0,
                    key=f"ed_mod_{u['id']}")
                new_cba = st.checkbox("全模块浏览", value=bool(u.get("can_browse_all")), key=f"ed_cba_{u['id']}")
                new_pw = st.text_input("新密码（留空不修改）", type="password", key=f"ed_pw_{u['id']}")
                
                c1, c2 = st.columns(2)
                if c1.form_submit_button("💾 保存", use_container_width=True):
                    fields = {
                        "display_name": new_display,
                        "role": new_role,
                        "module_id": module_options[new_module_name],
                        "can_browse_all": 1 if new_cba else 0,
                    }
                    if new_pw.strip():
                        fields["password_hash"] = hashlib.sha256(new_pw.encode()).hexdigest()
                    update_user(u["id"], **fields)
                    st.session_state[f"editing_{u['id']}"] = False
                    st.success("已保存")
                    st.rerun()
                if c2.form_submit_button("❌ 取消", use_container_width=True):
                    st.session_state[f"editing_{u['id']}"] = False
                    st.rerun()
        else:
            # 查看模式
            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
            col1.markdown(f"**{u['display_name']}** ({u['username']})")
            col2.markdown(f"模块: {u.get('module_name', '未分配')}")
            col3.markdown(role_labels.get(u["role"], u["role"]))
            if u.get("can_browse_all"):
                col4.markdown("🌐 全模块")
            
            if col5.button("✏️ 编辑", key=f"btn_ed_{u['id']}"):
                st.session_state[f"editing_{u['id']}"] = True
                st.rerun()
            
            # 停用按钮（admin 不可停用自己）
            if u["role"] != "admin":
                if col5.button("🗑️ 停用", key=f"btn_del_{u['id']}"):
                    deactivate_user(u["id"])
                    st.warning(f"已停用用户 {u['display_name']}")
                    st.rerun()
```

- [ ] **Step 3: 运行应用验证 CRUD**

Run: `cd weekly-report-system && streamlit run app.py`
- `admin` 登录 → 系统管理 → 用户管理
- 测试：新增用户 → 编辑用户 → 停用用户 → 确认列表更新

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/pages/admin.py
git commit -m "feat: user CRUD UI — add, edit, deactivate users in admin page"
```

---

### Task 5: 截止时间服务模块化

**Files:**
- Modify: `weekly-report-system/services/deadline.py:1-65`

**Interfaces:**
- Produces: `get_deadline_info(module_id=None) -> dict`, `check_deadline_passed(module_id=None) -> (bool, str)`

- [ ] **Step 1: 统一 deadline_day 为 0-based（0=周一），加迁移**

先在 `database_v2.py` 的 `init_db()` 末尾添加数据迁移（`conn.executescript` 块之后）：

```python
# 数据迁移：deadline_day 统一为 0-based (0=周一 ~ 6=周日)
# 旧默认值 1 的记录改为 0
conn.execute("UPDATE modules SET deadline_day = 0 WHERE deadline_day = 1")
```

然后修改列默认值（如果表尚未创建则用新默认）：
在 CREATE TABLE modules 中将 `deadline_day INTEGER DEFAULT 1` 改为 `deadline_day INTEGER DEFAULT 0`。

- [ ] **Step 2: 重写 get_deadline_info 支持按模块读取**

```python
"""截止时间服务"""
from datetime import datetime, timedelta
from database_v2 import get_db


def _get_module_deadline(module_id):
    """从数据库读取模块截止配置。deadline_day 为 0-based (0=周一)。
       返回 (deadline_day, deadline_time, auto_approve_time)"""
    if module_id is None:
        return 0, "10:00", "11:30"  # 默认周一 10:00
    conn = get_db()
    m = conn.execute(
        "SELECT deadline_day, deadline_time, auto_approve_time FROM modules WHERE id = ?",
        (module_id,)
    ).fetchone()
    conn.close()
    if m:
        return m["deadline_day"], m["deadline_time"], m["auto_approve_time"]
    return 0, "10:00", "11:30"


def get_deadline_info(module_id=None):
    """
    获取当前周的截止信息。

    Args:
        module_id: 模块 ID，为 None 时使用默认值（周一 10:00）

    返回: {
        'week_start': str,
        'week_end': str,
        'deadline': str,
        'auto_approve': str,
        'is_passed': bool,
        'message': str,
        'remaining': str or None,
    }
    """
    now = datetime.now()
    weekday = now.weekday()  # 0=周一

    # 计算本周一
    monday = now - timedelta(days=weekday)
    sunday = monday + timedelta(days=6)

    # 从数据库读取模块截止配置
    dl_day, dl_time, auto_time = _get_module_deadline(module_id)
    dl_hour, dl_minute = map(int, dl_time.split(":"))
    auto_hour, auto_minute = map(int, auto_time.split(":"))

    deadline = monday.replace(hour=dl_hour, minute=dl_minute, second=0, microsecond=0)
    if dl_day != 0:
        deadline = monday + timedelta(days=dl_day)
        deadline = deadline.replace(hour=dl_hour, minute=dl_minute, second=0, microsecond=0)

    auto_approve = monday.replace(hour=auto_hour, minute=auto_minute, second=0, microsecond=0)

    # 格式化截止时间描述
    day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    deadline_label = f"{day_names[dl_day]} {dl_time}"
    auto_label = f"{day_names[0] if auto_hour < 13 else day_names[dl_day]} {auto_time}"

    is_passed = now > deadline
    remaining = None
    message = ""

    if now < deadline:
        delta = deadline - now
        hours = delta.seconds // 3600 + delta.days * 24
        mins = (delta.seconds % 3600) // 60
        remaining = f"{hours}小时{mins}分钟"
        message = f"请在 {deadline_label} 前提交周报（剩余 {remaining}）"
    elif now < auto_approve:
        delta = auto_approve - now
        mins = delta.seconds // 60
        remaining = f"{mins}分钟"
        message = "提交已截止，Leader 审核中"
        is_passed = True
    else:
        message = "本周审核已结束，部门领导可查阅"
        is_passed = True

    return {
        "week_start": monday.strftime("%Y-%m-%d"),
        "week_end": sunday.strftime("%Y-%m-%d"),
        "deadline": deadline_label,
        "auto_approve": auto_label,
        "is_passed": is_passed,
        "message": message,
        "remaining": remaining,
    }


def check_deadline_passed(module_id=None):
    """检查是否已过截止时间。返回 (is_passed: bool, message: str)"""
    info = get_deadline_info(module_id)
    return info["is_passed"], info["message"]
```

- [ ] **Step 3: 更新 database_v2.py 中的 check_deadline_passed**

将 `database_v2.py:317-333` 中的旧 `check_deadline_passed` 替换为对 `services.deadline` 的代理：

```python
def check_deadline_passed(module_id=None):
    """检查是否已过截止时间（委托给 deadline 服务）"""
    from services.deadline import get_deadline_info
    info = get_deadline_info(module_id)
    return info["is_passed"], info["message"]
```

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/services/deadline.py weekly-report-system/database_v2.py
git commit -m "feat: module-aware deadline service — reads deadline_day/time from DB per module"
```

---

### Task 6: 上传页和审核页传入 module_id

**Files:**
- Modify: `weekly-report-system/pages/upload.py:33,50-51`
- Modify: `weekly-report-system/pages/review.py:17`

**Interfaces:**
- Consumes: `get_deadline_info(module_id)` from deadline service

- [ ] **Step 1: 上传页传入 module_id**

在 `upload.py` 的 `render_upload_page` 中，将：
```python
deadline_info = get_deadline_info()
```
改为：
```python
deadline_info = get_deadline_info(module_id)
```

- [ ] **Step 2: 审核页传入 module_id**

在 `review.py` 的 `render_review_page` 中，将：
```python
deadline_info = get_deadline_info()
```
改为：
```python
deadline_info = get_deadline_info(module_id)
```

- [ ] **Step 3: 运行应用验证截止时间显示**

Run: `cd weekly-report-system && streamlit run app.py`
- 不同模块用户登录 → 上传页显示的截止时间应反映数据库中的配置
- 默认配置下行为不变

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/pages/upload.py weekly-report-system/pages/review.py
git commit -m "feat: pass module_id to deadline service in upload and review pages"
```

---

### Task 7: 管理页模块截止时间编辑

**Files:**
- Modify: `weekly-report-system/pages/admin.py` (模块设置 Tab, 约第 40-51 行)

**Interfaces:**
- Consumes: `get_db()` from database_v2
- Produces: (UI change only)

- [ ] **Step 1: 重写模块设置 Tab 支持截止时间编辑**

将 `admin.py` 的模块设置 Tab（`with tab2:` 块）替换为：

```python
with tab2:
    st.subheader("模块列表")
    conn = get_db()
    modules = conn.execute("SELECT * FROM modules ORDER BY id").fetchall()
    
    for m in modules:
        with st.container(border=True):
            col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
            col1.markdown(f"**{m['name']}**")
            col2.caption(f"格式: {m['format']}")
            
            # 截止日
            day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            new_day = col3.selectbox(
                "截止日", range(7),
                index=m["deadline_day"],
                format_func=lambda d: day_names[d],
                key=f"dl_day_{m['id']}"
            )
            # 截止时间
            new_time = col4.text_input(
                "截止时间", value=m["deadline_time"],
                key=f"dl_time_{m['id']}"
            )
            
            if col5.button("💾 保存", key=f"save_dl_{m['id']}"):
                conn2 = get_db()
                conn2.execute(
                    "UPDATE modules SET deadline_day = ?, deadline_time = ? WHERE id = ?",
                    (new_day, new_time, m["id"])
                )
                conn2.commit()
                conn2.close()
                st.success(f"{m['name']} 截止时间已更新")
                st.rerun()
    conn.close()
```

- [ ] **Step 2: 运行应用验证截止时间编辑**

Run: `cd weekly-report-system && streamlit run app.py`
- `admin` 登录 → 系统管理 → 模块设置
- 修改国内运营商的截止日为周三、时间为 14:00 → 保存
- `user11` 登录 → 上传页应显示"请在 周三 14:00 前提交"

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/pages/admin.py
git commit -m "feat: editable module deadline in admin page — day + time per module"
```

---

### Task 8: Worker 自动通过按模块 auto_approve_time

**Files:**
- Modify: `weekly-report-system/worker.py:105-147`

**Interfaces:**
- Consumes: `get_db()`, `get_current_week()` from database_v2

- [ ] **Step 1: 重写 _check_auto_approve 按模块判断**

将 `worker.py:105-147` 的 `_check_auto_approve` 替换为：

```python
def _check_auto_approve():
    """检查并执行超时自动通过（按模块配置的 auto_approve_time）"""
    now = datetime.now()
    conn = get_db()
    week_start, _week_end = get_current_week()

    # 获取所有模块
    modules = conn.execute("SELECT id, name, auto_approve_time FROM modules").fetchall()
    
    for mod in modules:
        try:
            auto_h, auto_m = map(int, mod["auto_approve_time"].split(":"))
        except (ValueError, AttributeError):
            continue
        
        # 检查是否到了该模块的自动通过时间（当前时间 >= 配置时间）
        auto_dt = now.replace(hour=auto_h, minute=auto_m, second=0, microsecond=0)
        if now < auto_dt:
            continue  # 还没到时间
        
        # 只处理当天（周一）到时间的模块，避免重复执行
        if now > auto_dt + timedelta(minutes=10):
            continue  # 超过10分钟不处理，防止重复
        
        pending = conn.execute(
            """SELECT id, user_id FROM submissions
               WHERE module_id = ? AND week_start = ? AND status = 'submitted' AND is_latest = 1""",
            (mod["id"], week_start)
        ).fetchall()
        
        if not pending:
            continue
        
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
        print(f"[Worker] {mod['name']} 超时自动通过 {len(pending)} 条")
    
    conn.commit()
    conn.close()
```

需要在文件顶部添加 `timedelta` 导入：
```python
from datetime import datetime, timedelta
```

- [ ] **Step 2: Commit**

```bash
git add weekly-report-system/worker.py
git commit -m "feat: per-module auto-approve time in worker"
```

---

### Task 9: 端到端验证

- [ ] **Step 1: 完整流程测试**

Run: `cd weekly-report-system && streamlit run app.py`

D 验证：
- `user41`（海外BD）登录 → 上传页显示"📊 PPT"格式提示 → 上传 .pptx 文件 → 提交成功
- `superior` 登录 → 领导查阅 → 查看海外BD 成员的 PPT 文件 → 预览/降级提示正确

B 验证：
- `admin` 登录 → 系统管理 → 新增用户 → 编辑用户 → 停用用户

C 验证：
- `admin` 登录 → 模块设置 → 修改截止时间 → 对应模块成员看到新截止时间

- [ ] **Step 2: Final commit（如有遗漏修复）**

```bash
git add -A && git commit -m "chore: Phase 3 final adjustments after E2E verification"
```
