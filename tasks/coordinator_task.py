from crewai import Task
from config.prompts import TASK_PROMPTS
from models.schemas import CoordinatorPlan


def build_coordinator_task(agent, callback=None) -> Task:
    t = TASK_PROMPTS["coordinator"]
    return Task(
        description=t["description"],
        expected_output=t["expected_output"],
        agent=agent,
        output_pydantic=CoordinatorPlan,
        callback=callback,
    )