import hashlib
import os

import markdown
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.log import LogManager
from astrbot.core.message.components import ComponentType
from astrbot.core.star import Star
from playwright.async_api import async_playwright
from jinja2 import Environment, BaseLoader

logger = LogManager.GetLogger(log_name="knbot_enhance")

@register("knbot_enhance", "Kalinote", "KNBot 功能增强插件", "v0.1dev")
class KNBotEnhance(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        logger.debug(f"当前配置项: {self.config}")
        
        self.jinja_env = Environment(
            loader=BaseLoader(),
            variable_start_string='[[', 
            variable_end_string=']]',
            autoescape=False
        )
        
        # 载入markdown css样式
        self.markdown_css_content = ""
        self.markdown_html_template = ""
        if self.config.get("markdown_image_generate").get("enable") and self.config.get("markdown_image_generate").get("style") and not self.config.get("markdown_image_generate").get("style") == "不使用额外样式":
            # 构建资源路径
            css_path = os.path.join(os.getcwd(), os.path.join("data", "plugins", "knbot_enhance", "resource"), self.config.get("markdown_image_generate").get("style"))
                
            # 检查文件是否存在
            if not os.path.exists(css_path):
                logger.error(f"样式文件不存在: {css_path}")
            else:
                try:
                    with open(css_path, 'r', encoding='utf-8') as f:
                        self.markdown_css_content = f.read()
                    logger.debug(f"载入样式文件: {css_path}")
                except Exception as e:
                    logger.warning(f"读取样式文件失败: {e}")
                    
            html_path = os.path.join(os.getcwd(), os.path.join("data", "plugins", "knbot_enhance", "resource"), "markdown-template.html")
            if not os.path.exists(html_path):
                logger.error(f"样式文件不存在: {html_path}")
            else:
                try:
                    with open(html_path, 'r', encoding='utf-8') as f:
                        self.markdown_html_template = self.jinja_env.from_string(f.read())
                    logger.debug(f"载入样式文件: {html_path}")
                except Exception as e:
                    logger.warning(f"读取样式文件失败: {e}; 相关功能已禁用")
                    self.config["markdown_image_generate"]["enable"] = False
                    self.config.save()

    @filter.command("test")
    async def test(self, event: AstrMessageEvent):
        logger.debug("开始执行测试命令")
        
        # 测试 markdown 渲染
        ret = await self.text_to_markdown_image("""
# Markdown 渲染示例
这是一个将 Markdown 渲染为图片的 **Python** 脚本。
## 功能列表
*   支持基本的 Markdown 语法
*   可以应用 `CSS` 样式
*   代码高亮（需要 `Pygments` 库，`markdown` 会自动使用）
```python
def greet(name):
    print(f"Hello, {name}!")
greet("World")
```
## 表格示例
| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |
访问 [OpenAI](https://openai.com) 获取更多信息。

# 数学公式渲染测试

## 基础公式
行内公式示例：$E=mc^2$ 是爱因斯坦质能方程

块级公式示例：
$$
\int_{-\infty}^\infty e^{-x^2} dx = \sqrt{\pi}
$$

## 复杂结构测试
矩阵运算：
$$
\begin{bmatrix}
1 & 2 \\
3 & 4 
\end{bmatrix}
+
\begin{bmatrix}
5 & 6 \\
7 & 8 
\end{bmatrix}
=
\begin{bmatrix}
6 & 8 \\
10 & 12 
\end{bmatrix}
$$

多行公式对齐：
$$
\begin{aligned}
f(x) &= \int_0^1 x^2 dx \\
&= \left.\frac{1}{3}x^3\right|_0^1 \\
&= \frac{1}{3}
\end{aligned}
$$

## 特殊符号测试
求和与极限：
$$
\sum_{n=1}^\infty \frac{1}{n^2} = \frac{\pi^2}{6}
$$

微分方程：
$$
\frac{\partial u}{\partial t} = \alpha \nabla^2 u
$$

## 混合排版测试
文字与公式混排：当 $x > 0$ 时，函数 $f(x) = \frac{1}{\sqrt{2\pi\sigma^2}}e^{-\frac{(x-\mu)^2}{2\sigma^2}}$ 表示正态分布的概率密度函数。

多公式环境：
$$
\begin{cases}
2x + 3y = 7 \\
4x - y = 5 
\end{cases}
$$
对应的解为：
$$
x = \frac{7 \cdot (-1) - 5 \cdot 3}{2 \cdot (-1) - 4 \cdot 3} = 2,\quad
y = 3
$$

                                                """)
        logger.debug(f"text_to_markdown_image 返回值: {ret}")
        yield event.image_result(ret)
    
    @filter.on_decorating_result()
    async def markdown_image_generate(self, event: AstrMessageEvent):
        result = event.get_result()
        chain = result.chain
        # logger.debug(chain) # 打印消息链
        
        # logger.debug(self.config.get("markdown_image_generate").get("enable"))
        if self.config.get("markdown_image_generate").get("enable"):
            for i in chain:
                # logger.debug(len(i.text))
                # logger.debug(self.config.get("markdown_image_generate").get("trigger_count"))
                # TODO 这里可以进一步优化，而不只是简单通过字数来判断
                if i.type == ComponentType.Plain.value and len(i.text) > self.config.get("markdown_image_generate").get("trigger_count"):
                    i.text = "!!"
                    
        # logger.debug(chain) # 打印消息链

    # async def text_to_markdown_image(self, text: str) -> str:
    #     """
    #     将 Markdown 文本转换为带有样式的图片。
    #     """
        
    #     try:
    #         image_config = self.config.get("markdown_image_generate", {})
    #         width = image_config.get("width")
    #         if not width:
    #             raise ValueError("Configuration missing: 'markdown_image_generate.width' is required.")

    #         html_body = markdown.markdown(
    #             text,
    #             extensions=['extra', 'codehilite', 'tables', 'fenced_code'],
    #             extension_configs={
    #                 'codehilite': {'css_class': 'highlight'} # 使用 highlight class 配合 CSS
    #             }
    #         )

    #         full_html = f"""
    #         <!DOCTYPE html>
    #         <html>
    #         <head>
    #             <meta charset="UTF-8">
    #             <style>
    #                 body {{
    #                     font-family: sans-serif;
    #                     padding: 0;
    #                     margin: 0;
    #                     box-sizing: border-box;
    #                     background-color: white;
    #                 }}
    #                 {self.markdown_css_content}
    #                 body.markdown-body {{
    #                     width: {width}px;
    #                     box-sizing: border-box;
    #                     margin: 0 auto;
    #                     overflow: hidden;
    #                 }}

    #                 img {{
    #                     max-width: 100%;
    #                     height: auto;
    #                 }}

    #                 pre.highlight {{
    #                     background-color: #f6f8fa;
    #                     padding: 16px;
    #                     overflow: auto;
    #                     border-radius: 6px;
    #                 }}
    #                 code {{
    #                     font-family: monospace;
    #                 }}
    #             </style>
    #         </head>
    #         <body class="markdown-body">
    #             {html_body}
    #         </body>
    #         </html>
    #         """

    #         output_dir = os.path.join(os.getcwd(), "data", "temp", "knbot_enhance", "text_to_markdown_image")
    #         if not os.path.exists(output_dir):
    #             os.makedirs(output_dir)

    #         file_name = f"{hashlib.md5(full_html.encode('utf-8')).hexdigest()}.png"
    #         output_path = os.path.join(output_dir, file_name)

    #         async with async_playwright() as p:
    #             browser = await p.chromium.launch()
    #             page = await browser.new_page()
    #             try:
    #                 await page.set_viewport_size({"width": width, "height": 800}) # Height is arbitrary here
    #                 await page.set_content(full_html, wait_until='load')
    #                 await page.screenshot(
    #                     path=output_path,
    #                     full_page=True,
    #                     type='png'
    #                 )
    #             finally:
    #                 await page.close()
    #                 await browser.close()
    #         return output_path
    #     except Exception as e:
    #         print(f"Error generating markdown image: {e}")
    #         raise

    async def text_to_markdown_image(self, text: str) -> str:
        """
        将 Markdown 文本转换为带有样式的图片（使用模板文件）
        """
        try:
            image_config = self.config.get("markdown_image_generate", {})
            width = image_config.get("width")
            if not width:
                raise ValueError("Configuration missing: 'markdown_image_generate.width' is required.")

            # 生成 HTML 内容
            html_body = markdown.markdown(
                text,
                extensions=['extra', 'codehilite', 'tables', 'fenced_code'],
                extension_configs={
                    'codehilite': {'css_class': 'highlight'}
                }
            )

            # 生成完整 HTML
            full_html = self.markdown_html_template.render(
                markdown_css=self.markdown_css_content,
                content_width=width,
                body_content=html_body
            )

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
                    # 数学公式检测
                    has_math = await page.evaluate("""() => {
                        return document.body.textContent.includes('$$') || 
                            document.body.textContent.includes('$');
                    }""")

                    if has_math:
                        await page.wait_for_function("window.renderPromise", timeout=5000)

                    await page.screenshot(path=output_path, full_page=True, type="png")
                finally:
                    await page.close()
                    await browser.close()
            return output_path
        except Exception as e:
            print(f"Error generating markdown image: {e}")
            raise
