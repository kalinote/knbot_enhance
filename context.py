
import datetime
import json
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.provider import Provider
from astrbot.api import logger
from .prompt import *
from .enums import DeepResearchWorkStage

from jinja2 import Template

class DeepResearchContext:
    """
    深度研究上下文
    """    
    def __init__(self, session_id: str, provider: Provider, tools: list):        
        # 深度研究会话ID
        self._session_id: str = session_id
        
        # 使用的Provider
        self._provider = provider
        
        # 深度研究阶段
        self._stage: DeepResearchWorkStage = None
        
        # 完整对话历史
        self._history_org = []
        
        # 对话历史
        self._history = []
        
        # 外部工具
        self._tools = tools
        
        # 系统指令
        self._system_prompt_template = DEEPRESEARCH_PROMPT + DEEPRESEARCH_TOOLS + DEEPRESEARCH_ACTIONS
        
    @property
    def provider(self):
        return self._provider

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def stage(self) -> DeepResearchWorkStage:
        return self._stage
    
    @stage.setter
    def stage(self, stage: DeepResearchWorkStage):
        self._stage = stage
    
    @property
    def system_prompt(self) -> str:
        return Template(self._system_prompt_template).render(
            current_datetime=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            stage=self.stage,
            tools="\n".join([json.dumps(tool.get("function"), ensure_ascii=False, indent=4) for tool in self._tools]),
            actions=""
        )
    
    def add_history_org(self, role, content):
        if not content:
            return False
        
        self._history_org.append({
            "role": role,
            "content": content
        })
        
        return True
        
    def get_history_org(self):
        return self._history_org
    
    def add_history(self, role, content):
        self._history.append({
            "role": role,
            "content": content
        })
    
    async def call_llm(self, content) -> dict:
        response: LLMResponse = await self._provider.text_chat(
            prompt=content,
            contexts=self._history,
            system_prompt=self.system_prompt
        )
        
        response_json: str = response.completion_text
        if response_json.startswith("```json"):
            response_json = response_json.replace("```json", "").replace("```", "")
        
        logger.warning(f"调试输出: {response_json}")
        
        try:
            response_json = json.loads(response_json)
        except Exception as e:
            logger.error(response_json)
            logger.error(f"解析深度研究结果失败: {e}")
            return
        
        action = response_json.get("action")
        assistant_content = None
        if action == "ask":
            assistant_content = response_json.get("question")
        elif action == "set_stage":
            assistant_content = response_json.get("stage")
        else:
            logger.error(f"未知动作: {action}")
        
        # TODO 优化这里的结构
        self.add_history_org("user", content)
        self.add_history_org("assistant", response_json)
        self.add_history("user", content)
        self.add_history("assistant", assistant_content)
        
        return response_json
    