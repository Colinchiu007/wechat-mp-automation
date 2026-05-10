# 微信公众号自动化 Skill

跨平台内容自动化解决方案：自动搜集信息 → AI改写 → 多平台发布

## 功能特性

### 📥 数据采集
- **多平台支持**：微信公众号、知乎、YouTube、小红书、抖音、微博、RSS
- **灵活配置**：每个数据源独立配置采集规则
- **智能筛选**：关键词、热度、时间范围过滤
- **去重机制**：URL、内容哈希、标题相似度去重

### ✍️ 内容处理
- **多种改写策略**：摘要提取、风格迁移、深度改写
- **风格配置**：可配置的文案风格和格式规则
- **敏感词检测**：内置+自定义敏感词库
- **SEO优化**：关键词密度、标题建议

### 🎨 配图生成
- **AI生成**：支持 DALL-E、Midjourney、Stable Diffusion
- **图库选择**：Unsplash、Pexels
- **智能嵌入**：自动判断最佳插入位置

### 📤 多平台发布
- **支持的平台**：微信公众号、小红书、抖音、YouTube、B站
- **定时发布**：Cron 表达式配置发布时间
- **多账号管理**：支持多个账号同时运营
- **工作流引擎**：灵活的任务流程控制

### 🔧 扩展性
- **插件系统**：支持自定义数据源、改写策略、发布平台
- **REST API**：完整的 API 接口
- **Webhook**：事件触发机制

## 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/Colinchiu007/wechat-mp-automation.git
cd wechat-mp-automation

# 安装依赖
pip install -e ".[dev]"

# 初始化配置
cp .env.example .env
# 编辑 .env 填入你的配置
```

### 配置

编辑 `config/config.yaml` 配置数据源、风格、账号等信息。

### 运行

```bash
# 运行单个任务
python -m src.main run --workflow default --source tech_news

# 启动调度器
python -m src.main scheduler

# 启动 API 服务
python -m src.main api
```

## 项目结构

```
wechat-mp-automation/
├── src/
│   ├── config/          # 配置加载
│   ├── sources/         # 数据采集
│   ├── processors/      # 内容处理
│   ├── workflows/       # 工作流引擎
│   ├── publishers/      # 发布模块
│   ├── scheduler/       # 调度器
│   ├── storage/         # 数据存储
│   ├── api/             # REST API
│   ├── plugins/         # 插件系统
│   └── utils/           # 工具函数
├── config/              # 配置文件
├── tests/               # 测试
└── docs/                # 文档
```

## 开发

```bash
# 运行测试
pytest

# 代码检查
ruff check src/
mypy src/

# 格式化
ruff format src/
```

## 文档

- [需求规格说明书](./SPEC.md)
- [配置指南](./docs/CONFIG.md)
- [API 文档](./docs/API.md)
- [插件开发](./docs/PLUGIN_DEV.md)

## License

MIT
