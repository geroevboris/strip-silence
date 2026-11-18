const {chromium}=require('playwright');
const fs=require('fs');
const path=require('path');
const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:460,height:650},deviceScaleFactor:2});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const waveform=Array.from({length:550},(_,i)=>{const t=i/550;return Math.max(.002, Math.sin(t*71)**2*(t>.07&&t<.29||t>.46&&t<.72||t>.82&&t<.92?.35:.003)*(0.4+0.6*Math.sin(i*13)**2))});
 const profile={ok:true,duration:8,peaks:Array.from({length:800},(_,i)=>waveform[Math.floor(i/800*550)]),hop:480,rate:48000,first_frame:0,end_frame:384000,waveform};
 let calls=[];
 await page.route('http://127.0.0.1:47862/**',async route=>{
   const req=route.request(),url=new URL(req.url());calls.push(url.pathname);
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,'ui.html'),'utf8')});
   let data={ok:true};
   if(url.pathname==='/api/status')data={ok:true,protocol:12,can_replace:true,actions:['replace']};
   if(url.pathname==='/api/list')data={ok:true,selected_track_index:0,tracks:[{index:0,name:'Lead vocal',clips:[{index:0,name:'Vocal · Verse 02'}],can_take_lanes:true},{index:1,name:'Double L',clips:[{index:0,name:'Verse 02'}]}]};
   if(url.pathname==='/api/clip/profile')data=profile;
   if(url.pathname==='/api/batch/analyze'){if(!req.postDataJSON().backup_originals)throw Error('Backup missing');data={ok:true,plan_id:'test',skipped_count:0};}
   if(url.pathname==='/api/batch/start')data={ok:true,job_id:'test'};
   if(url.pathname==='/api/batch/status')data={ok:true,state:'done',message:'Готово: 1 клип очищен. Оригинал — в Take Lanes.',completed:1,total:1};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 await page.goto('http://127.0.0.1:47862/');await page.waitForFunction(()=>document.getElementById('metrics').textContent.includes('Вырезается'));
 await page.screenshot({path:path.join(process.env.UI_OUTPUT || root,'clear-silence-ui.png')});
 const a=await page.locator('#metrics').innerText();
 await page.locator('#strength').fill('90');await page.locator('#strength').dispatchEvent('input');
 const b=await page.locator('#metrics').innerText();if(a===b)throw Error('Wave not reacting');
 await page.locator('#probe').click();await page.waitForFunction(()=>document.getElementById('log').textContent.includes('Готово'));
 for(const width of [420,460]){await page.setViewportSize({width,height:650});const bounds=await page.evaluate(()=>({scroll:document.body.scrollWidth,width:innerWidth,height:document.body.scrollHeight}));if(bounds.scroll>width)throw Error('Horizontal overflow');if(bounds.height>650)throw Error('Vertical overflow: '+bounds.height);console.log({width,bounds});}
 if(errors.length)throw Error(errors.join('\n'));
 console.log('UI: live preview, backup option, completed job, no console errors passed');
 await browser.close();
})();
