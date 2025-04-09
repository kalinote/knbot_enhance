import hashlib
import json
import os
from typing import List

import astrbot.api.message_components as Comp

from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, register, Star
from astrbot.api import logger, AstrBotConfig, llm_tool
from astrbot.api.message_components import ComponentType
from astrbot.api.provider import Personality
from playwright.async_api import async_playwright
from jinja2 import Template

KNBOT_PROMPT = """
你是一个语言模型助手，你需要尽可能地回答或解决用户的问题。

# 回答要求
- 如果涉及到需要计算、推理或比较复杂的问题，需要**逐步思考**，并用户你的想法或思考过程
- 想法和过程需要尽可能详细到**每一个步骤**，不要尝试一步到位直接得到结果
- 在完成所有想法和过程以后再给用户提供最终结果
- 除特殊要求或必要情况外，较短内容或简洁内容的回答尽量不要使用Markdown格式
- 除特殊要求或必要情况外，较长的内容或复杂内容、需要排版的内容等使用Markdown格式
- 流程使用Mermaid图表绘制
- 数学公式使用latex公式表示

# 格式要求
- Mermaid图表语法应该包含在Markdown的Mermaid代码块中，防止渲染失败
- 编写latex公式需要使用latex语法(内联公式使用$...$，块级公式使用$$...$$)，除特殊情况外(需要展示公式原文)不能写在Markdown代码块中，防止渲染失败
- 如果回答无需使用公式，则不要乱用公式
"""

SUMMARY_PROMPT = """
你是一名擅长内容总结的助理，你需要将用户的内容总结为 10 个字以内的标题，标题语言与用户的首要语言一致，不要使用标点符号和其他特殊符号。直接返回总结内容，不要有其他内容。
"""

@register("knbot_enhance", "Kalinote", "[自用]KNBot 功能增强插件", "v1.0.2", "https://github.com/kalinote/knbot_enhance")
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
                logger.error(f"Markdown渲染模板文件不存在: {html_path}")
            else:
                try:
                    with open(html_path, 'r', encoding='utf-8') as f:
                        self.markdown_html_template = Template(f.read())
                    logger.debug(f"载入模板文件: {html_path}")
                except Exception as e:
                    logger.warning(f"读取Markdown渲染文件失败: {e}; 相关功能已禁用")
                    self.config["markdown_image_generate"]["enable"] = False
                    self.config.save()
                    
        # 设置KNBot人格，这一段似乎有点问题，需要进一步确认
        # if self.config.get("knbot_prompt"):
        #     personas = self.context.provider_manager.personas
        #     knbot_persona = None
        #     for persona in personas:
        #         if hasattr(persona, "name"):
        #             if persona.name == "KNBot":
        #                 knbot_persona = persona
        #                 break
        #         elif isinstance(persona, dict):
        #             if persona.get("name") == "KNBot":
        #                 knbot_persona = persona
        #                 break
        #         else:
        #             logger.warning(f"KNBot人格配置格式错误: {persona}; 相关功能已禁用")
        #             self.config["knbot_prompt"]["enable"] = False
        #             self.config.save()
        #             break
        #     if not knbot_persona:
        #         knbot_persona = Personality(
        #             name="KNBot",
        #             prompt=KNBOT_PROMPT,
        #             begin_dialogs=[],
        #             mood_imitation_dialogs=[]
        #         )
        #         personas.append(knbot_persona)

        #     # 设置默认人格为KNBot人格
        #     self.context.provider_manager.selected_default_persona = knbot_persona

    
    @filter.on_decorating_result(desc="将过长的文本内容转换为Markdown图片")
    async def long_message_handler(self, event: AstrMessageEvent):
        result = event.get_result()
        chain = result.chain
        if self.config.get("markdown_image_generate").get("enable"):
            for index, item in enumerate(chain):
                # TODO 这里可以进一步优化，而不只是简单通过字数来判断
                if item.type == ComponentType.Plain.value and len(item.text) > self.config.get("markdown_image_generate").get("trigger_count"):
                    logger.info(f"将文本内容转换为Markdown图片: {item.text[:10]}...")
                    await event.send(MessageChain().message(f"[系统] 正在渲染Markdown，请稍候..."))
                    image_path = await self.text_to_markdown_image(item.text, self.config.get("markdown_image_generate").get("generate_topic_summary"))
                    if not image_path:
                        continue
                    
                    chain[index] = Comp.Image.fromFileSystem(image_path)

    @llm_tool(name="tell_user")
    async def tell_user(self, event: AstrMessageEvent, message: str):
        """你可以使用这个工具告诉用户你的**简短的**想法或思考、处理问题的过程或者其他你需要告诉用户的消息等。
        你应该尽可能地在推理或解决问题的每一步使用该工具，让用户及时知道你的想法和处理过程。

        Args:
            message (string): 消息内容
        """
        yield event.plain_result(f"[想法] {message}")
        yield "已将该消息告知用户，继续你的思考"
        
    @llm_tool(name="tell_user_markdown")
    async def tell_user_markdown(self, event: AstrMessageEvent, message: str, title: str = ""):
        """你可以使用这个工具告诉用户你的**较长的或包含Markdown格式、Mermaid图表或latex公式等的**想法或思考、处理问题的过程或者其他你想告诉用户的消息等。
        你应该尽可能地在推理或解决问题的每一步使用该工具，让用户及时知道你的想法和处理过程。

        Args:
            message (string): 消息内容
            title (string): 消息的标题，可选参数，如果留空则使用系统默认的标题配置
        """
        image_path = await self.text_to_markdown_image(message, self.config.get("markdown_image_generate").get("generate_topic_summary"), f"[想法] {title}")
        if image_path:
            yield event.image_result(image_path)
        else:
            logger.warning(f"AI试图向用户发送一条Markdown消息，但生成Markdown图片失败，消息原文为: \n{message}")
            yield "处理Markdown格式失败，你可以尝试简化成不带格式的文本消息并使用tell_user工具告知用户"
        yield "已将该消息告知用户，继续你的思考"
            
    async def generate_topic_summary(self, text: str) -> str:
        """
        生成会话总结
        """
        response = await self.context.get_using_provider().text_chat(
            prompt=text,
            system_prompt=SUMMARY_PROMPT,
        )
        return response.completion_text

    async def text_to_markdown_image(self, text: str, generate_topic_summary: bool = False, title: str = "KNBot Enhance") -> str:
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
                json_text="const markdownInput = " + json_encoded_text + ";",
                topic_summary= await self.generate_topic_summary(text) if generate_topic_summary else title,
            )

            # 文件保存路径
            output_dir = os.path.join(os.getcwd(), "data", "temp")
            os.makedirs(output_dir, exist_ok=True)
            file_name = f"{hashlib.md5(full_html.encode('utf-8')).hexdigest()}.png"
            output_path = os.path.join(output_dir, file_name)
            
            with open(f"{output_path}.txt", "w", encoding="utf-8") as f:
                f.write(text)
            with open(f"{output_path}.html", "w", encoding="utf-8") as f:
                f.write(full_html)

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
