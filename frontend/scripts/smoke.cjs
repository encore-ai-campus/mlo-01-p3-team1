// Integration smoke: actual browser + C API/worker. No B API calls are mocked.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
(async()=>{
  const out=path.resolve(__dirname,'../../artifacts/browser');fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true,channel:process.env.SMOKE_BROWSER||'msedge'});
  const context=await browser.newContext({viewport:{width:1536,height:1024}});
  const page=await context.newPage();const errors=[],mutations=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('request',request=>{if(['POST','PUT'].includes(request.method())&&/\/api\/(playlists|playlist-families|recommendation-jobs)/.test(request.url()))mutations.push(request.url());});
  await page.goto('http://127.0.0.1:5173');
  await page.getByLabel('우리 동네').selectOption('demo-region');
  await page.getByRole('button',{name:'선곡표 받기',exact:true}).click();
  await page.getByText('45곡',{exact:true}).waitFor({timeout:30000});
  if(await page.locator('.tracks>li').count()!==45)throw new Error('Expected 45 rendered tracks');
  await page.mouse.move(0,0);
  const layout=await page.evaluate(()=>({
    panels:[...document.querySelectorAll('.music-grid>.card')].map(n=>{const b=n.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height};}),
    primary:getComputedStyle(document.querySelector('.selection .primary')).backgroundColor,
    top:document.querySelector('.banner-top').getBoundingClientRect().height,
    bottom:document.querySelector('.banner-bottom').getBoundingClientRect().height,
    forecast:document.querySelectorAll('.forecast-hour').length,
    bodyHeight:document.body.scrollHeight,
    cover:{width:document.querySelector('.album-cover').getBoundingClientRect().width,height:document.querySelector('.album-cover').getBoundingClientRect().height},
  }));
  await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});
  if(layout.primary!=='rgb(8, 123, 241)'||layout.top!==120||layout.bottom!==104||layout.forecast!==4)throw new Error('Mockup palette/banner/forecast mismatch: '+JSON.stringify(layout));
  if(layout.panels.some(p=>p.y!==330||p.height!==574)||layout.bodyHeight!==1024)throw new Error('Desktop compact layout mismatch: '+JSON.stringify(layout));
  if(Math.abs(layout.cover.width-layout.cover.height)>1)throw new Error('Album cover must remain square');
  if(await page.locator('.selection input[type=radio]').count()!==5||await page.locator('.chips input').count()!==27)throw new Error('Selection inputs missing');
  await page.locator('.tracks li').first().getByRole('button',{name:'제외',exact:true}).click();
  await page.getByText('이번 제외 곡 1개',{exact:false}).waitFor();
  if(!await page.getByRole('button',{name:'이 선곡표 승인'}).isDisabled())throw new Error('Unapplied exclusions must block approval');
  await page.locator('.tracks li').first().getByRole('button',{name:'제외 취소',exact:true}).click();
  await page.getByRole('button',{name:'이 선곡표 승인'}).click();
  await page.getByText('승인한 선곡표예요.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'사용 안내',exact:true}).click();
  const beforeGuide=mutations.length;
  await page.getByRole('dialog').waitFor();
  await page.locator('.guide-focus').waitFor();
  await page.screenshot({path:path.join(out,'guide.png'),fullPage:true});
  if(!await page.locator('main').evaluate(n=>n.closest('[inert]')!==null))throw new Error('Guide must isolate underlying operations');
  await page.keyboard.press('Tab');
  if(!await page.evaluate(()=>document.querySelector('[role=dialog]').contains(document.activeElement)))throw new Error('Guide focus escaped');
  await page.getByRole('dialog').getByRole('button',{name:'다음',exact:true}).click();
  await page.getByRole('heading',{name:'매장의 분위기를 골라 주세요'}).waitFor();
  await page.getByRole('dialog').getByRole('button',{name:'이전',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'다음',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'다음',exact:true}).click();
  await page.getByRole('heading',{name:'선곡표를 살펴보고 승인해 주세요'}).waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('dialog').waitFor({state:'hidden'});
  if(mutations.length!==beforeGuide)throw new Error('Guide produced real music mutations');
  await page.getByRole('button',{name:'다른 선곡표 요청',exact:true}).click();
  await page.getByText('재설정 서비스 연결을 기다리고 있어요. 현재 선곡표는 유지됩니다.',{exact:false}).waitFor();
  if(await page.locator('.tracks>li').count()!==45)throw new Error('Provider failure lost parent');
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Mobile horizontal overflow');
  await page.getByRole('button',{name:'사용 안내',exact:true}).click();
  const mobileGuide=await page.getByRole('dialog').boundingBox();
  if(!mobileGuide||mobileGuide.x<0||mobileGuide.x+mobileGuide.width>390)throw new Error('Mobile guide overflow');
  await page.keyboard.press('Escape');
  await page.goto('http://127.0.0.1:5173/login');
  await page.getByRole('heading',{name:'로그인'}).waitFor();
  await page.setViewportSize({width:1536,height:1024});
  await page.screenshot({path:path.join(out,'login.png'),fullPage:true});
  await page.getByLabel('비밀번호',{exact:true}).fill('temporary-check');
  await page.getByRole('button',{name:'비밀번호 표시',exact:true}).click();
  if(await page.getByLabel('비밀번호',{exact:true}).getAttribute('type')!=='text')throw new Error('Password visibility control failed');
  await page.getByRole('button',{name:'비밀번호 숨기기',exact:true}).click();
  await page.reload();
  if(await page.getByLabel('비밀번호',{exact:true}).inputValue()!=='')throw new Error('Password persisted');
  await page.goto('http://127.0.0.1:5173/admin/feedback/exclusions');
  await page.getByText('관리자 인증과 해당 메뉴의 권한 확인이 필요합니다.',{exact:false}).waitFor();
  if(errors.length)throw new Error(errors.join('\n'));
  console.log(JSON.stringify({checks:['45-track generation','mockup geometry/palette/inputs','exclusion save/cancel','approval','guide isolation/Escape','regeneration failure preserves parent','390px no overflow','login/password visibility and no persistence','admin denial'],layout,pageErrors:errors,screenshots:out}));
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
