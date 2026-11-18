// Use these public messages when connecting authentication services.
// Do not display raw server errors, account existence, lock status or identifiers.
export const authMessages = Object.freeze({
 invalidCredentials: 'Không thể đăng nhập với thông tin này. Vui lòng kiểm tra email và mật khẩu rồi thử lại.',
 registrationFailed: 'Chưa thể tạo tài khoản với thông tin này. Vui lòng kiểm tra lại hoặc thử đăng nhập nếu bạn đã có tài khoản.',
 rateLimited: 'Bạn đã thử quá nhiều lần. Vui lòng chờ một lúc rồi thử lại.',
 unavailable: 'Hiện chưa thể xử lý yêu cầu. Vui lòng thử lại sau.',
 expired: 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại để tiếp tục.'
});
