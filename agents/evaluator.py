from crewai import Agent
from config.prompts import AGENT_PROMPTS


def build_evaluator(llm) -> Agent:
    p = AGENT_PROMPTS["evaluator"]
    return Agent(
        role=p["role"],
        goal=p["goal"],
        backstory=p["backstory"],
        llm=llm,
        allow_delegation=False,
        max_iter=3,
        max_execution_time=90,
        verbose=False,
    )