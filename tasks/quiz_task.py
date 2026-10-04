from crewai import Task
from config.prompts import TASK_PROMPTS
from models.schemas import Quiz


def build_quiz_task(agent, explanation_task, callback=None) -> Task:
    t = TASK_PROMPTS["quiz"]
    return Task(
        description=t["description"],
        expected_output=t["expected_output"],
        agent=agent,
        context=[explanation_task],   # <- real handoff: Explainer -> Quiz Master
        output_pydantic=Quiz,
        callback=callback,
    )