"""测试格式化模块"""
from src.processors.formatter import markdown_to_wechat_html

# 测试 Markdown 转 HTML
md = """
# 测试标题

这是一段普通文字，包含**粗体**和*斜体*。

## 二级标题

- 列表项1
- 列表项2
- 列表项3

> 引用内容

### 三级标题

一些 `行内代码` 和：

```python
def hello():
    print("Hello, World!")
```

---

最后一段文字。
"""

html = markdown_to_wechat_html(md)
print("HTML output length:", len(html))
print("\nFirst 500 chars:")
print(html[:500])

# 检查关键元素
assert "<h2" in html, "Missing h2"
assert "<h3" in html, "Missing h3"
assert "<strong" in html, "Missing bold"
assert "<blockquote" in html, "Missing blockquote"
assert "<pre" in html, "Missing code block"
assert "<code" in html, "Missing inline code"
assert "max-width: 677px" in html, "Missing template wrapper"

print("\nFormatter test passed!")
