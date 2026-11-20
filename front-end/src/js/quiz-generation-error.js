export function quizGenerationError(error) {
 const messages = {
  QUIZ_INVALID_RESPONSE: 'AI chưa tạo được bộ câu hỏi hợp lệ. Hãy thử tạo lại bài.',
  INVALID_QUIZ_RESPONSE: 'Bộ câu hỏi từ máy chủ chưa hợp lệ. Hãy thử tạo lại bài.',
  INVALID_RESPONSE: 'Phản hồi từ máy chủ chưa hợp lệ. Chưa xác nhận được kết quả tạo bài.',
  LLM_TIMEOUT: 'AI phản hồi quá lâu. Chưa xác nhận được kết quả tạo bài.',
  NETWORK_ERROR: 'Không thể kết nối với máy chủ. Chưa xác nhận được kết quả tạo bài.',
  LLM_UNAVAILABLE: 'Chưa thể kết nối với dịch vụ AI.',
  LLM_ERROR: 'Dịch vụ AI chưa xử lý được yêu cầu.',
  LLM_INVALID_RESPONSE: 'Phản hồi từ dịch vụ AI chưa hợp lệ.',
  LLM_RATE_LIMITED: 'Dịch vụ AI đang giới hạn yêu cầu. Hãy thử lại sau.',
  LLM_NOT_CONFIGURED: 'Dịch vụ tạo bài chưa sẵn sàng. Vui lòng liên hệ quản trị viên.',
  TOPIC_NOT_FOUND: 'Chủ đề không tồn tại hoặc đã tắt. Hãy chọn chủ đề khác.',
  TOPIC_CLOSED: 'Chủ đề đã tắt. Hãy chọn chủ đề khác.',
  VALIDATION_ERROR: 'Hãy kiểm tra lại chủ đề và độ khó trước khi tạo bài.',
  INVALID_QUIZ_CONTEXT: 'Nội dung chủ đề chưa hợp lệ. Hãy chọn chủ đề khác.',
  AI_QUOTA_EXCEEDED: 'Bạn đã dùng hết lượt AI. Hãy xem hạn mức sử dụng trước khi tạo lại.',
  AI_REQUEST_BUSY: 'Một yêu cầu AI đang được xử lý. Hãy chờ rồi thử lại.',
  QUIZ_SAVE_FAILED: 'Chưa thể lưu bài luyện tập. Hãy thử lại sau.',
 };
 const blocked = [401, 403, 404, 422].includes(error?.status)
  || ['LLM_NOT_CONFIGURED', 'TOPIC_NOT_FOUND', 'TOPIC_CLOSED', 'INVALID_QUIZ_CONTEXT', 'AI_QUOTA_EXCEEDED'].includes(error?.code);
 return {
  message: error?.status === 403 ? 'Bạn không có quyền tạo bài với lựa chọn này.'
   : messages[error?.code] || (error?.status === 404 ? messages.TOPIC_NOT_FOUND : 'Chưa thể tạo bài luyện tập. Hãy thử lại sau.'),
  retryable: !blocked,
 };
}
