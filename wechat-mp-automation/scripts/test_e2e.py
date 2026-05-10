"""
端到端集成测试（Phase 1 MVP）
跳过 LLM 调用，使用 mock 改写结果
"""
import asyncio
import json
import sys
import os

# 设置 PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PYTHONPATH", "src")

from src.storage.database import Database
from src.processors.formatter import ContentFormatter, markdown_to_wechat_html
from src.publishers.wechat_mp import WeChatPublisher


async def test_e2e():
    """端到端测试：collect(mock) -> rewrite(mock) -> format -> publish(mock)"""
    db = Database("./data/e2e_test.db")
    await db.connect()

    print("=" * 60)
    print("Phase 1 E2E Test")
    print("=" * 60)

    # Step 1: 采集（mock 3 篇文章）
    print("\n[1/4] Collecting (mock)...")
    mock_contents = [
        {
            "id": "mock-001",
            "source_id": "tech-rss",
            "source_type": "rss",
            "url": "https://example.com/ai-2026",
            "title": "2026年AI大模型发展趋势",
            "content": "2026年，AI大模型继续快速发展。多模态能力进一步提升，推理能力显著增强。开源模型和闭源模型的差距正在缩小，而模型的小型化趋势也愈发明显。企业级应用场景持续扩展，从客服到研发，AI正在重塑各行各业的工作流程。",
            "summary": "AI大模型2026发展趋势分析",
            "author": "科技观察",
        },
        {
            "id": "mock-002",
            "source_id": "tech-rss",
            "source_type": "rss",
            "url": "https://example.com/robot-2026",
            "title": "具身智能机器人新突破",
            "content": "具身智能领域迎来重大突破。新一代人形机器人已经能够在复杂环境中自主导航和操作。结合大模型的推理能力，机器人开始理解自然语言指令并执行复杂任务。这标志着从数字世界到物理世界的跨越。",
            "summary": "具身智能机器人最新进展",
            "author": "机器之心",
        },
        {
            "id": "mock-003",
            "source_id": "tech-rss",
            "source_type": "rss",
            "url": "https://example.com/chip-2026",
            "title": "国产芯片量产里程碑",
            "content": "国产芯片迎来量产里程碑。最新一代AI推理芯片性能达到国际先进水平，能效比显著提升。这为国内AI产业的发展提供了坚实的硬件基础，也降低了AI应用的算力成本。",
            "summary": "国产芯片量产新进展",
            "author": "半导体行业观察",
        },
    ]

    for c in mock_contents:
        cid = await db.insert_content(c)
        print(f"  Inserted: {c['title'][:30]}")

    collected = await db.get_contents_by_status("collected")
    print(f"  Collected: {len(collected)} articles")

    # Step 2: 改写（mock，不调用 LLM）
    print("\n[2/4] Rewriting (mock)...")
    rewrites = []
    for c in collected:
        # 模拟改写结果
        rewrite_data = {
            "id": f"rewrite-{c['id']}",
            "content_id": c["id"],
            "strategy": "rewrite",
            "style": "professional",
            "title": f"【深度解析】{c['title']}",
            "content": f"""## 前言

{c['content']}

## 深度分析

从技术路线来看，这一进展具有重要意义：

- **技术创新**：核心突破在于架构层面的优化
- **产业影响**：对上下游产业链产生深远影响
- **未来展望**：预计将在未来12个月内看到更多应用落地

## 总结

{c['summary']}。我们正处于技术变革的关键节点，值得持续关注。

---

*本文由AI辅助改写，仅供参考。*
""",
            "word_count": 500,
            "model": "gpt-4o-mock",
            "tokens_used": 1500,
        }
        await db.insert_rewrite(rewrite_data)
        rewrites.append(rewrite_data)
        print(f"  Rewritten: {rewrite_data['title'][:30]}")

    # Step 3: 格式化
    print("\n[3/4] Formatting...")
    formatter = ContentFormatter(db, {"template": "minimal", "image": {"paths": []}})
    formatted_items = []
    for r in rewrites:
        result = await formatter.format_article(r)
        formatted_items.append(result)
        print(f"  Formatted: {r['title'][:30]} (html={len(result['html'])} chars)")

    # 验证 HTML 输出
    html_sample = formatted_items[0]["html"]
    assert "max-width: 677px" in html_sample, "Missing template wrapper"
    assert "<h2" in html_sample, "Missing h2 in formatted output"
    print("  HTML validation: OK")

    # Step 4: 发布（mock，不调用微信API）
    print("\n[4/4] Publishing (mock - skipping actual WeChat API)...")
    for item in formatted_items:
        # 直接插入 published 记录，跳过微信 API
        pub_data = {
            "id": f"pub-{item['id']}",
            "formatted_id": item["id"],
            "account_id": "default",
            "status": "draft",
            "media_id": "mock-media-id",
        }
        await db.insert_published(pub_data)
        print(f"  Saved to draft: {pub_data['id']}")

    # 最终统计
    print("\n" + "=" * 60)
    print("Final Stats:")
    for status in ["collected", "processing", "processed"]:
        rows = await db.fetch_all("SELECT COUNT(*) as cnt FROM contents WHERE status = ?", (status,))
        count = rows[0]["cnt"] if rows else 0
        if count > 0:
            print(f"  contents.{status}: {count}")

    rewrites_count = await db.fetch_all("SELECT COUNT(*) as cnt FROM rewrites")
    formatted_count = await db.fetch_all("SELECT COUNT(*) as cnt FROM formatted")
    published_count = await db.fetch_all("SELECT COUNT(*) as cnt FROM published")

    print(f"  rewrites: {rewrites_count[0]['cnt']}")
    print(f"  formatted: {formatted_count[0]['cnt']}")
    print(f"  published: {published_count[0]['cnt']}")
    print("=" * 60)

    await db.close()

    # 清理
    try:
        os.remove("./data/e2e_test.db")
    except Exception:
        pass

    print("\nE2E test PASSED!")


if __name__ == "__main__":
    asyncio.run(test_e2e())
