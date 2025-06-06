import hashlib
import json
import os
import datetime
import uuid
from typing import List

import astrbot.api.message_components as Comp
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, register, Star
from astrbot.api import logger, AstrBotConfig, llm_tool
from astrbot.api.message_components import ComponentType
from playwright.async_api import async_playwright
from jinja2 import Template
from astrbot.core.utils.session_waiter import (
    session_waiter,
    SessionController,
)

from data.plugins.knbot_enhance.enums import DeepResearchWorkStage

from .prompt import *
from .agent import DeepResearchAgent

@register("knbot_enhance", "Kalinote", "[自用]KNBot 功能增强插件", "1.0.4", "https://github.com/kalinote/knbot_enhance")
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
                    
        self.datas = {
            "deepresearch": {}
        }
        
    
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
                    image_path = await self._text_to_markdown_image(item.text, self.config.get("markdown_image_generate").get("generate_topic_summary"))
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
        image_path = await self._text_to_markdown_image(message, self.config.get("markdown_image_generate").get("generate_topic_summary"), f"[想法] {title}")
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
        
        deepresearch_session_id = str(uuid.uuid4())
        yield event.plain_result(f"深度研究会话ID: {deepresearch_session_id}, 保存该id以用于继续研究")
        deepresearch_agent = DeepResearchAgent(deepresearch_session_id, self.context.get_using_provider(), tools)
        self.datas["deepresearch"][deepresearch_session_id] = deepresearch_agent
        
        # 设置阶段为ASK
        deepresearch_agent.stage = DeepResearchWorkStage.ASK
        
        response_json = await deepresearch_agent.call_llm(research_topic)
        
        while True:
            action = response_json.get("action")
            if action == "ask":
                think = response_json.get("think")
                yield event.plain_result(f"[想法] {think}")
                question = response_json.get("question")
                yield event.plain_result(f"{question}")
                
                @session_waiter(timeout=300, record_history_chains=False)
                async def do_ask(controller: SessionController, event: AstrMessageEvent):
                    next_input_result = event.message_str
                    nonlocal response_json
                    response_json = await deepresearch_agent.call_llm(next_input_result)
                    controller.stop()
                    
                try:
                    await do_ask(event)
                except TimeoutError as _:
                    yield event.plain_result("[ask] 等待用户回答超时，如果需要恢复研究，请使用 session id 继续研究")
                    break
                except Exception as e:
                    logger.error(f"执行ask动作时出错: {e}")
                    yield event.plain_result("[系统] 执行ask动作时出错，请检查错误信息")
                    
            elif action == "set_stage":
                deepresearch_agent.stage = DeepResearchWorkStage.get_stage(response_json.get("stage"))
                yield event.plain_result(f"[系统] 当前阶段已设置为: {deepresearch_agent.stage}")
                response_json = await deepresearch_agent.call_llm(f"当前系统stage已经设置为: {deepresearch_agent.stage}, 请继续下一步操作", system_message=True)
                
            elif action == "answer":
                think = response_json.get("think")
                answer = response_json.get("answer")
                yield event.plain_result(f"[想法] {think}")
                
                format_answer = ""
                format_answer += answer
                if response_json.get("reference"):
                    reference_index = 1
                    for item in response_json.get("reference"):
                        format_answer += f"\n\n# 参考来源：\n{reference_index}. {item.get('title')}\n{item.get('content')}\n{item.get('url')}\n\n"
                        reference_index += 1
                
                yield event.plain_result(f"{format_answer}")
                
                @session_waiter(timeout=300, record_history_chains=False)
                async def do_answer(controller: SessionController, event: AstrMessageEvent):
                    next_input_result = event.message_str
                    nonlocal response_json
                    response_json = await deepresearch_agent.call_llm(next_input_result)
                    controller.stop()
                    
                try:
                    await do_answer(event)
                except TimeoutError as _:
                    yield event.plain_result("[answer] 等待用户回答超时，如果需要恢复研究，请使用 session id 继续研究")
                    break
                except Exception as e:
                    logger.error(f"执行answer动作时出错: {e}")
                    yield event.plain_result("[系统] 执行answer动作时出错，请检查错误信息")
                    
            elif action == "set_research_topic":
                research_topic_detail = response_json.get("research_topic")
                deepresearch_agent.research_topic = research_topic_detail
                yield event.plain_result(f"[系统] 当前研究主题已设置为:\n{research_topic_detail}")
                response_json = await deepresearch_agent.call_llm(f"研究主题已设置，请继续下一步操作", system_message=True)
                    
            elif action == "set_todo_list":
                todo_list = response_json.get("todo_list")
                for step in todo_list:
                    deepresearch_agent.add_todo_list(step)
                yield event.plain_result("[系统] 已设置Todo list:\n" + "\n".join([f"{i+1}. {item}" for i, item in enumerate(todo_list)]))
                response_json = await deepresearch_agent.call_llm(f"Todo List已设置，请继续下一步操作", system_message=True)
                    
            elif action == "set_todo_status":
                todo_id = response_json.get("id")
                todo_status = response_json.get("status")
                todo_reason = response_json.get("reason")
                result = deepresearch_agent.set_todo_status(todo_id, todo_status, todo_reason)
                if result:
                    yield event.plain_result(f"[系统] 已设置Todo项状态: {todo_id} -> {todo_status}")
                    response_json = await deepresearch_agent.call_llm(f"状态已设置，请继续下一步操作", system_message=True)
                else:
                    yield event.plain_result(f"[系统] 尝试设置Todo项状态，但设置失败: 未找到Todo项: {todo_id}")
                    response_json = await deepresearch_agent.call_llm(f"设置状态失败: 未找到Todo项: {todo_id}，请确认id是否正确", system_message=True)
                    
            else:
                logger.error(f"未知动作: {action}")
                yield event.plain_result(f"[系统] 尝试执行未知动作: {action}")
                break
        
        yield event.plain_result("[调试] deepresearch 结束")
            
    async def _generate_topic_summary(self, text: str) -> str:
        """
        生成会话总结
        """
        response = await self.context.get_using_provider().text_chat(
            prompt=text,
            system_prompt=SUMMARY_PROMPT,
        )
        return response.completion_text

    async def _text_to_markdown_image(self, text: str, generate_topic_summary: bool = False, title: str = None) -> str:
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
                topic_summary= title if title else await self._generate_topic_summary(text) if generate_topic_summary else "KNBot Enhance"
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
