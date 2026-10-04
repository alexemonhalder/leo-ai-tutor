"""CrewAI orchestration for Leo.

Pattern: Coordinator-led SEQUENTIAL pipeline.

  Stage 1  Coordinator                      -> plan (or clarification question)
  Stage 2  Explainer --context--> Quiz Master  (one sequential crew)
  --- student answers the quiz (human step) ---
  Stage 3  Evaluator (gets Quiz Master's quiz + answer key)
  Feedback loop: weak concepts go back to Stage 2 (Explainer re-teaches).

Every stage is wrapped in retries; if an agent stalls or fails, the
Coordinator reports it and falls back gracefully.
"""

import json
import os
import re
import time
from typing import Callable, Dict, List, Optional, Tuple

from crewai import Crew, LLM, Process

from agents.coordinator import build_coordinator
from agents.evaluator import build_evaluator
from agents.explainer import build_explainer
from agents.quiz_master import build_quiz_master
from models.schemas import (
    CoordinatorPlan, EvaluationResult, Explanation, QuestionFeedback, Quiz,
)
from tasks.coordinator_task import build_coordinator_task
from tasks.evaluation_task import build_evaluation_task
from tasks.explanation_task import build_explanation_task
from tasks.quiz_task import build_quiz_task

PASS_RATIO = 0.6
MAX_ROUNDS = 3
NUM_QUESTIONS = 4


class TutorError(Exception):
    """Raised when a stage fails after all retries."""


class TutorCrew:
    def __init__(self, on_event: Optional[Callable[[str, str], None]] = None):
        # on_event(agent_name, message) lets the UI show who is doing what
        self.on_event = on_event or (lambda agent, msg: None)
        self.llm = LLM(model=os.getenv("LEO_MODEL", "gpt-4o-mini"), temperature=0.4)
        self.coordinator = build_coordinator(self.llm)
        self.explainer = build_explainer(self.llm)
        self.quiz_master = build_quiz_master(self.llm)
        self.evaluator = build_evaluator(self.llm)

    # ------------------------------------------------------------ helpers
    def _cb(self, agent_name: str, handoff: str):
        def _callback(_output):
            self.on_event(agent_name, f"finished -> handing work to {handoff}")
        return _callback

    def _kickoff(self, build_crew: Callable[[], Crew], inputs: Dict, attempts: int = 2):
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                return build_crew().kickoff(inputs=inputs)
            except Exception as exc:  # stalls, timeouts, bad JSON, API errors
                last_error = exc
                self.on_event(
                    "Coordinator",
                    f"stage failed ({type(exc).__name__}), attempt {attempt}/{attempts}",
                )
                time.sleep(1)
        raise TutorError(
            "The team could not finish this step. Please try again or rephrase. "
            f"(Last error: {last_error})"
        )

    @staticmethod
    def _extract(task_output, model):
        parsed = getattr(task_output, "pydantic", None)
        if parsed is not None:
            return parsed
        raw = (task_output.raw or "").strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        return model.model_validate_json(raw)

    # ------------------------------------------------------------ stage 1
    def plan(self, student_name: str, request: str, memory_summary: str) -> CoordinatorPlan:
        self.on_event("Coordinator", "reading the request and planning")
        inputs = {
            "student_name": student_name,
            "request": request,
            "memory_summary": memory_summary,
        }

        def build():
            task = build_coordinator_task(
                self.coordinator, self._cb("Coordinator", "Explainer")
            )
            return Crew(
                agents=[self.coordinator], tasks=[task],
                process=Process.sequential, verbose=False,
            )

        try:
            out = self._kickoff(build, inputs)
            plan = self._extract(out.tasks_output[0], CoordinatorPlan)
        except Exception:
            # Fallback: Coordinator decides with a simple rule instead of stalling
            text = request.strip()
            if len(text) < 3:
                plan = CoordinatorPlan(
                    is_clear=False,
                    clarification_question="What topic would you like to learn today?",
                )
            else:
                plan = CoordinatorPlan(
                    is_clear=True, topic=text[:80],
                    study_plan=["Teach", "Quiz", "Feedback"],
                )
            self.on_event("Coordinator", "used fallback plan after a failure")

        if plan.is_clear and not (plan.topic or "").strip():
            plan.is_clear = False
            plan.clarification_question = (
                plan.clarification_question or "Which topic should we start with?"
            )
        return plan

    # ------------------------------------------------------------ stage 2
    def teach_and_quiz(
        self, student_name: str, topic: str, level: str, memory_summary: str,
        focus_concepts: Optional[List[str]] = None, student_note: str = "",
        round_number: int = 1,
    ) -> Tuple[Explanation, Quiz]:
        self.on_event("Coordinator", "dispatching Explainer, then Quiz Master")
        inputs = {
            "student_name": student_name,
            "topic": topic,
            "level": level,
            "memory_summary": memory_summary,
            "focus_concepts": ", ".join(focus_concepts) if focus_concepts else "none",
            "student_note": student_note.strip() or "none",
            "round_number": round_number,
            "num_questions": NUM_QUESTIONS,
        }

        def build():
            t1 = build_explanation_task(
                self.explainer, self._cb("Explainer", "Quiz Master")
            )
            t2 = build_quiz_task(
                self.quiz_master, t1, self._cb("Quiz Master", "the student")
            )
            return Crew(
                agents=[self.explainer, self.quiz_master], tasks=[t1, t2],
                process=Process.sequential, verbose=False,
            )

        out = self._kickoff(build, inputs)
        explanation = self._extract(out.tasks_output[0], Explanation)
        quiz = self._extract(out.tasks_output[1], Quiz)
        if not quiz.questions:
            raise TutorError("The Quiz Master returned no questions. Please retry.")
        return explanation, quiz

    # ------------------------------------------------------------ stage 3
    def evaluate(
        self, student_name: str, quiz: Quiz, answers: Dict[int, str]
    ) -> EvaluationResult:
        self.on_event("Coordinator", "sending quiz + answers to Evaluator")
        inputs = {
            "quiz_json": quiz.model_dump_json(),
            "answers_json": json.dumps(answers),
        }

        def build():
            task = build_evaluation_task(
                self.evaluator, self._cb("Evaluator", "Coordinator")
            )
            return Crew(
                agents=[self.evaluator], tasks=[task],
                process=Process.sequential, verbose=False,
            )

        llm_result: Optional[EvaluationResult] = None
        try:
            out = self._kickoff(build, inputs)
            llm_result = self._extract(out.tasks_output[0], EvaluationResult)
        except Exception:
            self.on_event(
                "Coordinator", "Evaluator unavailable, grading from the answer key"
            )

        return self._grade(quiz, answers, llm_result)

    @staticmethod
    def _grade(
        quiz: Quiz, answers: Dict[int, str], llm_result: Optional[EvaluationResult]
    ) -> EvaluationResult:
        """Score is computed in code (reliable); the Evaluator supplies the
        explanations. If the Evaluator failed, answer-key explanations are used."""
        by_id = {f.question_id: f for f in (llm_result.per_question if llm_result else [])}
        per_question, weak = [], []
        score = 0
        for q in quiz.questions:
            chosen = (answers.get(q.id) or "").strip().upper()[:1]
            correct = chosen == q.correct_answer.strip().upper()[:1]
            score += int(correct)
            if not correct:
                weak.append(q.concept)
            llm_fb = by_id.get(q.id)
            text = llm_fb.feedback if llm_fb else (
                f"The correct answer is {q.correct_answer}. {q.explanation}"
            )
            per_question.append(
                QuestionFeedback(
                    question_id=q.id, is_correct=correct,
                    feedback=text, concept=q.concept,
                )
            )
        total = len(quiz.questions)
        overall = (
            llm_result.overall_feedback if llm_result
            else "Graded from the answer key because the Evaluator was unavailable."
        )
        return EvaluationResult(
            score=score,
            total=total,
            per_question=per_question,
            overall_feedback=overall,
            weak_concepts=list(dict.fromkeys(weak)),
            needs_reteach=(score / total) < PASS_RATIO,
        )