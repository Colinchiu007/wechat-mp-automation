"""测试数据库模块"""
import asyncio
from src.storage.database import Database


async def test():
    db = Database("./data/test_fresh.db")
    await db.connect()

    # 测试插入
    cid = await db.insert_content({
        "id": "test-001",
        "source_id": "test",
        "source_type": "rss",
        "url": "https://example.com/test",
        "title": "测试文章",
        "content": "这是测试内容",
    })
    print(f"Inserted content: {cid}")

    # 查询
    rows = await db.get_contents_by_status("collected")
    print(f"Collected: {len(rows)} items")
    for r in rows:
        print(f"  title: {r['title']}")

    # 测试改写结果
    rid = await db.insert_rewrite({
        "id": "rewrite-001",
        "content_id": "test-001",
        "strategy": "rewrite",
        "style": "professional",
        "title": "改写后的标题",
        "content": "改写后的内容...",
        "word_count": 100,
        "model": "gpt-4o",
    })
    print(f"Inserted rewrite: {rid}")

    # 查看状态变化
    row = await db.fetch_one("SELECT status FROM contents WHERE id = ?", ("test-001",))
    print(f"Content status after rewrite: {row['status']}")

    # 测试格式化
    fid = await db.insert_formatted({
        "id": "fmt-001",
        "rewrite_id": "rewrite-001",
        "format": "wechat_mp",
        "html": "<p>test</p>",
        "cover_image": None,
        "images": "[]",
        "exports": "{}",
    })
    print(f"Inserted formatted: {fid}")

    # 测试发布
    pid = await db.insert_published({
        "id": "pub-001",
        "formatted_id": "fmt-001",
        "account_id": "default",
        "status": "draft",
    })
    print(f"Inserted published: {pid}")

    await db.close()
    print("\nDB test passed!")

    # 清理
    import os
    os.remove("./data/test_fresh.db")


asyncio.run(test())
