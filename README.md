<p align="center"><img src="assets/icon.svg" width="112" alt="UoE Companion icon"></p>

# UoE Companion · 爱丁堡校园助手

面向学生，在 **ChatGPT 聊天、本地 Work、云端 Work、Claude、WorkBuddy、DeepSeek Agent** 等通用智能体中，用自然语言集中查找学校资源、下载和阅读课件、整理学习日程。**Codex 用于开发，Work 是实际使用与验收环境之一。** 独立开源项目，非爱丁堡大学官方产品。

Manage University of Edinburgh resources and personal workflows through natural language in ChatGPT Chat, local Work, cloud Work or another MCP host. Each person uses their own campus account, local data and private connection.

[下载 0.5.1](https://github.com/saigyujikingyo-png/edinburgh-study-agent/releases/tag/v0.5.1) · [多智能体接入 / Agent setup](docs/HOSTS.md) · [多语言 / Languages](docs/LANGUAGES.md) · [分享与安装](docs/SHARING.md) · [聊天 / Work 连接](docs/WORK_SETUP.md) · [性能](docs/PERFORMANCE.md) · [验收范围](docs/WORK_ACCEPTANCE.md)

## 能做什么

在插件专属窗口完成校园登录和 MFA 后，后续请求复用会话。查询和下载通过结构化 DOM 与直接 HTTP 完成，无截图、视觉点击、逐文件“另存为”。学校会话过期时仍须重新登录。

| 功能 | 0.5.1 学生版状态与边界 |
| --- | --- |
| Learn 课程与资源 | 已实现课程分页、受支持文件夹内容发现、查找原始附件、批量下载和完整性校验 |
| 读取文件 | 已实现 PDF、DOCX、PPTX、XLSX、TXT、CSV、Markdown 文本读取；可复用校验后的本地文件 |
| MyEd、EUCLID | 已实现受支持的门户和学生记录页面读取；正式课程可从 EUCLID Courses 核对 |
| Timetabler | 已实现显示页面读取；完整结构化课表同步尚未实现 |
| 活动、实习和就业 | 已实现受支持官网页面和 MyCareerHub 链接的有限范围读取；不是全站检索 |
| 集中管理 | 已实现带时间与来源的搜索、收藏、标签、本地待办和学习计划 |
| 学习日程 | 新增统一课程事件、已知截止日期与未完成个人任务；保留未知日期、来源、分页和时区 |
| 多语言 | 10 种服务目录语言、跨语言目录词匹配、持久偏好与临时覆盖；网页/课件说明由宿主智能体翻译，原文证据不变 |
| 多智能体 | 标准 MCP；Claude、WorkBuddy 配置合并器，DeepSeek 官方桥适配与实际桥接测试；完整模型验收范围见接入文档 |
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
- “显示本周学习日程，用上海时区展示具体时间，并保留学校原始截止日期。”
- “Trouve la bibliothèque et présente mon agenda de la semaine.”
- “以后用中文解释，保留英文课名和课程编号。”

工具自动保存文件到本机。Work 可以通过插件读取文本；本机路径本身不是云端附件。结果会标明缓存或实时来源、时间、分页和未覆盖内容。

## 安装

已验证校园主机：Windows、Python 3.12、Google Chrome。核心要求 Python 3.11+。

```powershell
git clone https://github.com/saigyujikingyo-png/edinburgh-study-agent.git
cd edinburgh-study-agent
python scripts/install_runtime.py
```

在 ChatGPT 只保留一个已安装且已连接的 **UoE Companion** 入口，供聊天、本地 Work 和云端 Work 共用。三个场景已分别完成状态和缓存课程查询；云端 Work 另有实时课程刷新验收。后台校园服务独立运行，不需要再安装一个同名的本机目录插件。详见[连接说明](docs/WORK_SETUP.md)与[验收范围](docs/WORK_ACCEPTANCE.md)。

安装器创建 `~/.edinburgh-study-agent/runtime` 和私有 `mcp.json`，不会把凭据写进源码。本地用户按[多智能体接入指南](docs/HOSTS.md)生成或合并客户端配置；Work 用户继续按 [Work 连接指南](docs/WORK_SETUP.md) 建立自己的私有连接并登录学校。Work 的初次连接仍需要配置，不是通用一键安装服务。

分享给同学或老师时发送本仓库或[发布页](https://github.com/saigyujikingyo-png/edinburgh-study-agent/releases)。每人独立安装、登录和连接；不要分享自己的浏览器资料、数据库、下载目录或私有 Work 连接。完整步骤见[分享说明](docs/SHARING.md)。

## 效率与兼容性

0.4.0 将筛选和分页下推到数据库，移除收藏查询中的逐条连接，缓存文档解析，并以精简响应、分页和最长 25 秒任务等待减少模型往返。每次读取仍校验文件 SHA-256；复用本地文件时明确不保证远端最新。

0.5.0 保留原有 **28 个工具 ID**，新增日程、偏好和按需帮助，共 31 个。新客户端默认使用 28 个工具的学生集，隐藏三个旧开发工具；完整集继续兼容已有 Work 连接。参数目录兼容 DeepSeek 的较窄 schema 子集，服务端校验不变。Python 包名、私有数据目录和内部标识保持兼容。实测学生集工具描述比完整集少约 20% token；基准范围见[性能报告](docs/PERFORMANCE.md)。

## 开发与开源

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/smoke_mcp.py
python scripts/public_release.py
python scripts/package_plugin.py
```

MIT 许可证适用于本项目源码和原创图标，不授予学校课件的再分发权。没有复制第三方项目实现。[参考项目](docs/GITHUB_REFERENCES.md)包括 MCP Python SDK、Playwright 和 Blackboard 官方资料。[贡献指南](CONTRIBUTING.md) · [安全与隐私](SECURITY.md) · [发布流程](docs/RELEASING.md)
