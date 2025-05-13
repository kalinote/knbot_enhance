
from enum import Enum


class DeepResearchWorkStage(Enum):
    """
    深度研究任务执行阶段
    """
    ASK = "ask"                 # 明确目标
    PLANNING = "planning"       # 计划任务
    EXECUTE = "execute"         # 执行任务
    FINISHED = "finished"       # 任务完成
