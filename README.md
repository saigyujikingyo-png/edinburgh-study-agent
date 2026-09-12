<p align="center"><img src="assets/icon.svg" width="112" alt="UoE Companion icon"></p>

# UoE Companion · 爱丁堡校园助手

在 **ChatGPT Work** 中用自然语言集中查找学校资源、下载和阅读课件、整理事务。**Codex 用于开发，Work 用于日常使用和验收。** 独立开源项目，非爱丁堡大学官方产品。

Manage University of Edinburgh resources and personal workflows through natural language in ChatGPT Work or another MCP host. Each person uses their own campus account, local data and private connection.

[下载 0.4.0](https://github.com/saigyujikingyo-png/edinburgh-study-agent/releases/tag/v0.4.0) · [分享与安装](docs/SHARING.md) · [Work 连接](docs/WORK_SETUP.md) · [性能](docs/PERFORMANCE.md) · [验收范围](docs/WORK_ACCEPTANCE.md)

## 能做什么

在插件专属窗口完成校园登录和 MFA 后，后续请求复用会话。查询和下载通过结构化 DOM 与直接 HTTP 完成，无截图、视觉点击、逐文件“另存为”。学校会话过期时仍须重新登录。

| 功能 | 0.4.0 状态与边界 |
| --- | --- |
| Learn 课程与资源 | 已实现课程分页、受支持文件夹内容发现、查找原始附件、批量下载和完整性校验 |
| 读取文件 | 已实现 PDF、DOCX、PPTX、XLSX、TXT、CSV、Markdown 文本读取；可复用校验后的本地文件 |
| MyEd、EUCLID | 已实现受支持的门户和学生记录页面读取；正式课程可从 EUCLID Courses 核对 |
| Timetabler | 已实现显示页面读取；完整结构化课表同步尚未实现 |
| 活动、实习和就业 | 已实现受支持官网页面和 MyCareerHub 链接的有限范围读取；不是全站检索 |
| 集中管理 | 已实现带时间与来源的搜索、收藏、标签、本地待办和学习计划 |
| 日历 | 已实现本地 ICS 导入/导出；自动订阅、后台刷新和远程日历写入尚未实现 |
| 更多学校入口 | 收录 17 项服务，各自报告访问时间和覆盖范围；目录入口不代表完整接入 |
| 教师场景 | 可尝试本人有权限的资源读取与个人事务整理；教师专用 Learn、EUCLID 和管理后台尚未验收 |
| 对学校系统写入 | 尚未实现作业提交、批改评分、成绩发布、考勤、选课变更、活动报名、实习申请和消息发送 |
| 扫描件与外部平台 | OCR、视频转写、所有 LTI/外部供应商全覆盖尚未实现 |
| 多人共享 | 可分享源码/安装包，各自部署；统一托管、多租户隔离和一条公共 Work 连接服务所有人尚未实现 |

核心学生工作流已有 Windows 上的实际 Work 验收。macOS/Linux 的核心 CI 测试不等于校园登录或 Work 的端到端验收。教师专用能力不能从学生账号结果推断。详见[验收范围](docs/WORK_ACCEPTANCE.md)。

## 这样使用

- “刷新今年课程，下载这门课的课件和课程手册。”
- “读我已下载的课件，整理本周学习任务。”
- “查近期学校活动和实习信息，把这几个加入收藏。”
- “从 EUCLID 核对正式课程，再查看本周课表。”
- “告诉我哪些能力已实现，哪些老师功能还没验证。”

工具自动保存文件到本机。Work 可以通过插件读取文本；本机路径本身不是云端附件。结果会标明缓存或实时来源、时间、分页和未覆盖内容。

## 安装

已验证校园主机：Windows、Python 3.12、Google Chrome。核心要求 Python 3.11+。

```powershell
git clone https://github.com/saigyujikingyo-png/edinburgh-study-agent.git
cd edinburgh-study-agent
python scripts/install_runtime.py
```

安装器创建 `~/.edinburgh-study-agent/runtime` 和私有 `mcp.json`，不会把凭据写进源码。其他本地 MCP 主机可以使用该配置；Work 用户继续按 [Work 连接指南](docs/WORK_SETUP.md) 建立自己的私有连接并登录学校。Work 的初次连接仍需要配置，不是通用一键安装服务。

分享给同学或老师时发送本仓库或[发布页](https://github.com/saigyujikingyo-png/edinburgh-study-agent/releases)。每人独立安装、登录和连接；不要分享自己的浏览器资料、数据库、下载目录或私有 Work 连接。完整步骤见[分享说明](docs/SHARING.md)。

## 效率与兼容性

0.4.0 将筛选和分页下推到数据库，移除收藏查询中的逐条连接，缓存文档解析，并以精简响应、分页和最长 25 秒任务等待减少模型往返。每次读取仍校验文件 SHA-256；复用本地文件时明确不保证远端最新。

保留全部 **28 个工具 ID**、Python 包名、数据目录和插件内部标识以兼容已有安装；界面名称和图标为 UoE Companion。基准数据及冷启动取舍见[性能报告](docs/PERFORMANCE.md)。

## 开发与开源

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/smoke_mcp.py
python scripts/public_release.py
python scripts/package_plugin.py
```

MIT 许可证适用于本项目源码和原创图标，不授予学校课件的再分发权。没有复制第三方项目实现。[参考项目](docs/GITHUB_REFERENCES.md)包括 MCP Python SDK、Playwright 和 Blackboard 官方资料。[贡献指南](CONTRIBUTING.md) · [安全与隐私](SECURITY.md) · [发布流程](docs/RELEASING.md)
