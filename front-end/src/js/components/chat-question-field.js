import { validateChatQuestion } from '../chat-question.js';
import { el } from './ui.js';
import { clearError, validateFields } from './validation.js';

export function createChatQuestionField() {
 const input = el('textarea', {
  className: 'textarea',
  placeholder: 'Nhập câu hỏi của bạn…',
  'aria-label': 'Câu hỏi cho gia sư',
  maxlength: 4000,
 });
 const field = el('div', { className: 'field composer-question-field' }, input);
 const clearQuestionError = () => clearError(input);

 input.addEventListener('input', () => {
  if (input.hasAttribute('aria-invalid') && validateChatQuestion(input.value).valid) {
   clearQuestionError();
  }
 });

 function readQuestion() {
  const question = validateChatQuestion(input.value);
  return validateFields([[input, question.error]]) ? question.text : null;
 }

 function bindEnter(form, send) {
  input.addEventListener('keydown', event => {
   if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;
   event.preventDefault();
   if (!event.repeat && !send.disabled) form.requestSubmit(send);
  });
 }

 return { field, input, readQuestion, clearQuestionError, bindEnter };
}
