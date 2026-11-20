// Đoạn code tích hợp trong sự kiện gửi tin nhắn tại chat.js
async function handleSendMessage(messageText) {
    if (!messageText || !messageText.trim()) return;

    const chatContainer = document.getElementById('chat-messages-container') || document.querySelector('.chat-messages');
    const inputField = document.getElementById('chat-input') || document.querySelector('input[name="message"]');
    const sendButton = document.getElementById('send-button') || document.querySelector('button[type="submit"]');

    if (!chatContainer || !inputField) return;

    // 1. Hiển thị tin nhắn của user lên giao diện ngay lập tức
    appendMessageToUI(chatContainer, 'user', messageText);
    const userQuery = messageText;
    inputField.value = '';

    // 2. Khóa input và nút gửi để tránh spam request (Disabled state)
    inputField.disabled = true;
    if (sendButton) {
        sendButton.disabled = true;
        sendButton.classList.add('opacity-50');
    }

    // 3. Tạo bong bóng hiển thị trạng thái "AI đang suy nghĩ..." (Typing Indicator)
    const loadingId = 'ai-loading-' + Date.now();
    const loadingHtml = `
        <div id="${loadingId}" class="message-row ai-loading flex items-start space-x-3 my-3">
            <div class="message-bubble ai-bubble bg-gray-100 text-gray-800 p-3 rounded-lg rounded-tl-none text-sm flex items-center space-x-2">
                <span class="inline-block w-2 h-2 bg-gray-400 rounded-full animate-bounce"></span>
                <span class="inline-block w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100"></span>
                <span class="inline-block w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200"></span>
                <span class="ml-1 italic text-gray-500">Gia sư AI đang phân tích và soạn câu trả lời...</span>
            </div>
        </div>
    `;
    chatContainer.insertAdjacentHTML('beforeend', loadingHtml);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    try {
        // 4. Gọi API backend (Đảm bảo lấy token từ session/localStorage)
        const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
        
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': token ? `Bearer ${token}` : ''
            },
            body: JSON.stringify({ message: userQuery })
        });

        // Xóa bong bóng chờ
        document.getElementById(loadingId)?.remove();

        if (!response.ok) {
            throw new Error(`Lỗi server: ${response.status}`);
        }

        const data = await response.json();
        // Hiển thị câu trả lời thực tế từ AI (tuỳ theo cấu trúc response backend trả về, ví dụ data.reply hoặc data.response)
        const aiReply = data.reply || data.response || data.message || "Xin lỗi, mình chưa nhận được phản hồi từ hệ thống.";
        appendMessageToUI(chatContainer, 'ai', aiReply);

    } catch (error) {
        // Xóa bong bóng chờ nếu có lỗi xảy ra
        document.getElementById(loadingId)?.remove();
        appendMessageToUI(chatContainer, 'system', 'Không thể kết nối đến máy chủ gia sư AI. Vui lòng kiểm tra lại đường truyền.');
        console.error('Chat Integration Error:', error);
    } finally {
        // 5. Mở khóa lại input và nút gửi (Khôi phục trạng thái ban đầu)
        inputField.disabled = false;
        if (sendButton) {
            sendButton.disabled = false;
            sendButton.classList.remove('opacity-50');
        }
        inputField.focus();
    }
}

// Hàm phụ trợ hiển thị tin nhắn lên giao diện
function appendMessageToUI(container, sender, text) {
    const isUser = sender === 'user';
    const rowClass = isUser ? 'flex justify-end my-3' : 'flex justify-start my-3';
    const bubbleClass = isUser 
        ? 'bg-blue-600 text-white p-3 rounded-lg rounded-tr-none text-sm max-w-[80%]' 
        : 'bg-gray-100 text-gray-800 p-3 rounded-lg rounded-tl-none text-sm max-w-[80%]';

    const messageDiv = document.createElement('div');
    messageDiv.className = rowClass;
    messageDiv.innerHTML = `<div class="${bubbleClass}">${escapeHtml(text)}</div>`;
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
}

// Chống lỗi XSS cơ bản
function escapeHtml(string) {
    return String(string).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}