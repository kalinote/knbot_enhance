
from enum import Enum


class DeepResearchWorkStage(Enum):
    """
    深度研究任务执行阶段
    """
    ASK = "ask"                 # 明确目标
    PLANNING = "planning"       # 计划任务
    EXECUTE = "execute"         # 执行任务
    FINISHED = "finished"       # 任务完成

    @staticmethod
    def get_stage(stage: str) -> "DeepResearchWorkStage":
        stage = stage.lower()
        if stage == "ask":
            return DeepResearchWorkStage.ASK
        elif stage == "planning":
            return DeepResearchWorkStage.PLANNING
        elif stage == "execute":
            return DeepResearchWorkStage.EXECUTE
        elif stage == "finished":
            return DeepResearchWorkStage.FINISHED
        else:
            raise ValueError(f"无效的研究阶段: {stage}")

