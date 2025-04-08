import hashlib
import json
import os

import astrbot.api.message_components as Comp

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, register, Star
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import ComponentType
from playwright.async_api import async_playwright
from jinja2 import Template

@register("knbot_enhance", "Kalinote", "[自用]KNBot 功能增强插件", "0.0.3", "https://github.com/kalinote/knbot_enhance")
class KNBotEnhance(Star):
    """[自用]KNBot 功能增强插件
    """
    
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
    
    @filter.on_decorating_result(desc="将过长的文本内容转换为Markdown图片")
    async def markdown_image_generate(self, event: AstrMessageEvent):
        result = event.get_result()
        chain = result.chain
        if self.config.get("markdown_image_generate").get("enable"):
            for index, item in enumerate(chain):
                # TODO 这里可以进一步优化，而不只是简单通过字数来判断
                if item.type == ComponentType.Plain.value and len(item.text) > self.config.get("markdown_image_generate").get("trigger_count"):
                    logger.info(f"将文本内容转换为Markdown图片: {item.text[:10]}...")
                    image_path = await self.text_to_markdown_image(item.text)
                    if not image_path:
                        continue
                    
                    logger.info(f"生成Markdown图片: {image_path}")
                    chain[index] = Comp.Image.fromFileSystem(image_path)
                    logger.info(chain)

    async def text_to_markdown_image(self, text: str) -> str:
        """
        将 Markdown 文本转换为带有样式的图片（使用模板文件）
        """
        try:
            image_config = self.config.get("markdown_image_generate", {})
            width = image_config.get("width")
            if not width:
                width = 1600

            # 生成完整 HTML
            json_encoded_text = json.dumps(text)
            full_html = self.markdown_html_template.render(
                json_text="const markdownInput = " + json_encoded_text + ";",       # 传递markdown
            )

            with open("test.html", "w", encoding="utf-8") as f:
                f.write(full_html)

            # 文件保存路径
            output_dir = os.path.join(os.getcwd(), "data", "temp")
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
            return None
