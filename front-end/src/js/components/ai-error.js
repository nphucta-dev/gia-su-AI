import { el, button } from './ui.js';

export function aiErrorMessage(error) {
 const titles = {
  LLM_TIMEOUT: 'Gia sư phản hồi quá lâu.',
  LLM_UNAVAILABLE: 'Chưa thể kết nối với dịch vụ AI.',
  LLM_ERROR: 'Dịch vụ AI chưa xử lý được yêu cầu.',
  LLM_INVALID_RESPONSE: 'Gia sư trả về phản hồi chưa hợp lệ.',
  INVALID_RESPONSE: 'Phản hồi từ máy chủ chưa hợp lệ.',
  LLM_RATE_LIMITED: 'Dịch vụ AI đang giới hạn yêu cầu. Hãy thử lại sau.',
  LLM_NOT_CONFIGURED: 'Gia sư AI chưa sẵn sàng. Vui lòng liên hệ quản trị viên.',
  CHAT_BUSY: 'Phiên đang xử lý một yêu cầu khác. Vui lòng thử lại sau.',
  CHAT_CHANGED: 'Hội thoại vừa thay đổi. Hãy tải lại hội thoại.',
  CHAT_REPLY_EXISTS: 'Câu hỏi đã có phản hồi. Hãy tải lại hội thoại.',
  CHAT_RETRY_NOT_NEEDED: 'Không có câu hỏi chờ phản hồi. Hãy tải lại hội thoại.',
  TOPIC_CLOSED: 'Chủ đề đã đóng. Bạn vẫn có thể đọc lịch sử.',
  AI_QUOTA_EXCEEDED: 'Bạn đã dùng hết lượt AI. Bạn vẫn có thể đọc lịch sử.',
  DAILY_AI_QUOTA_EXCEEDED: 'Bạn đã dùng hết lượt AI. Bạn vẫn có thể đọc lịch sử.',
 };
 const forbidden = error?.status === 403 || error?.status === 404;
 const reload = ['CHAT_CHANGED', 'CHAT_REPLY_EXISTS', 'CHAT_RETRY_NOT_NEEDED'].includes(error?.code);
 const blocked = forbidden || error?.status === 401 || ['LLM_NOT_CONFIGURED', 'TOPIC_CLOSED', 'AI_QUOTA_EXCEEDED', 'DAILY_AI_QUOTA_EXCEEDED'].includes(error?.code);
 return {
  title: forbidden ? 'Không thể truy cập phiên học này.' : titles[error?.code] || (error?.status === 0 && error?.code === 'NETWORK_ERROR' ? 'Mất kết nối với máy chủ.' : 'Chưa thể nhận phản hồi từ gia sư.'),
  action: blocked ? null : reload ? 'reload' : 'retry',
 };
}

export function renderAiError(error, { description = 'Lịch sử hiện tại vẫn được giữ.', onRetry, onReload } = {}) {
 const state = aiErrorMessage(error);
 const action = state.action === 'reload' ? onReload : state.action === 'retry' ? onRetry : null;
 return el('div', { className: 'notice error ai-error' },
  el('strong', {}, state.title), el('p', {}, description),
  action ? button(state.action === 'reload' ? 'Tải lại hội thoại' : 'Thử lại', action, 'secondary small') : null);
}
