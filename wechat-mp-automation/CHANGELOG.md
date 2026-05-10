# 更新日志

本文档记录微信公众号自动化系统从项目初始化到当前的所有关键变动。

---

## [1.0.0-alpha.1] - 2026-05-10

### 新增

**项目初始化**
- 创建 GitHub 仓库：https://github.com/Colinchiu007/wechat-mp-automation
- 确定技术架构：定制 Skill + 调用现有 Skill 的混合路线
- 完成 SPEC.md 需求规格说明书（模块化版，5模块5阶段）

**模块 A - 数据采集层** (`src/sources/`)
- `base.py`: SourceBase 抽象基类，支持关键词/时间/热度过滤和 URL 去重
- `rss.py`: RSS 数据源，基于 feedparser，支持单 url 和 urls 列表两种配置格式
- `wechat.py`: 微信公众号搜索源（脚手架，Phase 2 完善）
- `zhihu.py`: 知乎热榜源（脚手架，Phase 2 完善）
- `youtube.py`: YouTube 源（脚手架，Phase 2 完善）
- `web_scraper.py`: 通用网页采集源（脚手架，Phase 2 完善）

**模块 B - 内容改写层** (`src/processors/rewrite.py`)
- 5 种改写策略：summarize / style_transfer / paraphrase / rewrite / expand
- LLM 调用：支持 OpenAI / Anthropic，自动重试（3次），429 限流处理
- 批量改写：并发控制（Semaphore=3），异常隔离
- 异步上下文管理器

**模块 C - 内容格式化层** (`src/processors/formatter.py`)
- Markdown → 微信公众号 HTML 转换
- 极简排版模板（677px 宽度，适配手机阅读）
- 支持元素：标题(h1-h3) / 粗体斜体 / 链接 / 列表 / 引用 / 代码块 / 行内代码 / 水平线
- 配图支持：按段落位置插入本地图片
- Markdown 导出功能

**模块 D - 公众号发布层** (`src/publishers/wechat_mp.py`)
- `WeChatMPClient`: 微信公众号 API 客户端
  - access_token 自动获取与刷新（提前5分钟）
  - 上传缩略图（thumb media）
  - 上传文章内图（返回 URL）
  - 创建草稿 / 获取草稿 / 删除草稿
  - 发布文章
- `WeChatPublisher`: 发布器
  - 处理封面图 + 文章内图替换
  - 自动关联 rewrite → content 获取标题和摘要
  - 发布结果写入数据库

**模块 E - 工作流引擎** (`src/workflows/engine.py`)
- 串行 pipeline：collect → rewrite → format → publish
- 支持 `--steps` 参数运行子集步骤
- 每步骤写入 execution_log 表记录执行状态和耗时
- 幂等处理：已改写/已格式化的内容自动跳过
- 错误恢复：改写失败的内容状态回退为 collected
- `state_machine.py`: 状态机定义（预留，Phase 3 完善）

**数据存储层** (`src/storage/database.py`)
- SQLite 异步操作（基于 aiosqlite）
- 5 张数据表：contents / rewrites / formatted / published / execution_log
- URL 去重机制（插入前检查）
- 内容状态追踪：collected → processing → processed
- 单例模式 + 自动建表
- 完整的业务方法：insert_content / insert_rewrite / insert_formatted / insert_published 等

**调度器** (`src/scheduler/cron.py`)
- MVP 阶段仅支持手动触发
- 预留 add_job / list_jobs / remove_job 接口（Phase 3 实现 Cron 定时）

**配置系统** (`src/config/`)
- `loader.py`: Pydantic 模型 + YAML 配置加载 + 环境变量解析（`${VAR}` 语法）
- `validator.py`: 配置校验
- `config/config.yaml`: 主配置文件（LLM / 数据库 / 改写 / 格式化 / 公众号账号）
- `config/sources/tech.yaml`: 示例 RSS 数据源（36氪/虎嗅/少数派）

**CLI 入口** (`src/main.py`)
- `python -m src.main run --all` — 运行完整链路
- `python -m src.main run --steps collect,rewrite` — 运行部分步骤
- `python -m src.main run --source tech-rss --style professional` — 指定数据源和风格
- `python -m src.main sources collect --source tech-rss` — 采集指定数据源
- `python -m src.main sources test --source tech-rss` — 测试数据源连通性
- `python -m src.main status` — 查看执行状态和最近日志

**测试**
- `scripts/test_db.py` — 数据库模块单元测试
- `scripts/test_formatter.py` — 格式化模块单元测试
- `scripts/test_rss.py` — RSS 采集测试
- `scripts/test_e2e.py` — 端到端集成测试（mock 数据，不调用 LLM/微信API）
- E2E 测试结果：3篇 mock 文章走完 collect→rewrite→format→publish 全链路 ✅

### 修复
- RSS 数据源配置兼容：同时支持 `url`（单字符串）和 `urls`（列表）两种格式
- formatter.py 引号冲突修复：CODE_BLOCK_STYLE 中 font-family 值引号嵌套问题

### 已知问题
- GitHub 推送失败（当前网络无法连接 github.com，代码仅本地 commit）
- PowerShell 中文输出乱码（GBK 终端编码问题，不影响程序运行）

---

## 架构决策记录

### AD-001: 技术路线选择
- **决策**: 定制 Skill + 调用现有 Skill 的混合路线
- **原因**: 现有 Skill 不能完全满足需求（多数据源采集、灵活改写策略、公众号 API），但可以复用底层能力
- **日期**: 2026-05-10

### AD-002: 数据库选型
- **决策**: Phase 1 使用 SQLite
- **原因**: MVP 阶段无需分布式存储，SQLite 零部署，aiosqlite 提供异步支持
- **日期**: 2026-05-10

### AD-003: 改写策略设计
- **决策**: 5 种策略（summarize/style_transfer/paraphrase/rewrite/expand），通过枚举配置
- **原因**: 不同场景需要不同深度的改写，策略化设计便于扩展
- **日期**: 2026-05-10

### AD-004: 发布模式
- **决策**: Phase 1 仅支持草稿箱模式，不自动发布
- **原因**: 自动发布风险高，需要人工审核环节
- **日期**: 2026-05-10
