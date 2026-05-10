# 微信公众号自动化 (wechat-mp-automation)

[English](#english) | [中文](#中文)

---

## English

### Introduction

微信公众号自动化工具，帮助创作者实现「数据采集 → AI改写 → 自动发布」的全流程自动化。支持多种数据源和LLM providers。

### Features

- **Multi-source Collection**: RSS, 知乎, YouTube, WebScraper
- **AI Rewriting**: 5 strategies (Summarize, Style Transfer, Paraphrase, Rewrite, Expand)
- **Auto-publishing**: Create drafts, publish articles to WeChat Official Accounts
- **Flexible Configuration**: Support multiple LLM providers (OpenAI, Anthropic, Qwen, DeepSeek)

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Colinchiu007/wechat-mp-automation.git
cd wechat-mp-automation

# 2. Configure environment
# See CONFIG.md for details
export LLM_API_KEY="your-api-key"
export WX_APP_ID="your-app-id"
export WX_APP_SECRET="your-app-secret"

# 3. Run
python -m wechat_mp_automation run
```

### Configuration

Edit `config/config.yaml` or set environment variables. See `CONFIG.md` for details.

### License

MIT

---

## 中文

### 简介

微信公众号自动化工具，帮助创作者实现「数据采集 → AI改写 → 自动发布」的全流程自动化。

### 功能特性

- **多源采集**: RSS订阅、知乎专栏、YouTube、Web网页采集
- **AI改写**: 5种改写策略（摘要、风格转换、改写、扩写、缩写）
- **自动发布**: 创建草稿箱、发布文章到微信公众号
- **灵活配置**: 支持多种LLM providers (OpenAI, Anthropic, Qwen, DeepSeek)

### 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/Colinchiu007/wechat-mp-automation.git
cd wechat-mp-automation

# 2. 配置环境变量
# 详见 CONFIG.md
$env:LLM_API_KEY="your-api-key"
$env:WX_APP_ID="your-app-id"
$env:WX_APP_SECRET="your-app-secret"

# 3. 运行
python -m wechat_mp_automation run
```

### 配置说明

编辑 `config/config.yaml` 或设置环境变量。详见 `CONFIG.md`。

### 许可证

MIT