const assert = require('node:assert/strict');
const { withApplication, login } = require('./helpers.cjs');

async function runChatChecks({ browser, baseUrl }) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  const apiCalls = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/\/api\/chat\//.test(request.url())) apiCalls.push(`${request.method()} ${new URL(request.url()).pathname}`); });
  const box = page.getByRole('textbox', { name: 'Câu hỏi cho gia sư', exact: true });
  const sendButton = page.getByRole('button', { name: 'Gửi câu hỏi', exact: true });
  const hintButton = page.locator('.chat-main .message-actions button').first();
  const userBubbles = () => page.locator('.messages .message.user');
  const tutorBubbles = () => page.locator('.messages .message.assistant:not(.pending)');
  async function ask(text) {
    const reply = page.waitForResponse(r => /\/sessions\/\d+\/messages$/.test(r.url()) && r.request().method() === 'POST');
    await box.fill(text);
    await sendButton.click();
    return reply;
  }
  try {
    // Tài khoản riêng để lịch sử chat từ các bài test khác không lẫn vào.
    const email = `chat-${Date.now()}@example.com`;
    const registered = await page.request.post(`${baseUrl}/api/auth/register`, { data: { name: 'Người học chat', email, password: 'MatKhau@123', confirmPassword: 'MatKhau@123', consent: true } });
    assert.equal(registered.status(), 201);
    await login(page, baseUrl, email);
    await page.goto(`${baseUrl}/#chat`);
    await page.getByRole('heading', { name: 'Hỏi gia sư AI', exact: true }).waitFor();

    // Phiên trống: chưa tạo phiên trên server, chưa có gợi ý.
    await page.getByText('Chưa có câu hỏi nào. Nhập câu hỏi bên dưới để bắt đầu phiên học.').waitFor();
    assert.equal(await hintButton.isDisabled(), true);
    assert.equal(await page.getByLabel('Chủ đề của phiên mới', { exact: true }).locator('option').count(), 3);
    assert.deepEqual(apiCalls, ['GET /api/chat/sessions']);

    // Chặn câu hỏi trống, không gọi API.
    await sendButton.click();
    await page.getByText('Vui lòng nhập câu hỏi trước khi gửi.').waitFor();
    assert.deepEqual(apiCalls, ['GET /api/chat/sessions']);

    // Gửi câu hỏi: hiện trạng thái đang phản hồi rồi câu trả lời thật, URL giữ ID phiên.
    const first = ask('[slow] Làm sao tìm nghiệm của ax² + bx + c = 0?');
    await page.getByText('Gia sư đang suy nghĩ…').waitFor();
    assert.equal(await box.isDisabled(), true);
    assert.equal((await first).status(), 201);
    await tutorBubbles().first().waitFor();
    assert.equal(await box.isDisabled(), false);
    assert.match(page.url(), /#chat\?session=\d+$/);
    const firstId = page.url().match(/session=(\d+)$/)[1];
    await tutorBubbles().first().locator('strong', { hasText: 'Gợi ý:' }).waitFor();
    await tutorBubbles().first().locator('code', { hasText: 'ax² + bx + c = 0' }).waitFor();
    await page.locator('.session-button.active').waitFor();
    assert.equal(await hintButton.textContent(), 'Gợi ý tiếp (2/3)');

    // Gợi ý mức 2 và 3, sau đó khoá nút.
    for (const level of [2, 3]) {
      const hinted = page.waitForResponse(r => r.url().endsWith('/hints'));
      await hintButton.click();
      assert.equal((await hinted).status(), 201);
      await page.locator('.message-meta', { hasText: `Gợi ý mức ${level}/3` }).waitFor();
    }
    assert.equal(await hintButton.textContent(), 'Đã xem 3 mức gợi ý');
    assert.equal(await hintButton.isDisabled(), true);

    // Nội dung người dùng nhập không bao giờ thành HTML.
    await ask('<img src=x onerror=alert(1)>');
    await page.locator('.messages .message.user', { hasText: '<img src=x onerror=alert(1)>' }).waitFor();
    assert.equal(await page.locator('#app img').count(), 0);
    assert.equal(await hintButton.textContent(), 'Gợi ý tiếp (2/3)', 'Câu hỏi mới bắt đầu lại ở mức 1');

    // Lỗi model: câu hỏi vẫn được lưu đúng một lần, Thử lại lấy câu trả lời.
    await ask('[timeout] Hàm số đồng biến là gì?');
    await page.getByText('Gia sư phản hồi quá lâu.').waitFor();
    assert.equal(await userBubbles().filter({ hasText: '[timeout] Hàm số đồng biến là gì?' }).count(), 1);
    const retried = page.waitForResponse(r => r.url().endsWith('/hints'));
    await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
    assert.equal((await retried).status(), 201);
    await page.locator('.chat-status').filter({ hasText: 'Gia sư phản hồi quá lâu.' }).waitFor({ state: 'detached' }).catch(() => {});
    assert.equal(await page.locator('.chat-status .notice').count(), 0);
    assert.equal(await userBubbles().filter({ hasText: '[timeout] Hàm số đồng biến là gì?' }).count(), 1);
    assert.equal(await tutorBubbles().last().locator('p').first().textContent().then(t => t.startsWith('Bạn thử xác định')), true);

    // Mất mạng trước khi lưu: giữ lại nội dung đã nhập, thử lại không tạo tin trùng.
    await page.route('**/api/chat/sessions/*/messages', route => (route.request().method() === 'POST' ? route.abort() : route.continue()));
    await box.fill('Câu hỏi khi mất mạng');
    await sendButton.click();
    await page.getByText('Không thể kết nối với máy chủ.').waitFor();
    assert.equal(await box.inputValue(), 'Câu hỏi khi mất mạng');
    assert.equal(await userBubbles().filter({ hasText: 'Câu hỏi khi mất mạng' }).count(), 0);
    await page.unroute('**/api/chat/sessions/*/messages');
    await box.fill('');
    await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
    await userBubbles().filter({ hasText: 'Câu hỏi khi mất mạng' }).waitFor();
    assert.equal(await userBubbles().filter({ hasText: 'Câu hỏi khi mất mạng' }).count(), 1);

    // Lời giải đầy đủ chưa có API: vẫn xác nhận trước, nhưng không tạo nội dung giả.
    await page.getByRole('button', { name: 'Xem lời giải', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Xem lời giải', exact: true }).click();
    await page.getByText('Lời giải đầy đủ chưa được mở.').waitFor();
    assert.equal(await page.locator('.messages .message', { hasText: 'Lời giải đầy đủ' }).count(), 0);

    // Tải lại trang: lịch sử lấy từ server.
    const countBefore = await page.locator('.messages .message').count();
    await page.reload();
    await page.locator('.messages .message').first().waitFor();
    assert.equal(await page.locator('.messages .message').count(), countBefore);
    assert.equal(page.url().endsWith(`#chat?session=${firstId}`), true);

    // Phiên mới ở chủ đề khác, rồi quay lại phiên cũ.
    await page.getByRole('button', { name: '+ Phiên mới', exact: true }).click();
    await page.getByText('Chưa có câu hỏi nào.').waitFor();
    await page.getByLabel('Chủ đề của phiên mới', { exact: true }).selectOption({ label: 'Toán học · Hàm số và đồ thị' });
    await ask('Đồ thị hàm bậc nhất là gì?');
    await tutorBubbles().first().waitFor();
    assert.match(page.url(), /#chat\?session=\d+$/);
    assert.notEqual(page.url().match(/session=(\d+)$/)[1], firstId);
    assert.equal(await page.locator('.chat-main h2').first().textContent(), 'Hàm số và đồ thị');
    assert.equal(await page.locator('.session-button').count(), 2);
    await page.locator('.session-button').filter({ hasText: 'ax² + bx + c = 0' }).click();
    await userBubbles().first().filter({ hasText: 'ax² + bx + c = 0' }).waitFor();
    assert.equal(await page.locator('.chat-main h2').first().textContent(), 'Phép cộng phân số', 'Không có tham số thì dùng chủ đề đầu tiên của danh mục');

    // Liên kết từ trang học mở phiên trống đúng chủ đề.
    await page.goto(`${baseUrl}/#chat?topic=2`);
    await page.reload();
    await page.getByText('Chưa có câu hỏi nào.').waitFor();
    assert.equal(await page.locator('.chat-main h2').first().textContent(), 'Hàm số và đồ thị');
    await page.goto(`${baseUrl}/#chat?session=999`);
    await page.reload();
    await page.getByRole('heading', { name: 'Không tìm thấy phiên chat', exact: true }).waitFor();

    for (const width of [360, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`${baseUrl}/#chat?session=${firstId}`);
      await page.reload();
      await page.locator('.messages .message').first().waitFor();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `Chat overflow at ${width}px`);
    }
    assert.deepEqual(errors, []);
    console.log('PASS: chat sessions/history/hints via real API, empty/loading/error/retry, no duplicate on retry, safe rendering, reload and responsive.');
  } finally {
    await context.close();
  }
}

module.exports = { runChatChecks };

if (require.main === module) withApplication(runChatChecks).catch(error => { console.error(error); process.exit(1); });
