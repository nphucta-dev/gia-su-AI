// Static, reviewed account markup. Never interpolate user data into these templates.
export const authTemplates = {
  login: `
<main class="auth-layout auth-layout--login">
    <section class="auth-card" aria-labelledby="page-title">
      <nav class="auth-tabs" aria-label="Tài khoản">
        <a class="auth-tab is-active" href="#login" aria-current="page">Đăng nhập</a>
        <a class="auth-tab" href="#register">Đăng ký</a>
      </nav>

      <div class="card-heading">
        <p class="eyebrow">Tiếp tục học</p>
        <h1 id="page-title">Chào mừng trở lại</h1>
        <p>Nhập thông tin tài khoản để tiếp tục hành trình học của bạn.</p>
      </div>

      <form id="account-form" class="auth-form" data-auth-form="login" novalidate>
        <div class="form-message" data-form-message role="status" aria-live="polite" aria-atomic="true" tabindex="-1"></div>

        <div class="form-field">
          <label for="login-email">Email</label>
          <input id="login-email" name="email" type="email" inputmode="email" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="255" required placeholder="ban@example.com">
          <p class="field-error" id="login-email-error" data-error-for="login-email"></p>
        </div>

        <div class="form-field">
          <label for="login-password">Mật khẩu</label>
          <div class="password-field">
            <input id="login-password" name="password" type="password" autocomplete="current-password" required aria-describedby="login-password-error">
            <button class="password-toggle" type="button" data-password-toggle aria-controls="login-password" aria-pressed="false" aria-label="Hiện mật khẩu">Hiện</button>
          </div>
          <p class="field-error" id="login-password-error" data-error-for="login-password"></p>
        </div>

        <button class="primary-button" type="submit">Đăng nhập</button>
      </form>

      <p class="account-switch">Chưa có tài khoản? <a href="#register">Đăng ký ngay</a></p>
    </section>

    <aside class="product-intro" aria-labelledby="intro-title">
      <p class="intro-label">Gia sư gợi mở</p>
      <h2 id="intro-title">Tiếp tục hành trình học của bạn.</h2>
      <p>Trở lại các cuộc hội thoại, bài luyện tập và tiến độ học tập trong một không gian tập trung.</p>
      <ul class="learning-points" aria-label="Các hoạt động học tập">
        <li><span aria-hidden="true">01</span> Hỏi từng bước</li>
        <li><span aria-hidden="true">02</span> Tự kiểm tra kiến thức</li>
        <li><span aria-hidden="true">03</span> Theo dõi tiến bộ</li>
      </ul>
    </aside>
  </main>
`,
  register: `
<main class="auth-layout auth-layout--register">
    <section class="auth-card" aria-labelledby="page-title">
      <nav class="auth-tabs" aria-label="Tài khoản">
        <a class="auth-tab" href="#login">Đăng nhập</a>
        <a class="auth-tab is-active" href="#register" aria-current="page">Đăng ký</a>
      </nav>

      <div class="card-heading">
        <p class="eyebrow">Bắt đầu học</p>
        <h1 id="page-title">Tạo tài khoản</h1>
        <p>Điền thông tin bên dưới để chuẩn bị tài khoản học tập.</p>
      </div>

      <form id="account-form" class="auth-form" data-auth-form="register" novalidate>
        <div class="form-message" data-form-message role="status" aria-live="polite" aria-atomic="true" tabindex="-1"></div>

        <div class="form-field">
          <label for="register-name">Họ tên</label>
          <input id="register-name" name="name" type="text" autocomplete="name" maxlength="120" required>
          <p class="field-error" id="register-name-error" data-error-for="register-name"></p>
        </div>

        <div class="form-field">
          <label for="register-email">Email</label>
          <input id="register-email" name="email" type="email" inputmode="email" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="255" required placeholder="ban@example.com">
          <p class="field-error" id="register-email-error" data-error-for="register-email"></p>
        </div>

        <div class="form-field">
          <label for="register-password">Mật khẩu</label>
          <div class="password-field">
            <input id="register-password" name="password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required aria-describedby="register-password-hint register-password-error">
            <button class="password-toggle" type="button" data-password-toggle aria-controls="register-password" aria-pressed="false" aria-label="Hiện mật khẩu">Hiện</button>
          </div>
          <p class="field-hint" id="register-password-hint">Sử dụng từ 8 đến 128 ký tự. Khoảng trắng trong mật khẩu được giữ nguyên.</p>
          <p class="field-error" id="register-password-error" data-error-for="register-password"></p>
        </div>

        <div class="form-field">
          <label for="register-confirm-password">Nhập lại mật khẩu</label>
          <div class="password-field">
            <input id="register-confirm-password" name="confirmPassword" type="password" autocomplete="new-password" required aria-describedby="register-confirm-password-error">
            <button class="password-toggle" type="button" data-password-toggle aria-controls="register-confirm-password" aria-pressed="false" aria-label="Hiện mật khẩu xác nhận">Hiện</button>
          </div>
          <p class="field-error" id="register-confirm-password-error" data-error-for="register-confirm-password"></p>
        </div>

        <div class="consent-field">
          <input id="register-consent" name="consent" type="checkbox" required aria-describedby="register-consent-error">
          <div>
            <label for="register-consent">Tôi đồng ý với quy định sử dụng cho người học từ đủ 18 tuổi.</label>
            <p class="field-error" id="register-consent-error" data-error-for="register-consent"></p>
          </div>
        </div>

        <button class="primary-button" type="submit">Tạo tài khoản</button>
      </form>

      <p class="account-switch">Đã có tài khoản? <a href="#login">Đăng nhập</a></p>
    </section>

    <aside class="product-intro" aria-labelledby="intro-title">
      <p class="intro-label">Gia sư gợi mở</p>
      <h2 id="intro-title">Học theo cách bạn hiểu.</h2>
      <p>Hỏi từng bước, tự tìm lời giải và nhìn thấy sự tiến bộ sau mỗi bài học.</p>
      <ul class="learning-points" aria-label="Lợi ích của Gia Sư AI">
        <li><span aria-hidden="true">01</span> Gợi ý thay vì làm hộ</li>
        <li><span aria-hidden="true">02</span> Luyện tập theo chủ đề</li>
        <li><span aria-hidden="true">03</span> Phản hồi dễ hiểu</li>
      </ul>
    </aside>
  </main>
`
};
