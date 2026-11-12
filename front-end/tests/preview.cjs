const {chromium}=require('C:/Users/HOANG MAI PHUONG/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
const base=process.env.BASE_URL || 'http://127.0.0.1:4173';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const page=await browser.newPage(); const api=[];const errors=[];
  page.on('request',r=>{if(r.url().includes('/api/'))api.push(r.url());});page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#login');
  await page.getByRole('button',{name:'Vào thử tài khoản sinh viên',exact:true}).click();
  await page.waitForURL('**/#dashboard');await page.getByRole('heading',{name:'Tổng quan học tập',exact:true}).waitFor();
  assert.equal(await page.locator('#preview-banner').isVisible(),true);
  assert.equal(await page.locator('.account-menu a[href="#admin"]').count(),0);
  for(const route of ['home','chat','practice','results','profile','history','dashboard']){
   await page.goto(base+'/#'+route);await page.locator('#app > div').waitFor();
   assert.ok(page.url().endsWith('#'+route));
  }
  await page.goto(base+'/#admin');await page.getByRole('heading',{name:'Không có quyền truy cập',exact:true}).waitFor();
  await page.reload();await page.getByRole('heading',{name:'Không có quyền truy cập',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>sessionStorage.getItem('gia-su-ai.access-token')),null);
  await page.locator('.account-menu summary').click();await page.locator('.account-menu').getByRole('button',{name:'Đăng xuất',exact:true}).click();
  await page.waitForURL('**/#login');assert.equal(await page.locator('#preview-banner').isVisible(),false);
  assert.equal(await page.evaluate(()=>sessionStorage.length),0);
  await page.getByRole('button',{name:'Vào thử tài khoản quản trị',exact:true}).click();
  await page.waitForURL('**/#admin?tab=subjects');await page.getByRole('heading',{name:'Quản lý môn học',exact:true}).waitFor();
  await page.reload();await page.getByRole('heading',{name:'Quản lý môn học',exact:true}).waitFor();
  for(const width of [360,768,1440]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
  assert.deepEqual(api,[]);assert.deepEqual(errors,[]);
  console.log('PASS preview: LEARNER/ADMIN screens, permissions, navigation, reload, logout, banner, responsive; no API calls or real tokens.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
