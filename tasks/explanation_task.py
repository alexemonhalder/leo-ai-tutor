from crewai import Task
from config.prompts import TASK_PROMPTS
from models.schemas import Explanation


def build_explanation_task(agent, callback=None) -> Task:
    t = TASK_PROMPTS["explanation"]
    return Task(
        description=t["description"],
        expected_output=t["expected_output"],
        agent=agent,
        output_pydantic=Explanation,
        callback=callback,
    )