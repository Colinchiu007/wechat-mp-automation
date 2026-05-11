# 代码注释完善工作

## 目标

为微信公众号自动化项目的四个核心模块添加详细注释。

## 完成情况

### 已添加注释的模块

1. **database.py** (24,845 bytes)
   - 模块级说明：职责、设计决策、数据流
   - 表字段注释：每个字段的作用和约束
   - 方法级注释：参数、返回值、设计决策
   - 幂等性说明：去重机制详解
   - 单例模式说明：为什么用单例

2. **engine.py** (27,832 bytes)
   - 模块级说明：核心设计、工作流状态机
   - 状态机图示：ASCII 图展示状态转换
   - 步骤详解：每个步骤的目的、流程、错误处理
   - 幂等性保证：如何避免重复处理
   - Phase 规划：从 MVP 到完整版的演进

3. **rewrite.py** (26,628 bytes)
   - 模块级说明：LLM 集成、成本控制
   - 策略详解：5 种改写策略的目的和适用场景
   - 配置说明：RewriteConfig 各字段含义
   - 系统提示词：每种策略的提示词模板
   - 并发控制：Semaphore 限制为 3 的原因
   - 重试机制：指数退避处理 429 错误

4. **wechat_mp.py** (22,896 bytes)
   - 模块级说明：API 文档链接、安全注意事项
   - Access Token 管理：自动刷新策略（提前 5 分钟）
   - 图片上传差异：封面图（media_id）vs 文章内图（URL）
   - 发布流程：从上传图片到创建草稿的完整流程
   - Phase 规划：从草稿箱模式到自动发布

## 注释风格

- **为什么**：设计决策（如"为什么用 SQLite"、"为什么是串行而非并行"）
- **是什么**：方法功能、参数含义、返回值结构
- **怎么用**：使用示例、配置示例
- **注意**：API 限制、安全事项、常见坑点

## 未添加注释的模块

以下模块注释较少，但不是核心关注点：
- `src/sources/base.py`：接口定义，相对直观
- `src/sources/rss.py`：逻辑简单，已有基本注释
- `src/processors/formatter.py`：格式转换，逻辑清晰
- `src/config/loader.py`：配置加载，已有 docstring

## 后续建议

1. 如需进一步完善，可添加：
   - 使用手册文档（docs/usage.md）
   - API 文档（使用 Sphinx 或 MkDocs）
   - 架构图（使用 Mermaid 或 PlantUML）

2. 代码审查时关注：
   - 注释是否与代码一致
   - 是否有遗漏的复杂逻辑
   - 是否有误导性注释

## Git 提交记录

- `8604cda`: docs: add detailed comments to database.py and engine.py
- `5b258cd`: docs: add detailed comments to rewrite.py and wechat_mp.py

## 文件变更

```
src/storage/database.py    | +300 lines (added comments)
src/workflows/engine.py    | +280 lines (added comments)
src/processors/rewrite.py  | +260 lines (added comments)
src/publishers/wechat_mp.py | +220 lines (added comments)
```
