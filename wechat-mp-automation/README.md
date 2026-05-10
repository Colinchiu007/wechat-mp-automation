# 微信公众号自动化系统

跨平台内容自动化解决方案：自动搜集 → AI改写 → 自动发布到公众号草稿箱

## 当前状态

**Phase 1 MVP 已完成** ✅ — 完整链路 `RSS采集 → AI改写 → 基础排版 → 公众号草稿箱` 已跑通

| 模块 | 状态 | 说明 |
|------|------|------|
| 模块A 数据采集 | ✅ MVP | RSS 采集完成，其他源脚手架 |
| 模块B 内容改写 | ✅ MVP | 5种策略，OpenAI/Anthropic LLM |
| 模块C 内容排版 | ✅ MVP | Markdown→公众号HTML，极简模板 |
| 模块D 公众号发布 | ✅ MVP | 草稿箱模式，图片上传 |
| 模块E 工作流引擎 | ✅ MVP | 串行pipeline，CLI入口 |

详见 [CHANGELOG.md](./CHANGELOG.md) 和 [SPEC.md](./SPEC.md)

## 快速开始

### 安装

```bash
git clone https://github.com/Colinchiu007/wechat-mp-automation.git
cd wechat-mp-automation
pip install -e ".[dev]"
```

### 配置

1. 编辑 `config/config.yaml` — 设置 LLM、数据库、改写风格、公众号账号
2. 编辑 `config/sources/tech.yaml` — 配置 RSS 数据源
3. 设置环境变量：

```bash
export OPENAI_API_KEY="sk-xxx"        # LLM API Key
export WX_APP_ID="wxXXX"             # 微信公众号 AppID
export WX_APP_SECRET="xxx"           # 微信公众号 AppSecret
```

### 运行

```bash
# 运行完整链路
python -m src.main run --all

# 只运行采集+改写
python -m src.main run --steps collect,rewrite

# 指定数据源和改写风格
python -m src.main run --source tech-rss --style professional

# 测试数据源连通性
python -m src.main sources test

# 采集指定数据源
python -m src.main sources collect --source 36kr

# 查看执行状态
python -m src.main status
```

### 测试

```bash
# E2E 集成测试（不需要 API Key）
python scripts/test_e2e.py

# 单模块测试
python scripts/test_db.py        # 数据库
python scripts/test_formatter.py # 格式化
python scripts/test_rss.py       # RSS 采集
```

## 项目结构

```
wechat-mp-automation/
├── src/
│   ├── main.py           # CLI 入口
│   ├── config/           # 配置加载与校验
│   ├── sources/          # 数据采集（RSS/知乎/YouTube等）
│   ├── processors/       # 内容处理（改写/格式化/配图/过滤）
│   ├── workflows/        # 工作流引擎
│   ├── publishers/       # 发布模块（公众号草稿箱）
│   ├── scheduler/        # 调度器（MVP:手动触发）
│   ├── storage/          # 数据存储（SQLite）
│   └── utils/            # 工具函数
├── config/
│   ├── config.yaml       # 主配置
│   └── sources/          # 数据源配置
│       └── tech.yaml     # 科技类 RSS
├── scripts/              # 测试脚本
├── tests/                # 单元测试
├── CHANGELOG.md          # 变更日志
├── SPEC.md               # 需求规格说明书
└── README.md             # 本文件
```

## Phase 规划

| Phase | 内容 | 状态 |
|-------|------|------|
| 1 | MVP: RSS采集+改写+排版+草稿箱 | ✅ 完成 |
| 2 | 多数据源+多风格改写+配图生成 | 🔲 |
| 3 | 定时调度+审核流程 | 🔲 |
| 4 | 多平台导出+REST API | 🔲 |
| 5 | 插件系统+完整拼装 | 🔲 |

## License

MIT
