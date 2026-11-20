import { onSessionCleared } from './session.js';

let previewQuizResult = null;
let lastQuizId = null;

export function setPreviewQuizResult(result) {
  previewQuizResult = result;
}

export function getPreviewQuizResult() {
  return previewQuizResult;
}

export function setLastQuizId(id) {
  lastQuizId = id;
}

export function getLastQuizId() {
  return lastQuizId;
}

onSessionCleared(() => {
  previewQuizResult = null;
  lastQuizId = null;
});

