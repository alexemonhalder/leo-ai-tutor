from typing import List, Optional
from pydantic import BaseModel, Field


class CoordinatorPlan(BaseModel):
    is_clear: bool = Field(description="True if the request names a learnable topic")
    topic: Optional[str] = Field(default=None, description="Short topic name")
    clarification_question: Optional[str] = Field(
        default=None, description="One question to ask if the request is unclear"
    )
    study_plan: List[str] = Field(default_factory=list)
    focus_hint: Optional[str] = None


class Explanation(BaseModel):
    title: str
    explanation: str
    key_points: List[str]
    example: str


class QuizQuestion(BaseModel):
    id: int
    question: str
    options: List[str] = Field(description="Exactly 4 options like 'A) ...'")
    correct_answer: str = Field(description="A, B, C or D")
    concept: str
    explanation: str


class Quiz(BaseModel):
    topic: str
    questions: List[QuizQuestion]


class QuestionFeedback(BaseModel):
    question_id: int
    is_correct: bool
    feedback: str
    concept: str


class EvaluationResult(BaseModel):
    score: int
    total: int
    per_question: List[QuestionFeedback]
    overall_feedback: str
    weak_concepts: List[str] = Field(default_factory=list)
    needs_reteach: bool = False