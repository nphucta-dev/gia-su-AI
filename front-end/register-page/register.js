const form = document.querySelector('#register-form');
const message = form.querySelector('[data-form-message]');
const errorFor = name => form.querySelector(`[data-error-for="${name}"]`);
const showError = (input, text) => {
  input.toggleAttribute('aria-invalid', Boolean(text));
  errorFor(input.name).textContent = text;
};
form.querySelectorAll('[data-password-toggle]').forEach(button => {
  button.addEventListener('click', () => {
    const input = document.getElementById(button.getAttribute('aria-controls'));
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    button.textContent = visible ? 'Ẩn' : 'Hiện';
    button.setAttribute('aria-pressed', String(visible));
  });
});
form.addEventListener('submit', event => {
  event.preventDefault();
  const name = form.elements.name;
  const email = form.elements.email;
  const password = form.elements.password;
  const confirm = form.elements.confirmPassword;
  const consent = form.elements.consent;
  [name, email, password, confirm, consent].forEach(input => showError(input, ''));
  let first;
  const invalid = (input, text) => { showError(input, text); if (!first) first = input; };
  if (!name.value.trim()) invalid(name, 'Vui lòng nhập họ tên.');
  if (!email.validity.valid) invalid(email, 'Vui lòng nhập email hợp lệ.');
  if (password.value.length < 8) invalid(password, 'Mật khẩu cần có ít nhất 8 ký tự.');
  if (password.value.length > 128) invalid(password, 'Mật khẩu không được vượt quá 128 ký tự.');
  if (!confirm.value) invalid(confirm, 'Vui lòng nhập lại mật khẩu để xác nhận.');
  else if (confirm.value !== password.value) invalid(confirm, 'Mật khẩu xác nhận chưa khớp.');
  if (!consent.checked) invalid(consent, 'Vui lòng đồng ý với quy định sử dụng.');
  if (first) {
    message.textContent = 'Vui lòng kiểm tra các trường được đánh dấu bên dưới.';
    message.classList.add('is-error');
    first.focus();
  } else {
    message.textContent = 'Biểu mẫu đã hợp lệ. Đây là bản xem trước giao diện.';
    message.classList.remove('is-error');
  }
});
