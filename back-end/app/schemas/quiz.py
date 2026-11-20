"""Generated quiz data stays on the server; learner views omit the answer key."""

from typing import Annotated, Literal
from pydantic import computed_field, BaseModel, ConfigDict, Field, StringConstraints, field_validator



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
        return value


def _valid_unicode(value: str) -> str:
    # TEXT uses utf8mb4. Invalid surrogate/control characters must not reach MySQL.
    if any(0xD800 <= ord(char) <= 0xDFFF or (ord(char) < 32 and char not in "\n\r\t") for char in value):
        raise ValueError("Invalid text")
    return value


class GeneratedQuiz(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    questions: tuple[GeneratedQuizQuestion, ...] = Field(min_length=5, max_length=5)


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
