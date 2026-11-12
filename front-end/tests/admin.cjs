const {chromium}=require('C:/Users/HOANG MAI PHUONG/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {mockSession,user}=require('./session-fixture.cjs');
const base=process.env.BASE_URL || 'http://127.0.0.1:4173';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try {
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await mockSession(page,{role:'ADMIN',authenticated:true});
  await page.goto(base+'/#login');await page.waitForURL('**/#admin?tab=subjects');
  const nav=page.locator('.nav');const account=page.locator('.account-menu');
  assert.deepEqual(await nav.locator('a').allTextContents(),['Môn học','Chủ đề','Tài liệu nguồn']);
  assert.deepEqual(await account.locator('nav a,nav button').allTextContents(),['Hồ sơ quản trị','Đăng xuất']);
  assert.equal(await page.locator('.brand').getAttribute('href'),'#admin?tab=subjects');
  for(const width of [360,390,768,1440]){
   await page.setViewportSize({width,height:1000});
   for(const tab of ['subjects','topics','documents']){
    await page.goto(base+'/#admin?tab='+tab);await page.locator('.admin-page').waitFor();
    assert.equal(await nav.locator('[aria-current=page]').getAttribute('href'),'#admin?tab='+tab);
    assert.equal(await page.locator('.tabs [aria-current=page]').count(),1);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Overflow '+tab+' '+width);
   }
   if(width<1100){await page.locator('.mobile-menu-button').click();assert.equal(await nav.isVisible(),true);assert.equal(await page.locator('#app').evaluate(node=>node.inert),true);assert.equal(await nav.locator('a').first().evaluate(node=>node===document.activeElement),true);await page.keyboard.press('Escape');assert.equal(await page.locator('#app').evaluate(node=>node.inert),false);assert.equal(await nav.isVisible(),false);}
  }
  await page.setViewportSize({width:1440,height:1000});
  await nav.getByRole('link',{name:'Môn học',exact:true}).click();await page.waitForURL('**/#admin?tab=subjects');
  await page.getByRole('button',{name:'Thêm môn học',exact:true}).click();
  await page.getByRole('button',{name:'Thêm nội dung',exact:true}).click();await page.getByText('Vui lòng nhập tên nội dung.',{exact:true}).waitFor();
  await page.getByLabel('Tên môn học',{exact:true}).fill('Hóa học');await page.getByLabel('Cấp học',{exact:true}).fill('THPT');
  await page.getByRole('button',{name:'Thêm nội dung',exact:true}).click();await page.getByRole('heading',{name:'Hóa học',exact:true}).waitFor();
  const chemistry=page.locator('.topic-row').filter({has:page.getByRole('heading',{name:'Hóa học',exact:true})});
  await chemistry.getByRole('button',{name:'Vô hiệu hoá',exact:true}).click();await chemistry.getByText('Đã tắt',{exact:true}).waitFor();
  await chemistry.getByRole('button',{name:'Kích hoạt',exact:true}).click();
  await nav.getByRole('link',{name:'Chủ đề',exact:true}).click();await page.waitForURL('**/#admin?tab=topics');
  await page.getByRole('button',{name:'Thêm chủ đề',exact:true}).click();
  await page.getByLabel('Tên chủ đề',{exact:true}).fill('Nguyên tử');await page.getByLabel('Chương',{exact:true}).fill('Chương 1');
  await page.getByRole('button',{name:'Thêm nội dung',exact:true}).click();await page.getByText('Vui lòng chọn môn học hợp lệ.',{exact:true}).waitFor();
  await page.locator('#app').getByLabel('Môn học',{exact:true}).selectOption('Hóa học');await page.getByRole('button',{name:'Thêm nội dung',exact:true}).click();
  await page.getByRole('heading',{name:'Nguyên tử',exact:true}).waitFor();
  await page.goBack();await page.waitForURL('**/#admin?tab=subjects');await page.getByRole('heading',{name:'Hóa học',exact:true}).waitFor();
  await page.goForward();await page.waitForURL('**/#admin?tab=topics');await page.getByRole('heading',{name:'Nguyên tử',exact:true}).waitFor();
  await nav.getByRole('link',{name:'Môn học',exact:true}).click();
  await chemistry.getByRole('button',{name:'Sửa',exact:true}).click();await page.getByLabel('Tên môn học',{exact:true}).fill('Hóa học cập nhật');
  await page.getByRole('button',{name:'Lưu thay đổi',exact:true}).click();
  await nav.getByRole('link',{name:'Chủ đề',exact:true}).click();
  const atom=page.locator('.topic-row').filter({has:page.getByRole('heading',{name:'Nguyên tử',exact:true})});
  await atom.getByText('Hóa học cập nhật · Chương 1',{exact:true}).waitFor();
  await nav.getByRole('link',{name:'Tài liệu nguồn',exact:true}).click();await page.waitForURL('**/#admin?tab=documents');
  const errorRow=page.locator('.document-row').filter({hasText:'Công thức tổng hợp.pdf'});
  await errorRow.getByRole('button',{name:'Thử lại',exact:true}).click();await errorRow.getByText('Đang xử lý',{exact:true}).waitFor();
  const ready=page.getByRole('switch',{name:'Tắt nguồn Chuyên đề hàm số.pdf',exact:true});await ready.click();
  assert.equal(await page.getByRole('switch',{name:'Bật nguồn Chuyên đề hàm số.pdf',exact:true}).getAttribute('aria-checked'),'false');
  await page.getByRole('searchbox',{name:'Tìm tài liệu'}).fill('khong-co');await page.getByRole('heading',{name:'Không tìm thấy tài liệu',exact:true}).waitFor();
  await page.getByRole('searchbox',{name:'Tìm tài liệu'}).fill('');
  await page.getByRole('button',{name:'↑ Tải tài liệu',exact:true}).click();
  await page.locator('#app').getByLabel('Môn học',{exact:true}).selectOption('Hóa học cập nhật');await page.locator('#app').getByLabel('Chủ đề',{exact:true}).selectOption('Nguyên tử');
  await page.locator('#document-file').setInputFiles({name:'nguyen-tu.txt',mimeType:'text/plain',buffer:Buffer.from('demo')});
  await page.getByRole('button',{name:'Tải lên',exact:true}).click();await page.locator('.document-row').filter({hasText:'nguyen-tu.txt'}).waitFor();
  await page.goto(base+'/#profile');await page.getByRole('heading',{name:'Hồ sơ quản trị',exact:true}).waitFor();await page.getByText(user.email,{exact:true}).waitFor();
  assert.equal(await page.locator('#app').getByText('Lịch sử học tập',{exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'Lưu thông tin'}).count(),0);
  for(const route of ['home','chat','practice','results','dashboard','history','intro']){await page.goto(base+'/#'+route);await page.waitForURL('**/#admin?tab=subjects');await page.locator('.admin-page').waitFor();}
  await page.goto(base+'/#admin?tab=wrong');await page.waitForURL('**/#admin?tab=subjects');
  await page.goto(base+'/#admin?tab=documents');await page.reload();await page.locator('.document-list').waitFor();assert.ok(page.url().endsWith('#admin?tab=documents'));
  assert.equal(await page.locator('.document-row').filter({hasText:'nguyen-tu.txt'}).count(),0);
  fs.mkdirSync('tests/test-output',{recursive:true});
  for(const width of [360,768,1440]){await page.setViewportSize({width,height:1000});await page.screenshot({path:'tests/test-output/admin-documents-'+width+'.png',fullPage:true});}
  await page.goto(base+'/#profile');await page.getByRole('heading',{name:'Hồ sơ quản trị',exact:true}).waitFor();await page.screenshot({path:'tests/test-output/admin-profile.png',fullPage:true});
  await page.getByRole('button',{name:'Đăng xuất',exact:true}).last().click();await page.waitForURL('**/#login');
  await page.goBack();await page.waitForURL('**/#login');assert.equal(await page.locator('.admin-page').count(),0);
  assert.deepEqual(errors,[]);
  console.log('PASS admin: role navigation/profile, 12 tab/viewport checks, URL/Back/Forward/reload, catalog CRUD/toggles/relations, document filters/upload/retry, guest logout guard.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
