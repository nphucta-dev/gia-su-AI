import { api, ApiError } from './api.js';

const answerKeys = new Set(['A', 'B', 'C', 'D']);

function validId(value) {
  return Number.isSafeInteger(value) && value > 0;
}

export function buildQuizSubmission(quizId, questions, answers) {
  if (!validId(quizId) || !Array.isArray(questions) || !(answers instanceof Map)) {
    throw new ApiError('Dữ liệu bài luyện tập chưa hợp lệ. Vui lòng mở lại bài.', 422, 'INVALID_QUIZ_SUBMISSION');
  }
  if (questions.length !== 5 || answers.size !== questions.length) {
    throw new ApiError('Vui lòng trả lời đầy đủ 5 câu trước khi nộp.', 422, 'INCOMPLETE_QUIZ');
  }
  const seen = new Set();
  const payload = [];
  for (const question of questions) {
    if (!validId(question?.id) || seen.has(question.id)) {
      throw new ApiError('Mã câu hỏi chưa hợp lệ. Vui lòng mở lại bài.', 422, 'INVALID_QUESTION_ID');
    }
    seen.add(question.id);
    const userAnswer = answers.get(question.id);
    if (!answerKeys.has(userAnswer)) {
      throw new ApiError('Vui lòng trả lời đầy đủ các câu hỏi trước khi nộp.', 422, 'INCOMPLETE_QUIZ');
    }
    payload.push({ questionId: question.id, userAnswer });
  }
  return { answers: payload };
}

// Only learner selections are sent; grading and explanations come from the backend.
export async function submitQuizAnswers(quizId, questions, answers, { signal } = {}) {
  const payload = buildQuizSubmission(quizId, questions, answers);
  const result = await api(`/quizzes/${quizId}/submit`, { method: 'POST', body: payload, signal });
  const submission = result?.submission;
  if (submission?.quizId !== quizId || submission?.status !== 'accepted') {
    throw new ApiError('Phản hồi nộp bài chưa hợp lệ. Đáp án của bạn vẫn được giữ để thử lại.', 0, 'INVALID_RESPONSE');
  }
  return submission;
}
