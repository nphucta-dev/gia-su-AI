import { getAccessToken, getSession, onSessionCleared, subscribeSession } from './session.js';

const prefix = 'gia-su-ai.quiz-draft.';
const answerKeys = new Set(['A', 'B', 'C', 'D']);

function key(userId, quizId) {
 return `${prefix}${String(userId)}.${String(quizId)}`;
}

function ownsCurrentTab(userId) {
 const session = getSession();
 return session.status === 'authenticated' && session.reason !== 'preview'
  && userId != null && String(session.user?.id) === String(userId);
}

// A draft only contains choices plus a fingerprint of the server's question set.
// Scores, correct answers, ownership and completion always come from the API.
function fingerprint(quiz) {
 return JSON.stringify(quiz.questions.map(question => [question.id, question.position, question.questionText,
  ...['A', 'B', 'C', 'D'].map(option => question.options[option])]));
}

export function clearQuizDraft(userId, quizId) {
 try { sessionStorage.removeItem(key(userId, quizId)); } catch { /* Storage may be unavailable. */ }
}

export function loadQuizDraft(userId, quiz) {
 const empty = () => { clearQuizDraft(userId, quiz.id); return new Map(); };
 if (!ownsCurrentTab(userId) || quiz.status !== 'in_progress') return empty();
 try {
  const raw = sessionStorage.getItem(key(userId, quiz.id));
  if (!raw) return new Map();
  const draft = JSON.parse(raw);
  if (draft?.version !== 1 || draft.fingerprint !== fingerprint(quiz) || !Array.isArray(draft.answers)
   || draft.answers.length > quiz.questions.length) return empty();
  const questionIds = new Set(quiz.questions.map(question => question.id));
  const answers = new Map();
  for (const entry of draft.answers) {
   if (!Array.isArray(entry) || entry.length !== 2 || !questionIds.has(entry[0]) || !answerKeys.has(entry[1]) || answers.has(entry[0])) return empty();
   answers.set(entry[0], entry[1]);
  }
  return answers;
 } catch { return empty(); }
}

export function saveQuizDraft(userId, quiz, answers) {
 if (!ownsCurrentTab(userId) || quiz.status !== 'in_progress') return;
 try {
  sessionStorage.setItem(key(userId, quiz.id), JSON.stringify({ version: 1, fingerprint: fingerprint(quiz), answers: [...answers] }));
 } catch { /* Keep the in-page answers usable if the browser refuses storage. */ }
}

function clearDraftsExcept(userId = null) {
 try {
  for (let index = sessionStorage.length - 1; index >= 0; index--) {
   const name = sessionStorage.key(index);
   if (name?.startsWith(prefix) && (userId === null || !name.startsWith(`${prefix}${String(userId)}.`))) sessionStorage.removeItem(name);
  }
 } catch { /* Nothing else to clear if storage is unavailable. */ }
}

onSessionCleared(() => {
 // Session cache invalidation also happens during a temporary /auth/me outage.
 // Keep local drafts in that case; the next verified owner still gates all reads.
 if (!getAccessToken()) clearDraftsExcept();
});
subscribeSession(session => {
 if (session.status === 'authenticated') clearDraftsExcept(session.reason === 'preview' ? null : session.user?.id ?? null);
});
