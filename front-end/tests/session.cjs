const {chromium} = require('C:/Users/HOANG MAI PHUONG/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const {user} = require('./session-fixture.cjs');
const base = process.env.BASE_URL || 'http://127.0.0.1:4173';
(async () => {
 const browser = await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try {
  const page = await browser.newPage();
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  let role='LEARNER', mode='ok', loginMode='ok', delay=0, loginDelay=0, loginCalls=0;
  await page.route('http://localhost:8000/api/auth/me', async route => {
   if(delay) await new Promise(r=>setTimeout(r,delay));
   if(mode==='network') return route.abort();
   if(mode==='expired') return route.fulfill({status:401,json:{error:{code:'TOKEN_EXPIRED',message:'Phiên đã hết hạn.'}}});
   return route.fulfill({json:{user:{...user,role}}});
  });
  await page.route('http://localhost:8000/api/auth/login', async route => {
   loginCalls++;
   if(loginDelay) await new Promise(r=>setTimeout(r,loginDelay));
   const payload=route.request().postDataJSON();
   assert.equal(payload.email,'learner@example.com');
   assert.equal(payload.password,' secret password ');
   if(loginMode==='missing') return route.fulfill({status:404,json:{detail:'Not Found'}});
   if(loginMode==='invalid') return route.fulfill({status:401,json:{error:{code:'INVALID_CREDENTIALS',message:'Email hoặc mật khẩu không đúng.'}}});
   return route.fulfill({json:{access_token:'test-only-token',token_type:'bearer',expires_in:1800,user:{...user,role:'ADMIN'}}});
  });
  const accountNav=page.locator('.account-menu nav');
  async function signIn() {
   await page.goto(base+'/#login');
   await page.getByLabel('Email',{exact:true}).fill('LEARNER@example.com');
   await page.getByLabel('Mật khẩu',{exact:true}).fill(' secret password ');
   await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  }
  await page.goto(base);
  await page.waitForURL('**/#intro');
  for (const width of [360,390,768,1440]) {
   await page.setViewportSize({width,height:900});
   const inset = await page.locator('.header-inner').evaluate(header => {
    const box = header.getBoundingClientRect();
    const style = getComputedStyle(header);
    const account = header.querySelector('.header-actions').getBoundingClientRect();
    return box.right - parseFloat(style.paddingRight) - account.right;
   });
   assert.ok(Math.abs(inset) < 2, 'Account controls align with the right header edge');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  }
  const intro = page.locator('#app');
  assert.equal(await intro.getByRole('link',{name:'Tạo tài khoản',exact:true}).count(),0);
  assert.equal(await intro.getByRole('link',{name:'Đăng nhập',exact:true}).count(),0);
  assert.equal(await intro.getByRole('link',{name:'Khám phá các chủ đề',exact:true}).count(),1);
  await intro.getByRole('link',{name:'Khám phá các chủ đề',exact:true}).click();
  await page.waitForURL('**/#home');
  await page.getByRole('heading',{name:'Hôm nay bạn muốn học gì?',exact:true}).waitFor();
  assert.equal(await page.locator('.nav').isVisible(),false);
  assert.equal(await page.locator('.brand').getAttribute('href'),'#intro');
  await page.goto(base+'/#dashboard');
  await page.waitForURL('**/#login');
  await page.locator('form[data-auth-form="login"]').waitFor();
  assert.equal(await accountNav.locator('a[href="#admin"]').count(),0);
  assert.equal(await accountNav.locator('a[href="#profile"]').count(),0);
  for (const width of [390,1440]) {
   await page.setViewportSize({width,height:900});
   assert.equal(await page.locator('.nav').isVisible(),false);
   assert.equal(await page.locator('.mobile-menu-button').isVisible(),false);
  }
  loginMode='invalid'; await signIn();
  await page.getByText('Email hoặc mật khẩu không đúng.',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>sessionStorage.length),0);
  loginMode='missing'; await signIn();
  await page.getByText('Backend đang chạy chưa có API đăng nhập.',{exact:false}).waitFor();
  loginMode='ok'; await signIn();
  await page.waitForURL('**/#dashboard');
  await page.getByRole('heading',{name:'Tổng quan học tập',exact:true}).waitFor();
  assert.equal(await page.locator('.nav').isVisible(),true);
  for(const route of ['home','chat','practice','dashboard']) assert.equal(await page.locator('.nav a[href="#'+route+'"]').isVisible(),true);
  await page.setViewportSize({width:390,height:900});
  assert.equal(await page.locator('.mobile-menu-button').isVisible(),true);
  await page.locator('.mobile-menu-button').click();
  assert.equal(await page.locator('.nav').isVisible(),true);
  await page.keyboard.press('Escape');
  await page.setViewportSize({width:1440,height:900});
  assert.equal(await accountNav.locator('a[href="#login"],a[href="#register"],a[href="#admin"]').count(),0);
  assert.equal(await accountNav.getByRole('button',{name:'Đăng xuất',includeHidden:true}).count(),1);
  await page.locator('.account-menu summary').click();
  await page.screenshot({path:'tests/test-output/learner-account-menu.png',fullPage:true});
  await page.keyboard.press('Escape');
  await page.goto(base+'/#profile');
  await page.getByRole('heading',{name:user.name,exact:true}).waitFor();
  assert.equal(await page.getByRole('link',{name:'Khu vực quản trị'}).count(),0);
  await page.goto(base+'/#admin');
  await page.getByRole('heading',{name:'Không có quyền truy cập',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Tài liệu nguồn',exact:true}).count(),0);
  await page.reload(); await page.getByRole('heading',{name:'Không có quyền truy cập',exact:true}).waitFor();
  for(const width of [360,390,768,1440]){
   await page.setViewportSize({width,height:900});
   await page.locator('.account-menu summary').click();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.keyboard.press('Escape');
   assert.equal(await page.locator('.account-menu').getAttribute('open'),null);
   assert.equal(await page.locator('.account-menu summary').evaluate(n=>n===document.activeElement),true);
  }
  await page.locator('.account-menu summary').click();
  await accountNav.getByRole('button',{name:'Đăng xuất',exact:true}).click();
  await page.waitForURL('**/#login');
  assert.equal(await page.locator('.nav').isVisible(),false);
  assert.equal(await page.locator('.mobile-menu-button').isVisible(),false);
  assert.equal(await page.evaluate(()=>sessionStorage.getItem('gia-su-ai.access-token')),null);
  assert.equal(await page.getByLabel('Mật khẩu',{exact:true}).inputValue(),'');
  await page.goBack(); await page.waitForURL('**/#login');
  await page.reload(); await page.locator('form[data-auth-form="login"]').waitFor();
  role='ADMIN'; await signIn(); await page.waitForURL('**/#admin?tab=subjects');
  await page.getByRole('heading',{name:'Quản lý môn học',exact:true}).waitFor();
  assert.equal(await accountNav.getByRole('link',{name:'Hồ sơ quản trị',includeHidden:true}).count(),1);
  role='LEARNER'; await page.goto(base+'/#admin'); await page.reload();
  await page.getByRole('heading',{name:'Không có quyền truy cập',exact:true}).waitFor();
  mode='expired'; await page.reload(); await page.waitForURL('**/#login');
  await page.getByText('Phiên đăng nhập không còn hợp lệ.',{exact:false}).waitFor();
  assert.equal(await page.evaluate(()=>sessionStorage.length),0);
  mode='ok'; role='ROOT'; await signIn();
  await page.getByText('Thông tin tài khoản hoặc vai trò không hợp lệ.',{exact:false}).waitFor();
  assert.equal(await page.evaluate(()=>sessionStorage.length),0);
  role='LEARNER'; await signIn(); await page.waitForURL('**/#dashboard');
  mode='network'; await page.reload(); await page.getByRole('heading',{name:'Chưa xác minh được phiên',exact:true}).waitFor();
  assert.equal(await page.getByRole('heading',{name:'Tổng quan học tập',exact:true}).count(),0);
  mode='ok'; await page.getByRole('button',{name:'Thử lại',exact:true}).click();
  await page.getByRole('heading',{name:'Tổng quan học tập',exact:true}).waitFor();
  delay=400; await page.reload(); await page.getByRole('heading',{name:'Đang kiểm tra phiên…',exact:true}).waitFor();
  await page.goto(base+'/#history');
  await page.goto(base+'/#dashboard');
  assert.equal(await accountNav.locator('a[href="#admin"]').count(),0);
  await page.getByRole('heading',{name:'Tổng quan học tập',exact:true}).waitFor(); delay=0;
  await page.goto(base+'/#profile'); await page.getByRole('heading',{name:user.name,exact:true}).waitFor();
  await page.goto(base+'/#home');
  await page.locator('.account-menu summary').click();
  await accountNav.getByRole('button',{name:'Đăng xuất',exact:true}).click(); await page.waitForURL('**/#login');
  assert.equal(await page.evaluate(()=>localStorage.length),0);
  loginDelay=400;
  await signIn();
  await page.goto(base+'/#intro');
  await new Promise(r=>setTimeout(r,600));
  assert.equal(await page.evaluate(()=>sessionStorage.length),0);
  assert.equal(await accountNav.locator('a[href="#profile"]').count(),0);
  assert.ok(loginCalls>=6);
  assert.deepEqual(errors,[]);
  console.log('PASS session: guests, verified LEARNER/ADMIN, untrusted login role, blocked admin/deep links, keyboard/mobile, local logout/Back/reload/relogin, missing API, invalid login/role, expiration, network retry and loading.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
