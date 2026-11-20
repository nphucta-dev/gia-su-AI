const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

async function run() {
 const source = fs.readFileSync(path.resolve(__dirname, '../src/js/chat-question.js'), 'utf8');
 const { validateChatQuestion } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
 for (const blank of ['', ' ', '   \t\n\r  ', '\u00a0', '\u200b', '\ufeff \u200b\u2060 ', '\u034f', '\u0301\ufe0f', '\u200d\ufe0f', null, undefined, 123]) {
  const result = validateChatQuestion(blank);
  assert.equal(result.valid, false, `Expected blank input ${JSON.stringify(blank)} to be rejected`);
  assert.equal(result.text, '');
  assert.equal(result.error, 'Vui lòng nhập câu hỏi trước khi gửi.');
 }
 for (const content of ['Giải x² − 5x + 6 = 0 như thế nào?', 'Toán có dấu tiếng Việt', 'x\u0301', '🙂', '?']) {
  const result = validateChatQuestion(`  ${content}  `);
  assert.equal(result.valid, true);
  assert.equal(result.text, content);
  assert.equal(result.error, '');
 }
 console.log('PASS TK-026: production UI validator rejects whitespace/invisible/mark-only questions and preserves visible text.');
}

run().catch(error => { console.error(error); process.exitCode = 1; });
