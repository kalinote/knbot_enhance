import hashlib
import json
import os

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.log import LogManager
from astrbot.core.message.components import ComponentType
from astrbot.core.star import Star
from playwright.async_api import async_playwright
from jinja2 import Template

logger = LogManager.GetLogger(log_name="knbot_enhance")

@register("knbot_enhance", "Kalinote", "KNBot 功能增强插件", "v0.1dev")
class KNBotEnhance(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        logger.debug(f"当前配置项: {self.config}")
        
        # 载入markdown css样式
        self.markdown_css_content = ""
        self.markdown_html_template = ""
        if self.config.get("markdown_image_generate").get("enable"):
            html_path = os.path.join(os.getcwd(), os.path.join("data", "plugins", "knbot_enhance", "resource"), "markdown-template.html")
            if not os.path.exists(html_path):
                logger.error(f"样式文件不存在: {html_path}")
            else:
                try:
                    with open(html_path, 'r', encoding='utf-8') as f:
                        self.markdown_html_template = Template(f.read())
                    logger.debug(f"载入模板文件: {html_path}")
                except Exception as e:
                    logger.warning(f"读取样式文件失败: {e}; 相关功能已禁用")
                    self.config["markdown_image_generate"]["enable"] = False
                    self.config.save()

    @filter.command("test")
    async def test(self, event: AstrMessageEvent):
        logger.debug("开始执行测试命令")
        
        # 测试 markdown 渲染
        ret = await self.text_to_markdown_image(r'''# Markdown 与 LaTeX 渲染综合测试

这是一个用于测试 Markdown 和 LaTeX 公式渲染能力的示例文档。

## 基本 Markdown 功能

*   **加粗文本** 和 *斜体文本*
*   `行内代码` 示例
*   [一个链接到 KaTeX](https://katex.org/)
*   无序列表项 1
    *   嵌套项 A
    *   嵌套项 B
*   有序列表项 1
    1.  嵌套项 C
    2.  嵌套项 D

> 这是一个块引用。
> 它可以包含多行。

代码块示例 (Python):
```python
import math

def calculate_circle_area(radius):
  """Calculates the area of a circle."""
  if radius < 0:
    raise ValueError("Radius cannot be negative")
  return math.pi * radius**2

# Example usage
r = 5
area = calculate_circle_area(r)
print(f"The area of a circle with radius {r} is {area}")
```

# 表格示例

| 列1 | 列2 | 列3 |
| --- | --- | --- |
| 行1 | 行1 | 行1 |
| 行2 | 行2 | 行2 |
| 行3 | 行3 | 行3 |


---

## LaTeX 公式渲染测试

### 行内公式 (Inline Formulas)

爱因斯坦的质能方程是 $E=mc^2$。
勾股定理可以表示为 $a^2 + b^2 = c^2$。
欧拉公式是 $e^{i\pi} + 1 = 0$。
一个简单的分数：$\frac{a}{b}$，以及更复杂的分数：$\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$。
包含希腊字母：$\alpha, \beta, \gamma, \Delta, \Omega$。
测试上下标：$X_{i}^{n+1}$ 和 $f(x) = x^2$。

### 块级公式 (Block Formulas)

高斯积分：
$$
\int_{-\infty}^{\infty} e^{-ax^2} dx = \sqrt{\frac{\pi}{a}}
$$

麦克斯韦方程组中的一个（高斯定律）：
$$
\nabla \cdot \mathbf{E} = \frac{\rho}{\varepsilon_0}
$$

黎曼 Zeta 函数在 $s=2$ 处的值：
$$
\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}
$$

使用 `aligned` 环境对齐多行公式：
$$
\begin{aligned}
f(x) &= (x+1)^2 \\\\
&= x^2 + 2x + 1 \\\\
\int f(x) dx &= \int (x^2 + 2x + 1) dx \\\\
&= \frac{1}{3}x^3 + x^2 + x + C
\end{aligned}
$$

矩阵表示：
$$
M = \begin{bmatrix}
1 & 2 & 3 \\\\
4 & 5 & 6 \\\\
7 & 8 & 9
\end{bmatrix}
\quad
\mathbf{v} = \begin{pmatrix} x \\\\ y \\\\ z \end{pmatrix}
$$

极限表示：
$$
\lim_{x \to 0} \frac{\sin x}{x} = 1
$$

## 混合内容

在段落中混合使用公式：函数 $g(x) = \sin(x^2)$ 的导数是 $g'(x) = \cos(x^2) \cdot 2x$。当 $x \to \infty$ 时，$\frac{1}{x} \to 0$。

列表项也可以包含公式：
1.  第一个关键点涉及 $\lambda$ 参数。
2.  第二个关键点是关于积分 $\int_0^1 x^n dx = \frac{1}{n+1}$ (对于 $n \neq -1$)。

---

测试结束。''')
        logger.debug(f"text_to_markdown_image 返回值: {ret}")
        yield event.image_result(ret)
    
    @filter.on_decorating_result()
    async def markdown_image_generate(self, event: AstrMessageEvent):
        result = event.get_result()
        chain = result.chain
        if self.config.get("markdown_image_generate").get("enable"):
            for i in chain:
                # TODO 这里可以进一步优化，而不只是简单通过字数来判断
                if i.type == ComponentType.Plain.value and len(i.text) > self.config.get("markdown_image_generate").get("trigger_count"):
                    i.text = "!!"

    async def text_to_markdown_image(self, text: str) -> str:
        """
        将 Markdown 文本转换为带有样式的图片（使用模板文件）
        """
        try:
            image_config = self.config.get("markdown_image_generate", {})
            width = image_config.get("width")
            if not width:
                width = 800

            # 生成完整 HTML
            json_encoded_text = json.dumps(text)
            full_html = self.markdown_html_template.render(
                json_text="const markdownInput = " + json_encoded_text + ";",       # 传递markdown
            )

            with open("test.html", "w", encoding="utf-8") as f:
                f.write(full_html)

            # 文件保存路径
            output_dir = os.path.join(os.getcwd(), "data", "temp", "knbot_enhance", "text_to_markdown_image")
            os.makedirs(output_dir, exist_ok=True)
            file_name = f"{hashlib.md5(full_html.encode('utf-8')).hexdigest()}.png"
            output_path = os.path.join(output_dir, file_name)

            # 使用 Playwright 截图
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                try:
                    await page.set_viewport_size({"width": width, "height": 800})
                    await page.set_content(full_html, wait_until="networkidle")

                    # 截图
                    await page.screenshot(path=output_path, full_page=True, type="png")
                finally:
                    await page.close()
                    await browser.close()
            return output_path
        except Exception as e:
            logger.error(f"生成Markdown图片时出错: {e}")
            raise
