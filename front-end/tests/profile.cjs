const {chromium}=require('C:/Users/HOANG MAI PHUONG/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {mockSession,user}=require('./session-fixture.cjs');
const base=process.env.BASE_URL || 'http://127.0.0.1:4173';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try {
  fs.mkdirSync('tests/test-output',{recursive:true});
  for(const role of ['LEARNER','ADMIN']) {
   const page=await browser.newPage(); const errors=[]; const writes=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('request',r=>{if(['PATCH','PUT','POST'].includes(r.method())) writes.push(r.url());});
   await mockSession(page,{role,authenticated:true});
   await page.goto(base+'/#profile');
   await page.getByRole('heading',{name:role==='ADMIN'?'Hồ sơ quản trị':'Hồ sơ của tôi',exact:true}).waitFor();
   await page.getByText(user.email,{exact:true}).waitFor();
   const name=page.getByLabel('Họ tên',{exact:true}); const year=page.getByLabel('Năm sinh (không bắt buộc)',{exact:true});
   const check=page.getByRole('button',{name:'Kiểm tra thông tin',exact:true});
   await name.fill('   '); await check.click();
   assert.equal(await name.getAttribute('aria-invalid'),'true');
   assert.equal(await name.evaluate(n=>n===document.activeElement),true);
   await name.evaluate(n=>{n.value='x'.repeat(121);}); await check.click();
   await page.getByText('Họ tên không được quá 120 ký tự.',{exact:true}).waitFor();
   await name.fill('  Tên mới  ');
   for(const invalid of ['2000.5','2e3','abc','-1']){await year.fill(invalid);await check.click();assert.equal(await year.getAttribute('aria-invalid'),'true');}
   await year.fill(''); await check.click();assert.equal(await name.inputValue(),'Tên mới');
   await page.getByRole('status').filter({hasText:'Thông tin chưa được lưu'}).waitFor();
   await year.fill('2005');await check.click();assert.equal(await year.getAttribute('aria-invalid'),null);
   assert.equal(await page.locator('input[name=email],input[name=role]').count(),0);
   assert.equal(await page.getByRole('heading',{name:'Lịch sử học tập',exact:true}).count(),role==='ADMIN'?0:1);
   for(const width of [360,768,1440]) {
    await page.setViewportSize({width,height:1000});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,role+' overflow '+width);
    await page.screenshot({path:`tests/test-output/profile-${role}-${width}.png`,fullPage:true});
   }
   await name.focus();await page.keyboard.press('Tab');assert.equal(await year.evaluate(n=>n===document.activeElement),true);
   await page.reload();await name.waitFor();assert.notEqual(await name.inputValue(),'Tên mới');assert.equal(await year.inputValue(),'');
   assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
   await page.getByRole('button',{name:'Đăng xuất',exact:true}).last().click();await page.waitForURL('**/#login');
   await page.goto(base+'/#profile');await page.waitForURL('**/#login');
   await page.close();
  }
  console.log('PASS profile: both roles, validation, keyboard, 6 viewport checks, unsaved draft, no writes, reload and logout guards. API mocked only in test.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
