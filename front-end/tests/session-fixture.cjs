// Isolated API responses for browser tests only. Never imported by application code.
const user = {id:'test-user',name:'Sinh viên kiểm thử',email:'learner@example.com',role:'LEARNER'};
async function mockSession(page, {role='LEARNER', authenticated=false} = {}) {
 await page.route('http://localhost:8000/api/auth/me', route => route.fulfill({json:{user:{...user,name:role === 'ADMIN' ? 'Quản trị viên kiểm thử' : user.name,role}}}));
 await page.route('http://localhost:8000/api/auth/login', route => route.fulfill({json:{}}));
 if(authenticated) await page.addInitScript(() => sessionStorage.setItem('gia-su-ai.access-token','test-only-token'));
}
module.exports = { mockSession, user };
