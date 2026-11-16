import { getSession, login, previewAvailable, startPreview } from '../session.js';
import { el, button } from '../components/ui.js';
import { authTemplates } from './auth-templates.js';

export function renderAccountScreen(register = false) {
  // Only local constant templates are parsed. User input is handled with textContent.
  const parsed = new DOMParser().parseFromString(authTemplates[register ? 'register' : 'login'], 'text/html');
  const main = parsed.querySelector('main');
  const layout = el('div', {className: main.className});
  layout.append(...Array.from(main.childNodes, node => document.importNode(node, true)));
  const screen = el('div', {className: 'account-screen'}, layout);
  setupForm(screen.querySelector('form'));
  const message = screen.querySelector('[data-form-message]');
  message.textContent = getSession().message;
  if (getSession().status === 'error') message.classList.add('is-error');
  if(!register && previewAvailable) {
    screen.querySelector('.auth-card').append(el('section', {className:'preview-login', 'aria-label':'Xem thử giao diện'},
      el('h2', {}, 'Xem thử giao diện'),
      el('p', {}, 'Không cần email hay mật khẩu. Dữ liệu minh họa, không kết nối API.'),
      el('div', {className:'page-actions'},
        button('Vào thử tài khoản sinh viên', () => startPreview('LEARNER'), 'primary'),
        button('Vào thử tài khoản quản trị', () => startPreview('ADMIN'), 'secondary'))));
  }
  return screen;
}


  const EMAIL_PATTERN = /^(?!\.)(?!.*\.\.)[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\.[A-Za-z]{2,}$/;

  function setDescribedBy(input, errorId) {
    const ids = new Set((input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
    ids.add(errorId);
    input.setAttribute('aria-describedby', [...ids].join(' '));
  }

  function showError(input, message) {
    const error = input.closest("form").querySelector(`[data-error-for="${input.id}"]`);
    if (!error) return;
    error.textContent = message;
    if (message) {
      input.setAttribute('aria-invalid', 'true');
      setDescribedBy(input, error.id);
    } else {
      input.removeAttribute('aria-invalid');
    }
  }

  function validateEmail(input) {
    const value = input.value.trim();
    if (!value) return 'Vui lòng nhập email.';
    if (value.length > 255 || !EMAIL_PATTERN.test(value)) {
      return 'Email chưa đúng định dạng. Vui lòng kiểm tra lại, ví dụ: ban@example.com.';
    }
    const [local, domain] = value.split('@');
    if (!local || local.length > 64 || local.endsWith('.') || !domain || domain.startsWith('-') || domain.endsWith('-') || domain.startsWith('.') || domain.endsWith('.')) {
      return 'Email chưa đúng định dạng. Vui lòng kiểm tra lại, ví dụ: ban@example.com.';
    }
    return '';
  }

  function validatorsFor(form) {
    const email = form.elements.email;
    const password = form.elements.password;
    const validators = new Map();

    if (form.dataset.authForm === 'register') {
      const name = form.elements.name;
      const confirmPassword = form.elements.confirmPassword;
      const consent = form.elements.consent;
      validators.set(name, () => {
        const value = name.value.trim();
        if (!value) return 'Vui lòng nhập họ tên.';
        if (value.length > 120) return 'Họ tên không được vượt quá 120 ký tự.';
        if (/\p{Cc}/u.test(value)) return 'Họ tên không được chứa ký tự điều khiển.';
        return '';
      });
      validators.set(email, () => validateEmail(email));
      validators.set(password, () => {
        if (!password.value) return 'Vui lòng nhập mật khẩu.';
        if (password.value.length < 8) return 'Mật khẩu cần có ít nhất 8 ký tự.';
        if (password.value.length > 128) return 'Mật khẩu không được vượt quá 128 ký tự.';
        return '';
      });
      validators.set(confirmPassword, () => {
        if (!confirmPassword.value) return 'Vui lòng nhập lại mật khẩu để xác nhận.';
        if (confirmPassword.value !== password.value) return 'Mật khẩu xác nhận chưa khớp. Vui lòng nhập lại.';
        return '';
      });
      validators.set(consent, () => consent.checked ? '' : 'Vui lòng xác nhận bạn đồng ý với quy định sử dụng trước khi tiếp tục.');
    } else {
      validators.set(email, () => validateEmail(email));
      validators.set(password, () => !password.value ? 'Vui lòng nhập mật khẩu.' : '');
    }
    return validators;
  }

  function setupPasswordToggles(form) {
    form.querySelectorAll('[data-password-toggle]').forEach((button) => {
      const input = form.querySelector('#' + button.getAttribute('aria-controls'));
      if (!input) return;
      button.addEventListener('click', () => {
        const willShow = input.type === 'password';
        input.type = willShow ? 'text' : 'password';
        button.textContent = willShow ? 'Ẩn' : 'Hiện';
        button.setAttribute('aria-pressed', String(willShow));
        const isConfirmation = input.name === 'confirmPassword';
        button.setAttribute('aria-label', `${willShow ? 'Ẩn' : 'Hiện'} mật khẩu${isConfirmation ? ' xác nhận' : ''}`);
      });
    });
  }

  function setupForm(form) {
    const message = form.querySelector('[data-form-message]');
    form.noValidate = true;
    const validators = validatorsFor(form);
    setupPasswordToggles(form);
    if (form.dataset.authForm === 'login') {
      const password = form.elements.password;
      const warning = el('p', {id: 'login-caps-warning', className: 'field-hint', hidden: true}, 'Caps Lock đang bật.');
      password.closest('.form-field').append(warning);
      setDescribedBy(password, warning.id);
      for (const type of ['keydown', 'keyup']) password.addEventListener(type, event => { warning.hidden = !event.getModifierState('CapsLock'); });
      password.addEventListener('blur', () => { warning.hidden = true; });
    }

    validators.forEach((validator, input) => {
      const eventName = input.type === 'checkbox' ? 'change' : 'input';
      input.addEventListener(eventName, () => {
        if (input.hasAttribute('aria-invalid')) showError(input, validator());
        message.textContent = '';
        message.classList.remove('is-error');
        if (input.name === 'password' && form.elements.confirmPassword?.hasAttribute('aria-invalid')) {
          showError(form.elements.confirmPassword, validators.get(form.elements.confirmPassword)());
        }
      });
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if(form.getAttribute('aria-busy') === 'true') return;
      let firstInvalid = null;
      validators.forEach((validator, input) => {
        const error = validator();
        showError(input, error);
        if (error && !firstInvalid) firstInvalid = input;
      });

      if (firstInvalid) {
        message.textContent = 'Vui lòng kiểm tra các trường được đánh dấu bên dưới.';
        message.classList.add('is-error');
        firstInvalid.focus();
        return;
      }

      if(form.dataset.authForm !== 'login') {
        message.textContent = 'Biểu mẫu đã hợp lệ. Chức năng gửi chưa được kết nối.';
        message.classList.remove('is-error');
        message.focus({preventScroll:true});
        return;
      }
      const submit = form.querySelector('[type="submit"]');
      const label = submit.textContent;
      submit.disabled = true;
      form.setAttribute('aria-busy', 'true');
      submit.textContent = 'Đang đăng nhập…';
      message.classList.remove('is-error');
      message.textContent = 'Đang xác thực tài khoản…';
      try {
        await login(form.elements.email.value, form.elements.password.value);
        form.elements.password.value = '';
      } catch(error) {
        if(!form.isConnected) return;
        message.textContent = error.message;
        message.classList.add('is-error');
        for(const [name, text] of Object.entries(error.fields || {})) {
          const input = form.elements.namedItem(name);
          if(input && typeof text === 'string') showError(input, text);
        }
        message.focus({preventScroll:true});
      } finally {
        submit.disabled = false;
        submit.textContent = label;
        form.removeAttribute('aria-busy');
      }
    });
  }