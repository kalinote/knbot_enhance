
import datetime
import json
import hashlib
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.provider import Provider
from astrbot.api import logger
from .prompt import *
from .enums import DeepResearchWorkStage

from jinja2 import Template

class DeepResearchAgent:
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
        self._system_prompt_template = DEEPRESEARCH_PROMPT + DEEPRESEARCH_ACTIONS + DEEPRESEARCH_TOOLS
        
        # 当前任务的研究主题
        self._research_topic = None
        
        # 当前任务的TODO list
        self._todo_list = []
        
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
    def research_topic(self) -> str:
        return self._research_topic
    
    @research_topic.setter
    def research_topic(self, research_topic: str):
        self._research_topic = research_topic
    
    @property
    def todo_list(self) -> list:
        return self._todo_list
    
    @property
    def system_prompt(self) -> str:
        # TODO 按阶段添加可用actions
        prompt = Template(self._system_prompt_template).render(
            current_datetime=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            stage=self.stage,
            tools="\n".join([json.dumps(tool.get("function"), ensure_ascii=False, indent=4) for tool in self._tools]),
            actions=""
        )
        
        return prompt
    
    def add_todo_list(self, step: str, status: str = "队列中", reason: str = ""):
        self._todo_list.append({
            "id": hashlib.md5(step.encode("utf-8")).hexdigest()[:6],
            "step": step,
            "status": status,
            "reason": reason
        })
        
    def set_todo_status(self, todo_id: str, status: str, reason: str):
        for todo in self._todo_list:
            if todo.get("id") == todo_id:
                todo["status"] = status
                todo["reason"] = reason
                break
        else:
            logger.error(f"未找到Todo项: {todo_id}")
            return False
        
        return True
    
    def add_history_org(self, role, content):
        if not content:
            return False
        
        self._history_org.append({
            "role": role,
            "content": content
        })
        
        if role == "assistant":
            action = content.get("action")
            assistant_content = None
            
            if action == "ask":
                assistant_content = content.get("question")
                
            elif action == "set_stage":
                assistant_content = content.get("stage")
                
            elif action == "answer":
                assistant_content = content.get("answer")
                
            elif action == "set_research_topic":
                assistant_content = content.get("research_topic")
                
            elif action == "set_todo_list":
                assistant_content = "\n".join(content.get("todo_list"))
                
            else:
                logger.error(f"未知动作: {action}")
                
            self.add_history(role, assistant_content)
        else:
            self.add_history(role, content)
        
        return True
        
    def get_history_org(self):
        return self._history_org
    
    def add_history(self, role, content):
        self._history.append({
            "role": role,
            "content": content
        })
    
    async def call_llm(self, content, system_message: bool = False) -> dict:
        prompt = content if not system_message else f"<system>{content}</system>"
        logger.warning(f"调试 - 发送消息：\n{prompt}")
        
        response: LLMResponse = await self._provider.text_chat(
            prompt=prompt,
            contexts=self._history,
            system_prompt=self.system_prompt
        )
        
        response_json: str = response.completion_text
        if response_json.startswith("```json"):
            response_json = response_json.strip("```json").strip("```")
        
        logger.warning(f"调试 - 模型输出: {response_json}")
        
        try:
            response_json = json.loads(response_json)
        except Exception as e:
            logger.error(response_json)
            logger.error(f"解析深度研究结果失败: {e}")
            return
        
        self.add_history_org("user", content)
        self.add_history_org("assistant", response_json)
        
        return response_json
    