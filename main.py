import hashlib
import json
import os
import datetime
from typing import List

import astrbot.api.message_components as Comp

from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, register, Star
from astrbot.api import logger, AstrBotConfig, llm_tool
from astrbot.api.message_components import ComponentType
from astrbot.api.provider import Personality
from playwright.async_api import async_playwright
from jinja2 import Template

from .prompt import *

@register("knbot_enhance", "Kalinote", "[自用]KNBot 功能增强插件", "v1.0.3", "https://github.com/kalinote/knbot_enhance")
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
        """通过这个工具向用户展示你的思考过程中的步骤性思考。
    
        使用该工具的场景：
        1. 当你在解决问题过程中形成了一个清晰的思考步骤
        2. 当你需要展示推理过程中的中间结论
        3. 适合简短、不包含复杂格式的想法(350字以内)
        
        使用指南：
        - 每完成一个思考步骤就调用一次，不要等到完成所有思考后才一次性展示
        - 保持每次消息简洁明了，聚焦于单一思考点
        - 使用自然语言表达，就像你在"思考出声"一样
        - 避免在此工具中使用Markdown、表格、图表或公式
        - 仅在展示思考步骤时使用该工具，如果需要与用户进行互动，则直接进行对话或提问，不要使用此工具
        
        Args:
            message (string): 你当前的思考步骤或中间结论（简短文本）
        """
        yield event.plain_result(f"[想法] {message}")
        yield "已向用户展示这一步思考，请继续下一步思考"
        
    @llm_tool(name="tell_user_markdown")
    async def tell_user_markdown(self, event: AstrMessageEvent, message: str, title: str = ""):
        """通过这个工具向用户展示包含丰富格式的思考过程或阶段性结论。
    
        使用该工具的场景：
        1. 当你需要展示包含Markdown格式的复杂内容
        2. 当你需要展示Mermaid流程图、表格或结构化数据
        3. 当你需要展示数学公式(LaTeX格式)
        4. 当内容较长且需要良好排版
        
        使用指南：
        - 每完成一个需要复杂表达的思考步骤就调用一次
        - 确保Markdown格式正确，特别是代码块、表格和列表
        - Mermaid图表必须包含在```mermaid代码块中
        - 数学公式使用LaTeX格式: 内联公式用$...$，块级公式用$$...$$
        - 合理使用标题、列表和强调来提高可读性
        - 仅在展示思考步骤时使用该工具，如果需要与用户进行互动，则直接进行对话或提问，不要使用此工具
        
        Args:
            message (string): 包含格式化内容的思考步骤或结论(Markdown格式)
            title (string): 可选的标题，简短描述这部分内容的主题（如"问题分析"、"计算过程"等）
        """
        image_path = await self.text_to_markdown_image(message, self.config.get("markdown_image_generate").get("generate_topic_summary"), f"[想法] {title}")
        if image_path:
            yield event.image_result(image_path)
        else:
            logger.warning(f"AI试图向用户发送一条Markdown消息，但生成Markdown图片失败，消息原文为: \n{message}")
            yield "处理Markdown格式失败，请简化内容并使用tell_user工具重试"
        yield "已向用户展示格式化内容，请继续下一步思考"
            
    @filter.command("deepresearch")
    async def deepresearch(self, event: AstrMessageEvent, research_topic: str):
        """
        进行深度研究
        """
        func_tools_mgr = self.context.get_llm_tool_manager()
        tools = func_tools_mgr.get_func_desc_openai_style()
        
        system_prompt = ""
        system_prompt += Template(DEEPRESEARCH_PROMPT).render(current_datetime=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        system_prompt += Template(DEEPRESEARCH_TOOLS).render(tools="\n".join([json.dumps(tool.get("function"), ensure_ascii=False, indent=4) for tool in tools]))
        system_prompt += Template(DEEPRESEARCH_ACTIONS).render(actions="")
        yield event.plain_result(system_prompt)
            
    async def generate_topic_summary(self, text: str) -> str:
        """
        生成会话总结
        """
        response = await self.context.get_using_provider().text_chat(
            prompt=text,
            system_prompt=SUMMARY_PROMPT,
        )
        return response.completion_text

    async def text_to_markdown_image(self, text: str, generate_topic_summary: bool = False, title: str = None) -> str:
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
                topic_summary= title if title else await self.generate_topic_summary(text) if generate_topic_summary else "KNBot Enhance"
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
