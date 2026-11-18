const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const chatSource = fs.readFileSync(path.resolve(__dirname, '../src/js/pages/chat.js'), 'utf8');
const uiSource = fs.readFileSync(path.resolve(__dirname, '../src/js/components/ui.js'), 'utf8');

assert.match(uiSource, /export function confirmDialog\(/, 'ui.js must export confirmDialog');
assert.match(chatSource, /const solutionButton = button\('Xem lời giải'/, 'chat.js must render Xem lời giải button');
assert.match(chatSource, /await confirmDialog\(\s*'Xem lời giải đầy đủ\?'/, 'requestSolution must open confirmation modal before API call');
assert.match(chatSource, /if \(!confirmed\)\s*\{[\s\S]*return;/, 'Cancelling modal must abort without calling solution API');
assert.match(chatSource, /api\(`\/chat\/sessions\/\$\{sessionId\}\/solution`,\s*\{\s*method:\s*'POST',\s*body:\s*\{\s*confirmed:\s*true\s*\}/, 'Confirming modal must call POST /chat/sessions/{id}/solution with confirmed: true');
assert.match(chatSource, /assistant\.isFullSolution !== true/, 'chat.js must validate isFullSolution flag from server');

console.log('PASS TK-035: solution confirmation modal guards full-solution API call.');
