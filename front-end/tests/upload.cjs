const {chromium}=require('C:/Users/HOANG MAI PHUONG/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.BASE_URL || 'http://127.0.0.1:4173';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try {
  const page=await browser.newPage(); const errors=[],api=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url().includes('/api/'))api.push(r.url());});
  await page.goto(base+'/#login');
  await page.getByRole('button',{name:'Vào thử tài khoản quản trị',exact:true}).click();
  await page.waitForURL('**/#admin?tab=subjects');
  const open=async()=>{
   await page.goto(base+'/#admin?tab=documents');
   await page.getByRole('button',{name:'↑ Tải tài liệu',exact:true}).click();
  };
  await open();
  const input=page.locator('#document-file'), feedback=page.locator('#file-feedback');
  const submit=page.getByRole('button',{name:'Thêm vào bản xem trước',exact:true});
  const set=async(name,mimeType,size=4)=>input.setInputFiles({name,mimeType,buffer:Buffer.alloc(size,65)});
  const valid=async()=>assert.match(await feedback.textContent(),/File đáp ứng kiểm tra ban đầu/);
  const invalid=async(pattern)=>{assert.match(await feedback.textContent(),pattern);assert.equal(await input.evaluate(n=>n.files.length),0);assert.equal(await page.getByRole('button',{name:'Xóa file',exact:true}).isVisible(),false);assert.equal(await page.locator('.upload-dropzone strong').textContent(),'Kéo thả tệp hoặc chọn từ máy');};
  await submit.click();assert.match(await feedback.textContent(),/Vui lòng chọn/);
  assert.ok(await page.locator('.field-error').count()>=2);
  await page.locator('#app').getByLabel('Môn học',{exact:true}).selectOption('Toán học');
  await page.locator('#app').getByLabel('Chủ đề',{exact:true}).selectOption('Hàm số bậc hai');
  for(const [name,mime] of [['demo.PDF','application/pdf'],['demo.TXT','text/plain'],['demo.txt','']]){await set(name,mime);await valid();}
  // Real File objects preserve an explicitly empty MIME in the drop path.
  await page.locator('.upload-dropzone').evaluate(n=>{const dt=new DataTransfer();dt.items.add(new File(['text'],'empty-mime.txt',{type:''}));n.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:dt}));});await valid();
  await set('demo.txt','text/plain',10*1024*1024);await valid();
  await set('demo.txt','text/plain',10*1024*1024+1);await invalid(/vượt giới hạn/);
  await set('demo.txt','text/plain',0);await invalid(/0 byte/);
  await set('demo.exe','application/pdf');await invalid(/Định dạng/);
  await set('demo.pdf','text/plain');await invalid(/MIME/);
  await set('demo.txt','application/octet-stream');await invalid(/MIME/);
  await set('demo.txt','text/plain');await valid();
  await page.locator('.upload-dropzone').evaluate(n=>{const dt=new DataTransfer();for(const name of ['one.txt','two.txt'])dt.items.add(new File(['text'],name,{type:'text/plain'}));n.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:dt}));});await invalid(/một file/);
  await submit.click();assert.equal(await page.locator('.upload-form').count(),1);assert.equal(await page.getByRole('button',{name:'Chọn tệp',exact:true}).evaluate(n=>n===document.activeElement),true);
  await set('repeat.txt','text/plain');await valid();
  await input.dispatchEvent('cancel');await valid();assert.equal(await input.evaluate(n=>n.files.length),1);
  await set('repeat.txt','text/plain');await valid();
  await page.getByRole('button',{name:'Xóa file',exact:true}).click();assert.equal(await input.evaluate(n=>n.files.length),0);assert.equal(await feedback.textContent(),'');
  const choose=page.getByRole('button',{name:'Chọn tệp',exact:true});
  await choose.focus();const picker=page.waitForEvent('filechooser');await page.keyboard.press('Enter');await (await picker).setFiles({name:'keyboard.txt',mimeType:'text/plain',buffer:Buffer.from('text')});await valid();
  await page.getByRole('button',{name:'Đặt lại',exact:true}).click();assert.equal(await input.evaluate(n=>n.files.length),0);assert.equal(await feedback.textContent(),'');assert.equal(await page.locator('#app').getByLabel('Chủ đề',{exact:true}).isDisabled(),true);
  const longName='<img src=x onerror=alert(1)>'+ 'a'.repeat(210)+'.txt';await set(longName,'text/plain');
  assert.equal(await page.locator('.upload-dropzone strong').textContent(),longName);assert.equal(await page.locator('.upload-dropzone img').count(),0);
  fs.mkdirSync('tests/test-output',{recursive:true});
  for(const width of [360,390,768,1440]){
   await page.setViewportSize({width,height:1000});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'upload overflow '+width);
   await page.evaluate(()=>window.scrollTo(0,0));
   await page.screenshot({path:'tests/test-output/upload-'+width+'.png',fullPage:true});
  }
  await page.getByRole('button',{name:'Hủy',exact:true}).click();await open();assert.equal(await input.evaluate(n=>n.files.length),0);assert.equal(await feedback.textContent(),'');
  await set('navigate.txt','text/plain');await page.goto(base+'/#admin?tab=subjects');await open();assert.equal(await input.evaluate(n=>n.files.length),0);
  await set('final.txt','text/plain');await page.locator('#app').getByLabel('Môn học',{exact:true}).selectOption('Toán học');await page.locator('#app').getByLabel('Chủ đề',{exact:true}).selectOption('Hàm số bậc hai');
  await page.getByLabel('Tiêu đề tài liệu',{exact:true}).fill('');await submit.click();assert.match(await page.locator('.field-error').textContent(),/tiêu đề/);
  await page.getByLabel('Tiêu đề tài liệu',{exact:true}).fill('final');await submit.click();await page.locator('.document-row').filter({hasText:'final.txt'}).waitFor();
  await open();await set('logout.txt','text/plain');
  await page.locator('.account-menu summary').click();await page.locator('.account-menu').getByRole('button',{name:'Đăng xuất',exact:true}).click();await page.waitForURL('**/#login');
  await page.goBack();await page.waitForURL('**/#login');
  await page.getByRole('button',{name:'Vào thử tài khoản quản trị',exact:true}).click();await page.waitForURL('**/#admin?tab=subjects');await open();assert.equal(await input.evaluate(n=>n.files.length),0);
  assert.deepEqual(errors,[]);assert.deepEqual(api,[]);
  console.log('PASS TK-040: validation boundaries, MIME, multiple drop, stale selection, keyboard picker, cancel event, reset/close/navigation/logout, safe long name, 4 responsive screenshots; mock only, no API.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
