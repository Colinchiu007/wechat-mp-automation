# 微信公众号自动化 - 配置说明

## 环境变量配置

在运行前需要配置以下环境变量：

```bash
# LLM 配置（必填）
# 支持: openai, anthropic, qwen, deepseek
export LLM_API_KEY="your-api-key-here"

# 微信公众号配置（必填）
export WX_APP_ID="your-app-id"
export WX_APP_SECRET="your-app-secret"
```

## 快速配置

### 方式 1: 环境变量（推荐开发用）

```powershell
# PowerShell
$env:LLM_API_KEY="sk-xxxx"
$env:WX_APP_ID="wx123456"
$env:WX_APP_SECRET="abc123"
```

### 方式 2: 直接修改 config.yaml

打开 `config/config.yaml`，修改以下字段：

```yaml
llm:
  provider: "deepseek"           # 可选: openai, anthropic, qwen, deepseek
  api_key: "${LLM_API_KEY}"     # 或直接填入 API key（不推荐）
  model: "deepseek-chat"       # 模型名称
  base_url: "https://api.deepseek.com/v1"  # API 端点

accounts:
  - id: "default"
    app_id: "${WX_APP_ID}"    # 或直接填入
    app_secret: "${WX_APP_SECRET}"
```

## LLM Provider 对照表

| Provider | model | base_url | 说明 |
|----------|-------|----------|------|
| openai | gpt-4o | https://api.openai.com/v1 | OpenAI |
| anthropic | claude-3-5-sonnet-20241022 | https://api.anthropic.com | Anthropic Claude |
| qwen | qwen-turbo | https://dashscope.aliyuncs.com/compatible-mode/v1 | 阿里通义千问 |
| deepseek | deepseek-chat | https://api.deepseek.com/v1 | DeepSeek |

## 配置完成后测试

```bash
python -m wechat_mp_automation run --test
```