/**
 * Thực hiện đăng xuất phía client một cách đồng nhất và an toàn
 */
function performClientLogout() {
    try {
        // 1. Xóa toàn bộ token và thông tin phiên lưu trữ ở client
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user_info');
        localStorage.removeItem('current_session_id');
        
        sessionStorage.clear();

        console.log('Client session successfully cleared. Redirecting to login...');

        // 2. Điều hướng về trang đăng nhập (kiểm tra đường dẫn hiện tại để trỏ đúng cấp thư mục)
        const pathname = window.location.pathname;
        if (pathname.includes('/pages/') || pathname.includes('/admin/')) {
            window.location.href = '../login.html';
        } else {
            window.location.href = 'login.html';
        }
    } catch (error) {
        console.error('Error during client logout execution:', error);
        // Fallback khẩn cấp
        window.location.href = '/login.html';
    }
}

// Tự động gắn sự kiện click cho các nút có class hoặc id đăng xuất trên giao diện
document.addEventListener('DOMContentLoaded', () => {
    const logoutTriggers = document.querySelectorAll('#logout-btn, .logout-btn, [data-action="logout"]');
    logoutTriggers.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            if (window.confirm('Bạn có chắc chắn muốn đăng xuất khỏi hệ thống Gia Sư AI không?')) {
                performClientLogout();
            }
        });
    });
});