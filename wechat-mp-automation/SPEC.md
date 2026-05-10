# 微信公众号自动化系统 — 产品需求规格说明书（模块化版）

> **设计原则**：把大系统拆成5个独立子项目（模块），每个模块**能单独开发、单独测试、单独跑起来**。先做最小可用版本（MVP），再逐步叠加功能。最后通过标准接口把5个模块拼装成完整系统。

---

## 📦 模块全景图

```
┌─────────────────────────────────────────────────────────┐
│                    完整系统（Phase 5 拼装）                │
│                                                         │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌────────┐ │
│  │ 模块 A  │──▶│ 模块 B  │──▶│ 模块 C  │──▶│ 模块 D │ │
│  │ 信息采集 │   │ 内容改写 │   │ 内容格式化│   │ 公众号发布│ │
│  └─────────┘   └─────────┘   └─────────┘   └────────┘ │
│       ▲                                        ▲       │
│       │            ┌─────────┐                 │       │
│       └────────────│ 模块 E  │─────────────────┘       │
│                    │ 调度中心 │                         │
│                    └─────────┘                         │
└─────────────────────────────────────────────────────────┘
```

**模块之间的数据流**：
- 模块 A 产出 → 原始内容列表（JSON 标准格式）
- 模块 B 产出 → 改写后的内容列表（JSON 标准格式）
- 模块 C 产出 → 格式化+配图后的发布稿（JSON 标准格式）
- 模块 D 产出 → 发布结果（成功/失败+链接）
- 模块 E 是"大脑"，按时间表调度 A→B→C→D 的执行

**关键约定**：所有模块之间通过 **JSON 文件 + SQLite 数据库** 传递数据。不依赖网络调用，不依赖共享内存。每个模块都有独立的命令行入口，可以直接 `python main.py` 跑。

---

## 🧱 模块 A：信息采集模块

### 定位
从互联网上自动抓取内容，输出标准化的原始内容列表。**这是整个系统的"入口"，没有数据，后面所有模块都跑不起来。**

### MVP 目标（最小可用版本）
只做 **RSS 订阅源**，能从任意 RSS 地址拉取文章，存入本地数据库。

### 完整功能清单

#### A1. 数据源管理
| 功能 | 说明 | 优先级 |
|------|------|--------|
| 添加数据源 | 通过配置文件添加 RSS/网页等数据源 | P0-MVP |
| 启用/禁用数据源 | 每个数据源可独立开关 | P0-MVP |
| 数据源分组 | 按主题/行业对数据源分组管理 | P2 |
| 数据源健康检查 | 检测数据源是否可访问、内容是否更新 | P1 |

#### A2. 支持的数据源类型
| 数据源 | 采集方式 | 优先级 | 备注 |
|--------|----------|--------|------|
| RSS/Atom | feedparser 解析 | P0-MVP | 最基础，先只做这个 |
| 微信公众号 | 搜狗微信搜索 / 公众号历史文章 | P1 | 需要处理反爬 |
| 知乎 | 知乎热榜 + 话题 + 搜索 | P1 | 可用知乎 API 或爬虫 |
| YouTube | YouTube Data API v3 | P1 | 需要 API Key |
| 小红书 | 第三方API或爬虫 | P2 | 反爬严格，难度高 |
| 抖音 | 第三方API | P2 | 同上 |
| 通用网页 | BeautifulSoup 爬取 | P1 | 用户指定URL+CSS选择器 |
| 微博 | 微博搜索API | P2 | 需要Cookie |

#### A3. 采集规则配置
每个数据源可配置以下规则（YAML 格式）：

```yaml
sources:
  - id: "tech-rss"
    type: "rss"
    url: "https://example.com/feed.xml"
    enabled: true
    schedule: "0 */4 * * *"    # 每4小时采集一次
    filters:
      time_range: 7            # 只采集最近7天的
      min_words: 500           # 最少500字
      include_keywords: ["AI", "大模型", "GPT"]  # 包含任一关键词
      exclude_keywords: ["广告", "推广"]          # 排除包含这些词的
      include_mode: "any"      # any=包含任一, all=包含全部
    dedup:
      by: "url"                # 按URL去重, 可选 title/content_hash
      window: 30               # 30天内的去重窗口
```

#### A4. 去重机制
| 策略 | 说明 | 优先级 |
|------|------|--------|
| URL 去重 | 相同URL不重复采集 | P0-MVP |
| 标题相似度去重 | 标题相似度>80%视为重复 | P1 |
| 内容指纹去重 | 对内容做 SimHash，相似度>85%去重 | P2 |

#### A5. 输出格式（标准JSON）
```json
{
  "batch_id": "20260510_143052",
  "source_id": "tech-rss",
  "collected_at": "2026-05-10T14:30:52+08:00",
  "items": [
    {
      "id": "uuid-xxx",
      "source_type": "rss",
      "source_name": "36氪",
      "url": "https://36kr.com/p/xxx",
      "title": "OpenAI发布GPT-5",
      "author": "张三",
      "published_at": "2026-05-10T12:00:00+08:00",
      "content": "全文内容...",
      "summary": "摘要...",
      "metadata": {
        "categories": ["AI"],
        "tags": ["GPT", "大模型"],
        "word_count": 3200
      }
    }
  ],
  "stats": {
    "total": 10,
    "filtered": 6,
    "deduped": 2,
    "final": 2
  }
}
```

### 独立运行方式
```bash
# 采集所有已启用的数据源
python -m src.sources collect --all

# 采集指定数据源
python -m src.sources collect --source tech-rss

# 测试数据源连通性
python -m src.sources test --source tech-rss

# 查看已采集的内容
python -m src.sources list --limit 20
```

### 文件结构
```
src/sources/
├── __init__.py
├── base.py           # BaseSource 抽象基类
├── rss.py            # RSS 数据源（MVP）
├── wechat.py         # 微信公众号
├── zhihu.py          # 知乎
├── youtube.py        # YouTube
├── web_scraper.py    # 通用网页爬虫
├── xiaohongshu.py    # 小红书（P2）
├── douyin.py         # 抖音（P2）
└── weibo.py          # 微博（P2）
config/sources/       # 数据源配置文件
├── tech.yaml         # 科技类
├── finance.yaml      # 财经类
└── custom.yaml       # 用户自定义
```

---

## 🧱 模块 B：内容改写模块

### 定位
把模块 A 采集的原始内容，通过 AI 改写成符合公众号风格的文章。**这是整个系统的"核心价值"，改写质量直接决定最终输出质量。**

### MVP 目标
只做**单篇改写**——输入一篇原始文章 + 改写指令，输出改写后的文章。支持一种 LLM（OpenAI 兼容接口）。

### 完整功能清单

#### B1. 改写策略
| 策略 | 说明 | 适用场景 | 优先级 |
|------|------|----------|--------|
| 深度改写 | 保留核心信息，完全重写表达 | 原创度要求高 | P0-MVP |
| 精简摘要 | 压缩到指定字数 | 快讯/简报类 | P0-MVP |
| 风格迁移 | 按指定风格改写 | 品牌调性统一 | P1 |
| 多角度改写 | 同一内容生成多个角度版本 | A/B测试 | P2 |
| 翻译改写 | 外文内容翻译+本地化 | 海外资讯 | P2 |

#### B2. 风格配置
支持通过配置文件定义改写风格：

```yaml
styles:
  - id: "professional"
    name: "专业深度"
    description: "行业分析师视角，数据和逻辑驱动"
    prompt_template: |
      你是一位资深行业分析师，请将以下内容改写为专业深度分析文章。
      要求：
      1. 保持事实准确性，不编造数据
      2. 增加行业背景和分析视角
      3. 使用专业但不晦涩的语言
      4. 目标字数：{target_words}字
      原文：
      {content}
    target_words: 3000
    reference_examples: []    # 可选：提供参考范文

  - id: "casual"
    name: "轻松科普"
    description: "通俗易懂，像跟朋友聊天"
    prompt_template: |
      你是一位科技博主，请用轻松有趣的方式改写以下内容。
      要求：
      1. 用大白话解释专业概念
      2. 可以加适当的比喻和类比
      3. 语气亲切自然，不要太正式
      4. 目标字数：{target_words}字
      原文：
      {content}
    target_words: 2000
```

#### B3. LLM 配置
```yaml
llm:
  provider: "openai"           # openai | anthropic | qwen | deepseek | local
  api_key: "${OPENAI_API_KEY}" # 从环境变量读取
  model: "gpt-4o"
  base_url: "https://api.openai.com/v1"  # 兼容 OpenAI 接口即可
  timeout: 120
  retry: 3
  max_tokens: 4096
  temperature: 0.7
```

支持多 LLM 配置，不同风格可以用不同模型：
```yaml
llm_profiles:
  high_quality:
    model: "gpt-4o"
    temperature: 0.7
  fast_draft:
    model: "gpt-4o-mini"
    temperature: 0.9
  chinese_optimized:
    model: "qwen-max"
    temperature: 0.7
```

#### B4. 敏感词过滤
改写完成后自动检测敏感词：
| 功能 | 说明 | 优先级 |
|------|------|--------|
| 内置敏感词库 | 政治/色情/暴力等基础词库 | P0-MVP |
| 自定义敏感词 | 用户可添加行业敏感词 | P1 |
| 敏感词替换 | 自动替换为安全词汇 | P1 |
| 敏感词标记 | 不替换但标记提醒人工审核 | P1 |
| 风险评分 | 对内容给出风险等级(0-100) | P2 |

#### B5. 改写质量评估
| 指标 | 说明 | 优先级 |
|------|------|--------|
| 原创度检测 | 与原文的相似度，目标<30% | P1 |
| 可读性评分 | Flesch-Kincaid 等可读性指标 | P2 |
| 信息完整度 | 核心信息是否保留 | P2 |
| 字数达标 | 是否在目标字数范围内 | P0-MVP |

#### B6. 输出格式
```json
{
  "original_id": "uuid-xxx",
  "rewrite_id": "uuid-yyy",
  "strategy": "deep_rewrite",
  "style": "professional",
  "model": "gpt-4o",
  "title": "改写后的标题",
  "content": "改写后的正文...",
  "word_count": 3200,
  "quality": {
    "originality": 0.72,
    "readability": 0.85,
    "info_retention": 0.90,
    "word_count_match": true,
    "sensitive_words": [],
    "risk_score": 5
  },
  "metadata": {
    "tokens_used": 4500,
    "latency_ms": 3200,
    "cost_usd": 0.045
  }
}
```

### 独立运行方式
```bash
# 改写单篇文章（从数据库取最新一条未改写的）
python -m src.processors rewrite --latest

# 改写指定文章
python -m src.processors rewrite --id uuid-xxx

# 批量改写所有未改写的文章
python -m src.processors rewrite --all-pending

# 用指定风格改写
python -m src.processors rewrite --style casual --id uuid-xxx

# 预览改写效果（不存库）
python -m src.processors rewrite --dry-run --id uuid-xxx
```

### 文件结构
```
src/processors/
├── __init__.py
├── rewrite.py        # 改写引擎
├── filter.py         # 敏感词过滤
├── quality.py        # 质量评估
├── prompts/          # Prompt 模板
│   ├── deep_rewrite.yaml
│   ├── summary.yaml
│   ├── style_transfer.yaml
│   └── multi_angle.yaml
config/styles/        # 风格配置
├── professional.yaml
├── casual.yaml
└── custom.yaml
config/keywords/      # 敏感词库
├── politics.txt
├── violence.txt
└── custom.txt
```

---

## 🧱 模块 C：内容格式化模块

### 定位
把模块 B 改写好的纯文本，加工成公众号可直接发布的格式——排版、配图、生成封面。**让文章从"能看"变成"好看"。**

### MVP 目标
只做**文本排版**——将 Markdown 转成公众号 HTML，支持基础排版样式。

### 完整功能清单

#### C1. 排版引擎
| 功能 | 说明 | 优先级 |
|------|------|--------|
| Markdown → 公众号 HTML | 基础转换 | P0-MVP |
| 排版模板 | 可选多种排版样式（极简/商务/活泼等） | P0-MVP |
| 自定义排版 | 用户可自定义 CSS 样式 | P1 |
| 代码块高亮 | 技术文章的代码块渲染 | P1 |
| 表格排版 | 复杂表格的公众号适配 | P2 |

#### C2. 配图引擎
| 功能 | 说明 | 优先级 |
|------|------|--------|
| AI 生成配图 | DALL-E / Flux 等生成配图 | P1 |
| 图库搜索配图 | Unsplash / Pexels 搜图 | P1 |
| 手动上传配图 | 指定本地图片路径 | P0-MVP |
| 封面图生成 | 标题+风格→封面图 | P1 |
| 图片数量控制 | 配置每篇文章配几张图 | P0-MVP |
| 图片位置控制 | 指定图片插入位置（段落之间/固定间隔） | P1 |
| 图片尺寸适配 | 自动裁剪为公众号支持的尺寸 | P1 |

配图配置示例：
```yaml
image:
  count: 3                    # 每篇文章配3张图
  position: "between_sections" # between_sections | fixed_interval | manual
  interval: 3                 # 每隔3段插一张（fixed_interval模式）
  source: "unsplash"          # unsplash | pexels | ai_generate | local
  style: "minimal"            # 图片风格
  size: "900x383"             # 公众号推荐尺寸
  cover:
    enabled: true
    size: "900x383"           # 公众号封面图2.35:1比例
    style: "gradient_text"    # gradient_text | photo_overlay | ai_generate
```

#### C3. 多平台导出
| 平台 | 格式 | 优先级 |
|------|------|--------|
| 微信公众号 | HTML（直接粘贴到编辑器） | P0-MVP |
| 小红书 | 纯文本+图片包（ZIP） | P1 |
| 抖音 | 口播稿（纯文本）+ 字幕文件（SRT） | P2 |
| YouTube | 英文翻译+SEO描述 | P2 |
| 知乎 | Markdown | P2 |
| 通用 Markdown | .md 文件 | P1 |

#### C4. 输出格式
```json
{
  "article_id": "uuid-zzz",
  "format": "wechat_mp",
  "title": "文章标题",
  "html": "<div class='article'>...</div>",
  "cover_image": "/output/covers/cover_xxx.jpg",
  "images": [
    { "url": "/output/images/img1.jpg", "position": "after_paragraph_3" },
    { "url": "/output/images/img2.jpg", "position": "after_paragraph_7" }
  ],
  "exports": {
    "markdown": "/output/exports/article_xxx.md",
    "xiaohongshu": "/output/exports/article_xxx_xhs.zip"
  },
  "metadata": {
    "word_count": 3200,
    "image_count": 3,
    "reading_time_min": 8
  }
}
```

### 独立运行方式
```bash
# 格式化指定文章
python -m src.processors format --id uuid-yyy

# 指定排版模板
python -m src.processors format --id uuid-yyy --template business

# 生成配图
python -m src.processors format --id uuid-yyy --with-images

# 导出到小红书格式
python -m src.processors format --id uuid-yyy --export xiaohongshu

# 预览排版效果（输出到HTML文件用浏览器打开）
python -m src.processors format --id uuid-yyy --preview
```

### 文件结构
```
src/processors/
├── formatter.py      # 排版引擎
├── image.py          # 配图引擎
├── exporter.py       # 多平台导出
config/templates/     # 排版模板
├── minimal.yaml      # 极简
├── business.yaml     # 商务
├── lively.yaml       # 活泼
└── custom.yaml       # 自定义
```

---

## 🧱 模块 D：公众号发布模块

### 定位
把模块 C 产出的发布稿，自动发布到微信公众号。**这是整个系统的"出口"，也是风险最高的模块——发错了就撤不回。**

### MVP 目标
只做**草稿箱发布**——自动创建草稿，人工确认后再发布。不做自动发布。

### 完整功能清单

#### D1. 公众号管理
| 功能 | 说明 | 优先级 |
|------|------|--------|
| 多公众号管理 | 支持配置多个公众号 | P0-MVP |
| AppID/Secret 配置 | 每个公众号独立配置 | P0-MVP |
| Token 管理 | access_token 自动刷新 | P0-MVP |
| 发布权限分级 | 草稿/预览/正式发布 | P0-MVP |

#### D2. 发布流程
```
创建草稿 → 预览验证 → 人工审核 → 确认发布
    │                       ↑
    └── 自动执行             └── 可选：自动或手动
```

| 步骤 | 说明 | 自动/手动 | 优先级 |
|------|------|-----------|--------|
| 上传素材（图片） | 图片上传到公众号素材库 | 自动 | P0-MVP |
| 创建草稿 | 标题+正文+封面 → 草稿箱 | 自动 | P0-MVP |
| 预览 | 发送到指定微信号预览 | 自动 | P0-MVP |
| 人工审核 | 审核人确认内容无误 | 手动 | P0-MVP |
| 发布 | 从草稿箱发布 | 手动（可配置为自动） | P0-MVP |
| 定时发布 | 设定发布时间，到时间自动发 | 自动 | P1 |

#### D3. 发布安全机制
| 功能 | 说明 | 优先级 |
|------|------|--------|
| 发布前预览 | 自动发送预览到管理员微信 | P0-MVP |
| 审核流程 | 必须人工确认才能发布（可关闭） | P0-MVP |
| 发布频率限制 | 每天最多发N篇（防误操作） | P1 |
| 发布日志 | 记录每次发布的完整信息 | P0-MVP |
| 失败重试 | 发布失败自动重试3次 | P1 |
| 回退机制 | 发布失败后自动回退到草稿状态 | P1 |

#### D4. 公众号配置
```yaml
accounts:
  - id: "main_account"
    name: "主账号"
    app_id: "${WX_MAIN_APP_ID}"
    app_secret: "${WX_MAIN_APP_SECRET}"
    default: true
    publish_mode: "draft"     # draft | preview | auto
    preview_users:            # 预览接收人
      - "admin_openid_xxx"
    reviewers:                # 审核人
      - "admin_openid_xxx"
    daily_limit: 3            # 每天最多发3篇
```

#### D5. 输出格式
```json
{
  "publish_id": "pub-xxx",
  "article_id": "uuid-zzz",
  "account_id": "main_account",
  "status": "published",
  "media_id": "微信公众号素材ID",
  "publish_time": "2026-05-10T16:00:00+08:00",
  "preview_url": "预览链接",
  "article_url": "发布后的文章链接",
  "error": null
}
```

### 独立运行方式
```bash
# 发布到草稿箱
python -m src.publishers publish --id uuid-zzz --account main --mode draft

# 发送预览
python -m src.publishers preview --id uuid-zzz --to admin_openid_xxx

# 确认发布（从草稿到正式）
python -m src.publishers confirm --media-id MEDIA_ID

# 查看发布状态
python -m src.publishers status --publish-id pub-xxx

# 查看今日发布统计
python -m src.publishers stats --today
```

### 文件结构
```
src/publishers/
├── __init__.py
├── wechat_mp.py     # 微信公众号发布
├── preview.py       # 预览管理
├── audit.py         # 审核流程
├── media.py         # 素材管理
config/accounts/     # 公众号配置
├── main.yaml
└── secondary.yaml
```

---

## 🧱 模块 E：调度中心模块

### 定位
系统的"大脑"——按时间表自动调度 A→B→C→D 的执行，管理状态，处理异常。**没有它，你就得手动一个模块一个模块地跑。**

### MVP 目标
只做**手动触发一条链路**——一条命令跑完 A→B→C→D，不做定时调度。

### 完整功能清单

#### E1. 工作流引擎
| 功能 | 说明 | 优先级 |
|------|------|--------|
| 串行执行 | A→B→C→D 依次执行 | P0-MVP |
| 条件分支 | 根据上一步结果决定下一步 | P1 |
| 并行执行 | 多个数据源同时采集 | P2 |
| 错误恢复 | 任意步骤失败后，可从该步骤重试 | P1 |
| 步骤跳过 | 配置跳过某些步骤（如跳过配图） | P1 |

工作流状态机：
```
IDLE → COLLECTING → COLLECTED → REWRITING → REWRITTEN
  → FORMATTING → FORMATTED → PUBLISHING → PUBLISHED → IDLE

任何状态 → ERROR（失败后可回到上一个成功状态重试）
任何状态 → CANCELLED（手动取消）
```

#### E2. 定时调度
| 功能 | 说明 | 优先级 |
|------|------|--------|
| Cron 表达式 | 标准 cron 语法配置执行时间 | P1 |
| 采集频率 | 每个数据源独立配置采集频率 | P1 |
| 发布时间窗 | 指定每天的发布时间段（如8:00-22:00） | P1 |
| 错峰发布 | 避开用户不活跃的时段 | P2 |

调度配置示例：
```yaml
schedules:
  - name: "每日科技资讯"
    cron: "0 8,14,20 * * *"    # 每天8/14/20点执行
    workflow: "default"
    sources: ["tech-rss", "zhihu-tech"]
    style: "professional"
    account: "main_account"
    publish_window: "08:00-22:00"
    publish_mode: "draft"      # 草稿模式，人工审核后发布
```

#### E3. 状态管理
| 功能 | 说明 | 优先级 |
|------|------|--------|
| SQLite 持久化 | 所有状态存入本地数据库 | P0-MVP |
| 状态追踪 | 每篇文章的完整生命周期记录 | P0-MVP |
| 状态查询 | 按状态/时间/来源筛选 | P1 |
| 状态恢复 | 程序重启后自动恢复未完成的任务 | P1 |

#### E4. 监控与告警
| 功能 | 说明 | 优先级 |
|------|------|--------|
| 执行日志 | 每次执行的详细日志 | P0-MVP |
| 成功率统计 | 采集/改写/发布的成功率 | P1 |
| 飞书/微信告警 | 关键错误推送到管理员 | P1 |
| 每日报告 | 每天汇总运行情况 | P2 |

#### E5. 数据存储
```yaml
storage:
  database:
    type: "sqlite"
    path: "./data/content.db"
  
  # 数据表结构（核心表）
  tables:
    - contents        # 原始内容
    - rewrites        # 改写结果
    - formatted       # 格式化结果
    - published       # 发布记录
    - sources         # 数据源配置
    - schedules       # 调度配置
    - execution_log   # 执行日志
```

### 独立运行方式
```bash
# 手动执行完整链路
python -m src.workflows run --all

# 只执行采集+改写
python -m src.workflows run --steps collect,rewrite

# 从指定步骤恢复执行
python -m src.workflows resume --from rewrite --batch-id 20260510_143052

# 查看执行状态
python -m src.workflows status

# 启动调度服务（守护进程）
python -m src.workflows serve --daemon
```

### 文件结构
```
src/workflows/
├── __init__.py
├── engine.py         # 工作流引擎
├── state_machine.py  # 状态机
├── scheduler.py      # 定时调度
├── recovery.py       # 错误恢复
src/scheduler/
├── __init__.py
├── cron.py           # Cron 解析
├── executor.py       # 任务执行器
src/storage/
├── __init__.py
├── database.py       # SQLite 操作
├── models.py         # 数据模型
src/monitoring/
├── __init__.py
├── logger.py         # 日志
├── metrics.py        # 指标统计
├── alerts.py         # 告警
```

---

## 🗓️ 开发阶段规划

### Phase 1：最小可用系统（MVP）—— 约1周

> **目标**：跑通一条完整链路——从RSS采集→AI改写→排版→存入草稿箱

| 任务 | 模块 | 具体内容 | 预估时间 |
|------|------|----------|----------|
| 项目初始化 | 全局 | pyproject.toml、目录结构、配置框架 | 0.5天 |
| RSS采集 | 模块A | feedparser解析、基础过滤、URL去重、存SQLite | 1天 |
| 单篇改写 | 模块B | OpenAI接口调用、一种改写策略、基础prompt | 1天 |
| 基础排版 | 模块C | Markdown→公众号HTML、一种排版模板、手动上传图片 | 1天 |
| 草稿箱发布 | 模块D | 微信公众号API对接、创建草稿、上传素材 | 1.5天 |
| 串行链路 | 模块E | 命令行入口、A→B→C→D串行执行、基础日志 | 0.5天 |
| 集成测试 | 全局 | 端到端跑通一条链路 | 0.5天 |

**MVP 交付标准**：
- ✅ 配置一个RSS源，能自动采集文章
- ✅ 采集的文章能自动改写
- ✅ 改写后的文章能自动排版
- ✅ 排版后的文章能自动进入公众号草稿箱
- ✅ 全流程一条命令完成

### Phase 2：增强采集 + 改写质量 —— 约1周

| 任务 | 模块 | 具体内容 |
|------|------|----------|
| 多数据源 | 模块A | 知乎、微信公众号、YouTube |
| 多改写策略 | 模块B | 精简摘要、风格迁移 |
| 敏感词过滤 | 模块B | 基础敏感词库+检测 |
| 标题去重 | 模块A | 标题相似度去重 |
| 图库配图 | 模块C | Unsplash/Pexels 搜索配图 |

### Phase 3：自动化 + 安全机制 —— 约1周

| 任务 | 模块 | 具体内容 |
|------|------|----------|
| 定时调度 | 模块E | Cron 表达式、守护进程 |
| 审核流程 | 模块D | 人工审核+预览确认 |
| 错误恢复 | 模块E | 失败重试、状态恢复 |
| 多公众号 | 模块D | 多账号管理 |
| 飞书告警 | 模块E | 关键错误推送 |

### Phase 4：多平台 + 高级功能 —— 约2周

| 任务 | 模块 | 具体内容 |
|------|------|----------|
| 多平台导出 | 模块C | 小红书、抖音、YouTube |
| AI配图 | 模块C | DALL-E/Flux 生成配图 |
| 小红书数据源 | 模块A | 小红书内容采集 |
| 内容指纹去重 | 模块A | SimHash 去重 |
| 质量评估 | 模块B | 原创度、可读性评分 |
| 每日报告 | 模块E | 运行数据汇总 |

### Phase 5：插件化 + 生态 —— 持续迭代

| 任务 | 模块 | 具体内容 |
|------|------|----------|
| 插件系统 | 全局 | 自定义数据源/改写策略/排版模板的插件机制 |
| Web UI | 全局 | 简单的Web管理界面 |
| API 接口 | 全局 | REST API，方便外部集成 |
| Docker 部署 | 全局 | 一键部署 |

---

## 🔗 模块间接口规范

所有模块之间通过 SQLite 数据库 + JSON 文件交互。核心约定：

### 数据库表结构

```sql
-- 原始内容
CREATE TABLE contents (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    url TEXT UNIQUE,
    title TEXT NOT NULL,
    content TEXT,
    summary TEXT,
    author TEXT,
    published_at DATETIME,
    metadata JSON,
    status TEXT DEFAULT 'collected',  -- collected | processing | processed | published | error
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 改写结果
CREATE TABLE rewrites (
    id TEXT PRIMARY KEY,
    content_id TEXT REFERENCES contents(id),
    strategy TEXT NOT NULL,
    style TEXT,
    title TEXT,
    content TEXT NOT NULL,
    word_count INTEGER,
    quality_score JSON,
    model TEXT,
    tokens_used INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 格式化结果
CREATE TABLE formatted (
    id TEXT PRIMARY KEY,
    rewrite_id TEXT REFERENCES rewrites(id),
    format TEXT NOT NULL,           -- wechat_mp | xiaohongshu | douyin | youtube
    html TEXT,
    cover_image TEXT,
    images JSON,
    exports JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 发布记录
CREATE TABLE published (
    id TEXT PRIMARY KEY,
    formatted_id TEXT REFERENCES formatted(id),
    account_id TEXT NOT NULL,
    media_id TEXT,
    status TEXT DEFAULT 'draft',    -- draft | previewed | published | failed
    publish_time DATETIME,
    article_url TEXT,
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 执行日志
CREATE TABLE execution_log (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    step TEXT NOT NULL,              -- collect | rewrite | format | publish
    status TEXT NOT NULL,            -- started | success | failed
    input_count INTEGER,
    output_count INTEGER,
    error TEXT,
    duration_seconds REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 模块间数据流

```
模块A写入 → contents 表（status='collected'）
模块B读取 → contents 表（status='collected'）→ 写入 rewrites 表 → 更新 contents.status='processed'
模块C读取 → rewrites 表 → 写入 formatted 表
模块D读取 → formatted 表 → 写入 published 表 → 更新 contents.status='published'
模块E负责 → 触发各模块执行 + 记录 execution_log
```

### 状态转换规则

```
collected → processing（改写开始）→ processed（改写完成）→ formatting → formatted → publishing → published
                                                                    ↑
任何中间状态 → error（失败）→ 可回到上一个成功状态重新执行
```

---

## ⚙️ 全局配置文件结构

```yaml
# config/config.yaml — 主配置文件
app:
  name: "wechat-mp-automation"
  version: "1.0.0"
  debug: false

# 各模块独立配置文件路径
modules:
  sources: "config/sources/"        # 模块A
  styles: "config/styles/"          # 模块B
  templates: "config/templates/"     # 模块C
  accounts: "config/accounts/"       # 模块D
  schedules: "config/schedules/"     # 模块E

# 共享配置
database:
  type: "sqlite"
  path: "./data/content.db"

llm:
  provider: "openai"
  api_key: "${OPENAI_API_KEY}"
  model: "gpt-4o"
  base_url: "https://api.openai.com/v1"

storage:
  output_path: "./output"
  log_path: "./logs"

logging:
  level: "INFO"
  file: "./logs/app.log"
```

---

## 📋 环境变量清单

```bash
# 必需
OPENAI_API_KEY=sk-xxx                    # LLM API Key

# 微信公众号（模块D必需）
WX_MAIN_APP_ID=wx1234                    # 公众号AppID
WX_MAIN_APP_SECRET=secret123             # 公众号AppSecret

# 可选
DALLE_API_KEY=sk-xxx                     # AI配图（Phase 4）
UNSPLASH_ACCESS_KEY=xxx                  # 图库配图（Phase 2）
PEXELS_API_KEY=xxx                       # 图库配图（Phase 2）
YOUTUBE_API_KEY=xxx                      # YouTube数据源（Phase 2）
FEISHU_WEBHOOK=xxx                       # 飞书告警（Phase 3）
```

---

## 🚫 不做什么（明确边界）

| 不做 | 原因 |
|------|------|
| 自己训练模型 | 用现成LLM API即可，不需要训练 |
| 浏览器自动化采集 | 容易封号，优先用API和RSS |
| 移动端App | 先做命令行+Web UI，不做原生App |
| 实时监控Dashboard | Phase 5 再考虑，先做好核心功能 |
| 多租户/用户系统 | 先单用户使用，不做多租户 |
| 评论管理 | 只做内容发布，不做互动管理 |
| 数据分析/BI | 只做采集→改写→发布，不做数据分析 |

---

## 🎯 成功指标

| 指标 | MVP目标 | 完整版目标 |
|------|---------|-----------|
| 采集成功率 | >90% | >95% |
| 改写原创度 | >50% | >70% |
| 端到端耗时 | <5分钟/篇 | <3分钟/篇 |
| 人工干预率 | <50% | <20% |
| 日发布量 | 3篇 | 10篇+ |
