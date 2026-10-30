# Local Docs Workbench · 本地资料工作台

[![DSH Skill](https://img.shields.io/badge/DeepSeek%20Harness-skill-4a7dff)](https://github.com/Rexray117/Local-Docs-Workbench-Skill)
[![version](https://img.shields.io/badge/version-1.1.0-brightgreen)](https://github.com/Rexray117/Local-Docs-Workbench-Skill/releases)
[![license](https://img.shields.io/badge/license-MIT-blue)](./LICENSE)

> 一个 **DeepSeek Harness（DSH）/ Agent Skill**：`local-docs-workbench` v1.1.0。

从本地既有文档（md/docx）抽取真实数据，构建"单文件、全内联、零外链"的本地工作台 HTML， 并用 Node DOM 桩 + 无头 Chrome 双重验证。适用于把散落的项目资料变成可检索、可校验、 可归档的只读索引页，且要求不部署、不上传、不改动源文件的场景。 触发词：搭建工作台、生成单文件HTML工作台、本地资料索引页、把md转成工作台、 抽取文档生成看板、workbench from local docs。

## 适用场景

把本仓库整体放进 agent 的技能目录即可按描述自动触发；也可以在对话里直接点名 `local-docs-workbench`。

## 目录结构

```
`SKILL.md`
`LICENSE`
`.gitignore`

```

## 安装

### DSH（DeepSeek Harness）

技能目录放到用户级技能根：

```powershell
# Windows
git clone https://github.com/Rexray117/Local-Docs-Workbench-Skill.git "$env:USERPROFILE\.dsh\skills\local-docs-workbench"
```

```bash
# macOS / Linux
git clone https://github.com/Rexray117/Local-Docs-Workbench-Skill.git ~/.dsh/skills/local-docs-workbench
```

也可以用 DSH 的插件管理安装本地目录：

```
plugin_manager action=install_bundle target=<本仓库绝对路径>
```

### 其他 agent（Codex / WorkBuddy / Claude Code）

技能根分别位于 `~/.codex/skills`、`~/.workbuddy/skills`、`~/.claude/skills`，把本仓库克隆成其中的 `local-docs-workbench` 子目录即可（技能名以 `SKILL.md` 的 `name: local-docs-workbench` 为准）。

## 版本

- 当前版本：**v1.1.0**（与 `SKILL.md` 的 `version` 字段一致）
- 变更记录见仓库提交历史

## License

MIT © 2026 Rexray117
