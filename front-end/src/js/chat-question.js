export function validateChatQuestion(raw) {
 const value = typeof raw === 'string' ? raw : '';
 if (!/[^\p{C}\p{M}\p{Z}\s]/u.test(value)) return { valid: false, text: '', error: 'Vui lòng nhập câu hỏi trước khi gửi.' };
 return { valid: true, text: value.trim(), error: '' };
}
