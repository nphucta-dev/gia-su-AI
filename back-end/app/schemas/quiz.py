"""Generated quiz data stays on the server; learner views omit the answer key."""

from typing import Annotated, Literal
import unicodedata
from pydantic import computed_field, BaseModel, ConfigDict, Field, StringConstraints, field_validator
from app.utils.text import has_visible_text



QuizDifficulty = Literal["easy", "medium", "hard"]
AnswerLetter = Literal["A", "B", "C", "D"]
QuizText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=8000)]
OptionText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2000)]


class QuizOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    A: OptionText
    B: OptionText
    C: OptionText
    D: OptionText


class GeneratedQuizQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    question_text: QuizText
    options: QuizOptions
    correct_answer: AnswerLetter = Field(repr=False)
    explanation: QuizText = Field(repr=False)

    @field_validator("question_text", "explanation")
    @classmethod
    def valid_text(cls, value: str) -> str:
        return _valid_unicode(value)

    @field_validator("options")
    @classmethod
    def valid_options(cls, value: QuizOptions) -> QuizOptions:
        for option in value.model_dump().values():
            _valid_unicode(option)
        if len({_normalized_text(option) for option in value.model_dump().values()}) != 4:
            raise ValueError("Duplicate quiz options")
        return value


def _valid_unicode(value: str) -> str:
    # TEXT uses utf8mb4. Invalid surrogate/control characters must not reach MySQL.
    if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\r\t" for char in value):
        raise ValueError("Invalid text")
    if not has_visible_text(value):
        raise ValueError("Empty quiz text")
    return value


def _normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class GeneratedQuiz(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    questions: tuple[GeneratedQuizQuestion, ...] = Field(min_length=5, max_length=5)

    @field_validator("questions")
    @classmethod
    def unique_questions(cls, value: tuple[GeneratedQuizQuestion, ...]) -> tuple[GeneratedQuizQuestion, ...]:
        if len({_normalized_text(question.question_text) for question in value}) != len(value):
            raise ValueError("Duplicate quiz questions")
        return value


class GenerateQuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic_id: int = Field(alias="topicId", strict=True, ge=1, le=2**31 - 1)
    difficulty: QuizDifficulty


class QuizQuestionItem(BaseModel):
    id: int
    position: int
    question_text: str = Field(serialization_alias="questionText")
    options: QuizOptions


class QuizItem(BaseModel):
    id: int
    topic_id: int = Field(serialization_alias="topicId")
    difficulty: QuizDifficulty
    status: Literal["in_progress", "completed"]
    created_at: str = Field(serialization_alias="createdAt")
    questions: list[QuizQuestionItem]


class QuizResponse(BaseModel):
    quiz: QuizItem


class QuizSummaryItem(BaseModel):
    id: int
    topic_id: int = Field(serialization_alias="topicId")
    topic_name: str = Field(serialization_alias="topicName")
    subject_name: str = Field(serialization_alias="subjectName")
    difficulty: QuizDifficulty
    status: Literal["in_progress", "completed"]
    created_at: str = Field(serialization_alias="createdAt")
    score: float | None = None
    completed_at: str | None = Field(default=None, serialization_alias="completedAt")


class QuizListResponse(BaseModel):
    quizzes: list[QuizSummaryItem]
    limit: int
    offset: int
    has_more: bool = Field(serialization_alias="hasMore")


class SubmittedAnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    question_id: int = Field(alias="questionId", strict=True, ge=1, le=2**31 - 1)
    user_answer: AnswerLetter = Field(alias="userAnswer")


class SubmitQuizAnswersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list[SubmittedAnswerInput] = Field(min_length=5, max_length=5)


class SavedQuizAnswerItem(BaseModel):
    question_id: int = Field(serialization_alias="questionId")
    user_answer: AnswerLetter = Field(serialization_alias="userAnswer")


class QuizSubmissionItem(BaseModel):
    quiz_id: int = Field(serialization_alias="quizId")
    status: Literal["accepted"] = "accepted"
    saved_count: int = Field(serialization_alias="savedCount")
    answers: list[SavedQuizAnswerItem]
    quiz_status: Literal["completed"] = Field(serialization_alias="quizStatus")
    score: float
    correct_count: int = Field(serialization_alias="correctCount")
    total_count: int = Field(serialization_alias="totalCount")
    completed_at: str = Field(serialization_alias="completedAt")


class QuizSubmissionResponse(BaseModel):
    submission: QuizSubmissionItem


class QuizResultQuestion(QuizQuestionItem):
    user_answer: AnswerLetter = Field(serialization_alias="userAnswer")
    correct_answer: AnswerLetter = Field(serialization_alias="correctAnswer")
    is_correct: bool = Field(serialization_alias="isCorrect")
    explanation: str


class QuizResultItem(BaseModel):
    difficulty: QuizDifficulty | None = None

    @computed_field
    @property
    def id(self) -> int:
        return self.quiz_id

    quiz_id: int = Field(serialization_alias="quizId")
    topic_id: int = Field(serialization_alias="topicId")
    status: Literal["completed"] = "completed"
    score: float
    correct_count: int = Field(serialization_alias="correctCount")
    total_count: int = Field(serialization_alias="totalCount")
    completed_at: str = Field(serialization_alias="completedAt")
    questions: list[QuizResultQuestion]


class QuizResultResponse(BaseModel):
    result: QuizResultItem

class QuizResultQuestionItem(BaseModel):
    id: int
    position: int
    question_text: str = Field(serialization_alias="questionText")
    options: QuizOptions
    user_answer: AnswerLetter = Field(serialization_alias="userAnswer")
    correct_answer: AnswerLetter = Field(serialization_alias="correctAnswer")
    is_correct: bool = Field(serialization_alias="isCorrect")
    explanation: str
