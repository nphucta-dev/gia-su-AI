let counter = 0;
export function clearError(input) {
 const id = input.dataset.errorId;
 if (id) {
  document.getElementById(id)?.remove();
  const remaining = (input.getAttribute('aria-describedby') || '').split(' ').filter(v => v && v !== id);
  if (remaining.length) input.setAttribute('aria-describedby', remaining.join(' ')); else input.removeAttribute('aria-describedby');
 }
 input.removeAttribute('aria-invalid');
}
export function showError(input, message) {
 clearError(input);
 const error = document.createElement('p'); error.className = 'field-error'; error.id = `validation-error-${++counter}`; error.textContent = message;
 input.dataset.errorId = error.id;
 input.setAttribute('aria-invalid', 'true'); input.setAttribute('aria-describedby', [input.getAttribute('aria-describedby'), error.id].filter(Boolean).join(' '));
 (input.closest('.field') || input.closest('.consent-row')?.parentElement || input.parentElement).append(error);
}
export function validateFields(rules) {
 let first = null;
 for (const [input, message] of rules) { clearError(input); if (message) { showError(input, message); first ||= input; } }
 first?.focus(); return !first;
}
export function setupValidation(form, inputs) {
 form.noValidate = true;
 inputs.forEach(input => { input.addEventListener('input', () => clearError(input)); input.addEventListener('change', () => clearError(input)); });
}
