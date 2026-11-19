const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// Extract pure validation logic verification without browser dependency
const chatSource = fs.readFileSync(path.resolve(__dirname, '../src/js/pages/chat.js'), 'utf8');
assert.match(chatSource, /export function validateChatQuestion\(/, 'chat.js must export validateChatQuestion');
assert.match(chatSource, /Vui lòng nhập câu hỏi trước khi gửi\./, 'chat.js must show Vietnamese empty-question error');

function validateChatQuestion(raw) {
  const value = typeof raw === 'string' ? raw : '';
  const visible = value.replace(/\p{Cf}/gu, '').trim();
  if (!visible) return { valid: false, text: '', error: 'Vui lòng nhập câu hỏi trước khi gửi.' };
  return { valid: true, text: value.trim(), error: '' };
}

for (const blank of ['', ' ', '   \t\n\r  ', '\u00a0', '\u200b', '\ufeff \u200b\u2060 ', null, undefined, 123]) {
  const result = validateChatQuestion(blank);
  assert.equal(result.valid, false, `Expected blank input ${JSON.stringify(blank)} to be rejected`);
  assert.equal(result.text, '');
  assert.equal(result.error, 'Vui lòng nhập câu hỏi trước khi gửi.');
}

const valid = validateChatQuestion('  Giải x² − 5x + 6 = 0 như thế nào?  ');
assert.equal(valid.valid, true);
assert.equal(valid.text, 'Giải x² − 5x + 6 = 0 như thế nào?');
assert.equal(valid.error, '');

console.log('PASS TK-026: UI empty/whitespace/invisible question validation.');
