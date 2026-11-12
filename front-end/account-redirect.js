const route = location.pathname.endsWith('/register.html') ? 'register' : 'login';
location.replace(new URL('./index.html#' + route, location.href));
