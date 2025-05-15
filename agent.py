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
        
        # 不同阶段的对话历史
        self._history = {
            DeepResearchWorkStage.ASK: [],
            DeepResearchWorkStage.PLANNING: [],
            DeepResearchWorkStage.EXECUTE: [],
            DeepResearchWorkStage.FINISHED: []
        }
        
        # 外部工具
        self._tools = tools
        
        # 系统指令
        self._system_prompt_template = DEEPRESEARCH_PROMPT + DEEPRESEARCH_ACTIONS + DEEPRESEARCH_TOOLS + DEEPRESEARCH_NOTICE
        
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
    def history(self) -> list:
        return self._history[self.stage]
    
    @history.getter
    def history(self) -> list:
        return self._history[self.stage]
    
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
        self.history.append({
            "role": role,
            "content": content
        })
    
    async def call_llm(self, content, system_message: bool = False) -> dict:
        org_prompt = content if not system_message else f"<system>{content}</system>"
        current_prompt = org_prompt
        
        accumulated_contexts_for_llm = self.history.copy()
        
        response_json = None
        
        while True:
            logger.warning(f"调试 - 发送消息:\n{current_prompt}")
            
            response: LLMResponse = await self._provider.text_chat(
                prompt=current_prompt,
                contexts=accumulated_contexts_for_llm,
                system_prompt=self.system_prompt
            )
            
            raw_response_text: str = response.completion_text
            if raw_response_text.startswith("```json"):
                raw_response_text = raw_response_text.strip("```json").strip("```")
            
            logger.warning(f"调试 - 模型输出: {raw_response_text}")
            
            try:
                response_json = json.loads(raw_response_text)
                self.add_history_org("user", org_prompt)
                self.add_history_org("assistant", response_json)
                break
            except Exception as e:
                logger.error(f"解析结果失败: {e}")
                logger.error(f"原始输出: {raw_response_text}")
                
                accumulated_contexts_for_llm.append({
                    "role": "user",
                    "content": current_prompt
                })
                accumulated_contexts_for_llm.append({
                    "role": "assistant",
                    "content": raw_response_text
                })
                
                current_prompt = f"<system>你上一次的回复 (已包含在上面的对话历史中) 无法被正确解析为JSON。解析时遇到的具体错误是: {e}\n请仔细检查对话历史，并严格按照JSON格式重新生成你的回复。</system>"
        
        return response_json
    