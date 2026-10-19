// Actual browser -> Vite -> common API -> worker -> isolated SQLite.
// Weather/catalog are synthetic. Advertisement MongoDB is not exercised here.
const {chromium}=require('playwright');
const base=process.env.SMOKE_BASE_URL||'http://127.0.0.1:19073';
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'msedge'}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(base+'/');
    // The public app now has a home screen; controls are on Today's Playlist.
    await page.getByRole('link',{name:'오늘의 선곡',exact:true}).click();
    await page.waitForURL('**/playlist');
    await page.getByRole('radio',{name:'반영하지 않음'}).check();
    const acceptedPromise=page.waitForResponse(response=>response.url().endsWith('/api/recommendation-jobs')&&response.request().method()==='POST');
    await page.getByRole('button',{name:'선곡표 받기',exact:true}).click();
    const accepted=await (await acceptedPromise).json();
    await page.getByText('45곡',{exact:true}).waitFor({timeout:30000});
    const state=await (await page.request.get(base+'/api/recommendation-jobs/'+accepted.job_id)).json();
    const playlist=await (await page.request.get(base+'/api/playlists/'+state.playlist_id)).json();
    if(playlist.context.options.region_id!==null||playlist.context.weather!==null)throw new Error('OFF must preserve no region and no weather');
    if(await page.getByRole('button',{name:'이 선곡표 승인'}).isDisabled())throw new Error('OFF without region must allow approval');
    const first=page.locator('.tracks>li').first();
    const like=first.getByRole('button',{name:/ 좋아요$/});
    await like.click();await page.waitForFunction(()=>document.querySelector('.tracks li button[aria-label$=" 좋아요"]')?.getAttribute('aria-pressed')==='true');
    await like.click();await page.waitForFunction(()=>document.querySelector('.tracks li button[aria-label$=" 좋아요"]')?.getAttribute('aria-pressed')==='false');
    await page.getByRole('radio',{name:'5점',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('[data-rating="5"]')?.getAttribute('aria-checked')==='true');
    await page.getByRole('button',{name:'평가 취소',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('[data-rating="5"]')?.getAttribute('aria-checked')==='false');
    await first.getByRole('button',{name:'제외',exact:true}).click();
    await page.getByText('이번 제외 곡 1개',{exact:false}).waitFor();
    await first.getByRole('button',{name:'제외 취소',exact:true}).click();
    // Region selectors are now visible without opening or closing a popover.
    await page.getByLabel('시·도',{exact:true}).selectOption('서울특별시');
    await page.getByLabel('시·군·구',{exact:true}).selectOption('성동구');
    await page.getByLabel('읍·면·동',{exact:true}).selectOption('region:1120065000');
    await page.getByRole('button',{name:'선택한 지역으로 날씨 변경',exact:true}).click();
    await page.getByLabel('시·도',{exact:true}).selectOption('경기도');
    if(await page.getByLabel('시·군·구',{exact:true}).inputValue()||await page.getByLabel('읍·면·동',{exact:true}).inputValue())throw new Error('Changing province must clear child selections');
    await page.setViewportSize({width:390,height:844});
    if(await page.evaluate(()=>document.body.scrollWidth>innerWidth))throw new Error('Region hierarchy must not overflow the mobile page');
    await page.setViewportSize({width:1440,height:1000});
    await page.goto(base+'/login');
    await page.getByLabel('아이디',{exact:true}).fill('browser-reviewer');
    await page.getByLabel('비밀번호',{exact:true}).fill('Browser-test-only-123!');
    await page.getByRole('button',{name:'로그인',exact:true}).click();
    await page.waitForURL('**/admin/ads');
    await page.getByRole('link',{name:'음악 관리',exact:true}).click();
    await page.getByRole('heading',{name:'음악 관리',exact:true}).waitFor();
    await page.getByRole('link',{name:'제외 이력',exact:true}).click();
    await page.getByRole('button',{name:/ 이력 보기$/}).first().waitFor();
    await page.getByRole('button',{name:'로그아웃',exact:true}).click();
    await page.waitForURL('**/login');
    if(errors.length)throw new Error('Browser errors: '+errors.join(', '));
    console.log('integration-browser-ok: region hierarchy/cascade reset, OFF without region, reaction/rating/exclusions, ADMIN login/history/logout');
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
