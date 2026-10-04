from crewai import Agent
from config.prompts import AGENT_PROMPTS


def build_quiz_master(llm) -> Agent:
    p = AGENT_PROMPTS["quiz_master"]
    return Agent(
        role=p["role"],
        goal=p["goal"],
        backstory=p["backstory"],
        llm=llm,
        allow_delegation=False,
        max_iter=3,
        max_execution_time=120,
        verbose=False,
    )