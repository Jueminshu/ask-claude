# 周报收集与整理工具调研

> 调研日期：2026-07-28
> 调研范围：GitHub 上与周报收集、生成、整理相关的开源项目和 Claude Code Skills

---

## 一、自动采集生成类

### 1. Woozed/weekly-report-collector ⭐ 推荐

> **"一句话，替我交周报"** — 本地文档 + Git/SVN + QQ + 钉钉 → 自动采集信号，生成周报。

- **仓库**：<https://github.com/Woozed/weekly-report-collector>
- **定位**：面向 Cursor 用户的一键周报采集工具
- **采集来源**：
  - 本地文档（Windows Recent + 搜索索引/目录扫描）
  - Git/SVN（`git log` / `svn log`，`watch_roots` 下自动发现）
  - QQ（Framework QCE → `localhost:40653`）
  - 钉钉（PC 本地 `dingtalk.db` AES 解密 → SQLite）
- **使用方式**：对 Cursor 说「生成本周周报」或「一键周报」
- **产出**：`drafts/week-YYYY-MM-DD.md` + `drafts/week-YYYY-MM-DD-signals.json`
- **技术栈**：Python 3.10+ + MCP Server + PowerShell 脚本
- **局限**：目前主要面向 Cursor，MCP Server 可移植到 Claude Code

### 2. Muneeer/claude-standup ⭐ 推荐

> 从 Claude Code 会话记录自动生成日报/周报，纯本地运行。

- **仓库**：<https://github.com/Muneeer/claude-standup>
- **定位**：Claude Code 插件，自动读取会话转录生成报告
- **采集来源**：`~/.claude/projects/` 下的会话转录 + 可选 Git commits
- **安装**：
  ```bash
  /plugin marketplace add Muneeer/claude-standup
  /plugin install claude-standup
  ```
- **使用**：
  - `/standup` — 今日日报
  - `/standup week` — 周报汇总
  - `/standup 2026-06-19` — 指定日期
- **特点**：纯本地、无外部服务、零第三方依赖（Python 3.8+ 标准库）
- **配置**：`~/.claude-standup/config.json`，支持模板自定义、语言切换

---

## 二、团队协作 + 飞书/钉钉集成类

### 3. RoboZephyr/lark-skills ⭐ 重点推荐

> 从 GitHub/GitLab commit 自动生成团队周报，投递到飞书。

- **仓库**：<https://github.com/RoboZephyr/lark-skills>
- **定位**：飞书/Lark 自动化 Skill 合集，基于 Claude Code + lark-cli
- **包含的 7 个 Skill**：

| Skill | 功能 |
|--------|------|
| `lark-doc-personal` | 个人版飞书创建文档（user OAuth） |
| `lark-doc-deliver` | 企业版飞书 bot 创建 + 权限转移 + 消息投递 |
| `doc-summary` | 按关键词搜飞书文档 → 汇总 → 投递 |
| `weekly-report` | 从 Git 提交 → 成员摘要 → 结构化周报 → 飞书 |
| `progress-report` | 项目进度同步 → 飞书文档 |
| `meeting-action-sync` | 会议纪要 → 行动项提取 → 同步到文档 |
| `okr-writing` | OKR 制定/评审/润色（含 Google re:Work 方法论） |

- **weekly-report 工作流程**（7 步）：

```
读取配置 → Subagent并行采集 → OKR上下文(可选) → 汇总分析 → 创建飞书文档 → 权限转移 → 消息投递
```

- **核心亮点**：
  - **Subagent 并行**：每位成员独立 subagent，避免上下文溢出
  - **全分支遍历**：不只看 main，所有分支按 SHA 去重
  - **状态区分**：已合并 PR / 进行中 PR / 未归属 PR 的分支提交明确标注
  - **双文档产出**：原始数据文档 + 汇总分析文档
  - **权限自动化**：创建→转移所有权→Bot 重授权→多成员授权
  - **索引管理**：汇总入口文档自动追加，时间倒序
  - **定时任务**：launchd 每周一 09:00 自动执行

- **安装**：
  ```bash
  git clone https://github.com/RoboZephyr/lark-skills.git
  cd lark-skills && ./install.sh
  npm install -g @larksuite/cli
  python3 skills/weekly-report/scripts/init_index.py \
    --config skills/weekly-report/config.yaml \
    --title "团队工程周报"
  ```

- **局限**：
  - 不覆盖 QQ/钉钉采集
  - 定时任务依赖 launchd（macOS），Windows 需手动配置计划任务
  - 需要飞书自建应用和 lark-cli 配置

---

## 三、Agent Skill（可直接安装到 Claude Code）

### 4. abner235/weekly-report-html

> 「一页纸周报」HTML 渲染规范 Skill：结论先行、可打印 A4 的经营周报。

- **仓库**：<https://github.com/abner235/weekly-report-html>
- **定位**：把数据渲染成风格统一的专业周报，改一个 CSS 变量即可换主色
- **安装**：放入 `~/.claude/skills/weekly-report-html/`
- **设计规范**：
  - 结论先行 → 证据在后 → 行动收尾
  - 中性灰 + 唯一主色（默认深青 `#0f766e`）
  - 涨跌符号 `▲/▼` + 颜色双通道表达
  - 趋势→折线、占比→环图(≤5段)、明细→表格
  - 自带 `@media print` 适配 A4 打印
- **数据输入**：首选 Markdown 周报文档（`templates/source.example.md`），次选 JSON
- **适用场景**：已有数据，需要美化输出格式

### 5. HengYu2022/vibe-spark

> Claude Code Skill：被动检测重复工作模式 → 建议自动化 + 从 git history 生成周报。

- **仓库**：<https://github.com/HengYu2022/vibe-spark>
- **特点**：自动化发现 + 项目创意生成 + 周报自动生成三位一体

---

## 四、独立产品/工具

| 项目 | 仓库 | 亮点 |
|------|------|------|
| zero00004/weekly-report-builder | <https://github.com/zero00004/weekly-report-builder> | AI 驱动周报生成器，免费开源 |
| wynn2025/ai-weekly-report-generator | <https://github.com/wynn2025/ai-weekly-report-generator> | 从任务列表生成专业周报，零依赖 |
| haodehaode378/git-weekly | <https://github.com/haodehaode378/git-weekly> | 跨多仓库分析 commit 生成结构化周报 |
| supunakalanka76/weekly-report-system | <https://github.com/supunakalanka76/weekly-report-system> | 全栈 AI 周报系统（含审批、分析、通知） |
| Songx888/github-issue-weekly-report | <https://github.com/Songx888/github-issue-weekly-report> | 从 GitHub Issues 和 PR 生成周报 |

---

## 五、场景推荐矩阵

| 你的场景 | 推荐工具 | 理由 |
|----------|----------|------|
| 从 QQ/钉钉/本地文档自动采集周报素材 | weekly-report-collector | 唯一覆盖 IM 聊天记录采集 |
| 从 Claude Code 会话 + Git 自动生成 | claude-standup | 直接安装为插件，零配置 |
| 团队 Git 提交 → 周报 → 飞书 | lark-skills | 最完整的团队周报自动化方案 |
| 已有数据，要美化输出为一页纸 | weekly-report-html | 专业设计规范，改色即用 |
| 需要检测重复工作 + 自动生成周报 | vibe-spark | 被动自动化发现 |

---

## 六、与本机已安装工具的关系

本机已安装 [Superpowers](https://github.com/obra/superpowers) 插件（方法论文档见 `superpowers-skills.md`），与上述周报工具完全互补：

| 维度 | Superpowers | 周报工具 |
|------|-------------|----------|
| 定位 | 通用开发方法论（TDD/计划/审查） | 周报自动化 |
| 作用域 | 代码开发全流程 | 汇报与文档产出 |
| 可组合性 | 为周报工具的开发改进提供方法论支撑 | 不影响 Superpowers 工作流 |

---

## 七、周报系统建设记录

> 本节记录营销运作部周报收集系统的建设进度。

### 2026-07-28：需求确认 & 国内运营商模板分析

**项目背景**：
- 部门：营销运作部，约 60 人
- 现状：所有人通过 Outlook 邮件提交周报（Excel/PPT 附件），手动下载整理为 4 个模块汇总，提交给领导
- 目标：自动化采集 → 按模块整理 → 汇总 → 自动投递 + 辅助分析

**四个业务模块**：

| 模块 | 格式 | 状态 |
|------|------|------|
| 国内运营商 | Excel | ✅ 模板已分析 |
| 销售部 | Excel | 待分析 |
| 营销运营部 | Excel | 待分析 |
| 海外BD | PPT | 待分析 |

#### 国内运营商模板结构

- **格式**：Excel (.xlsx)
- **Sheet 规则**：每人一个 Sheet，以姓名命名
- **列结构**（6列固定模板）：

| 列 | 字段名 | 类型 | 说明 |
|------|------|------|------|
| A | 序号 | 自增编号 | 无上限，模板仅示例 5 行 |
| B | 重点项目 | 自由文本 | 本周重点推进的项目名称 |
| C | 子目标/关键举措 | 自由文本 | 具体行动拆解 |
| D | 本周工作进展 | 自由文本 | 本周实际完成情况 |
| E | 下周计划 | 自由文本 | 下周安排 |
| F | 风险及求助 | 自由文本 | 遇到的问题和需要的支持 |

#### 【国内运营商】初设计

**采集 → 合并 → 分析 → 投递**

**输入**：N 人通过 Outlook 邮件发送的 Excel 周报附件
**输出**：一个合并后的 Excel 文件

**合并 Excel 结构**：
```
【国内运营商】周报汇总_20260729.xlsx
├── 📑 目录               ← 超链接："时间+姓名"，点击跳转至对应 Sheet
├── 📊 本周分析            ← 提交率 / 风险聚类 / 重点项目 / 工作量
├── 张三                  ← 仅本周提交内容，无模板空行
├── 李四                  ← 仅本周提交内容
└── ...
```

**设计原则**：
- 不保留模板空行（某人填几行就显示几行）
- 不保留空白 Sheet（未提交的人不出现）
- 目录含超链接，一键跳转
- 分析 Sheet 作为汇总呈现

**可分析项**：

| 分析项 | 来源 | 输出 |
|------|------|------|
| 提交状态 | 人员名单 vs 目录 | 已提交/未提交清单，提交率 |
| 风险汇总 | F 列「风险及求助」 | 关键词聚类，高亮共性问题 |
| 重点项目 | B 列「重点项目」 | 去重归类，当前热点一览 |
| 工作量概况 | 行数 + D 列字数 | 各人员工作量粗估 |

**工具链**：OfficeCLI（读取）+ openpyxl（合并+超链接）+ Claude API（分析）

**开发状态**：✅ 端到端测试通过（2026-07-29）
- 采集模块：本地文件扫描模式已就绪
- 合并模块：目录超链接 + 去空行 + 分析 Sheet 完整工作
- 分析模块：提交率/风险聚类/重点项目/工作量
- 待接入：Microsoft Graph API（邮件自动采集）

**用法**：
```bash
cd weekly-report-system
# 放入周报到 data/raw/domestic_operator/
D:\Python312\python.exe main.py --module domestic_operator merge
```


#### 已安装工具

| 工具 | 用途 | 安装来源 |
|------|------|------|
| Superpowers | AI 开发方法论 | superpowers-marketplace |
| OfficeCLI | 读取/操作 Excel/Word/PPT | iOfficeAI/OfficeCLI |

---

## 附录：相关链接

- Superpowers 官网：<https://primeradiant.com/superpowers/>
- Superpowers Discord：<https://discord.gg/35wsABTejz>
- lark-cli 文档：<https://github.com/larksuite/cli>
- 飞书开放平台：<https://open.feishu.cn/app>
