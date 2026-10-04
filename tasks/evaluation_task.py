from crewai import Task
from config.prompts import TASK_PROMPTS
from models.schemas import EvaluationResult


def build_evaluation_task(agent, callback=None) -> Task:
    t = TASK_PROMPTS["evaluation"]
    return Task(
        description=t["description"],   # quiz JSON + answers arrive as inputs
        expected_output=t["expected_output"],
        agent=agent,
        output_pydantic=EvaluationResult,
        callback=callback,
    )