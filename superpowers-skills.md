# Superpowers — Claude Code 智能体技能框架

> 安装日期：2026-07-28
> 仓库：[obra/superpowers](https://github.com/obra/superpowers)
> 安装来源：superpowers-marketplace

---

## 简介

Superpowers 是由 Jesse Vincent 和 Prime Radiant 团队打造的完整智能体软件开发方法论。它让你的 AI 编程助手遵循严谨的工作流，而非"瞎写代码"。

- **核心哲学**：TDD 优先、系统化优于临时应付、简洁优于复杂、证据优于宣称
- **自动激活**：技能按描述自动触发，用户无需手动调用

---

## 已安装技能清单

### 测试
- `test-driven-development` — 红-绿-重构循环（含测试反模式参考）

### 调试
- `systematic-debugging` — 四阶段根因分析
- `verification-before-completion` — 修复后验证

### 协作
- `brainstorming` — 苏格拉底式设计对话
- `writing-plans` — 详细实现计划（2-5分钟/任务）
- `executing-plans` — 批量执行+人工检查点
- `subagent-driven-development` — 子智能体驱动开发+两阶段审查
- `dispatching-parallel-agents` — 并行子智能体工作流
- `requesting-code-review` — 代码审查清单
- `receiving-code-review` — 响应审查反馈
- `using-git-worktrees` — 隔离的并行开发分支
- `finishing-a-development-branch` — 合并/PR决策流程

### 元技能
- `writing-skills` — 创建新技能
- `using-superpowers` — 技能系统使用入门

---

## 基本工作流

```
头脑风暴 → 设计方案确认 → 编写计划 → 子智能体执行 → 代码审查 → 完成分支
```

---

## 安装命令

```bash
# 添加市场
claude plugin marketplace add obra/superpowers-marketplace

# 安装插件
claude plugin install superpowers@superpowers-marketplace
```

---

## 更新

```bash
/plugin update superpowers@superpowers-marketplace
```

---

## 相关资源

- 官方博客（发布公告）：<https://blog.fsck.com/2025/10/09/superpowers/>
- 商业支持：sales@primeradiant.com
- Discord 社区：<https://discord.gg/35wsABTejz>
