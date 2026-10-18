// Browser layout/adapter verification only: ads HTTP responses are fixtures here.
// This is not an application data provider and is never imported by the app.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.SMOKE_BASE_URL||'http://127.0.0.1:19073';
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try{
    const page=await browser.newPage({viewport:{width:1536,height:1024}}),errors=[],operations=[];
    page.on('pageerror',error=>errors.push(error.message));
    const ads=['카페 운영을 위한 추천 상품','매장 운영에 도움이 되는 서비스','겨울 원두 기획전'].map((title,index)=>({
      ad_id:'layout-ad-'+index,title,asset_id:'layout-asset-'+index,link_url:'https://cafe.example/products',
      placement:index===1?'bottom':'top',starts_at:index===2?'2026-11-01T00:00:00Z':'2026-10-08T00:00:00Z',
      ends_at:index===2?'2026-12-01T00:00:00Z':'2026-11-01T00:00:00Z',priority:1,version:1,paused:false,
      status:index===2?'RESERVED':'ACTIVE',daily_budget_tokens:10000,total_budget_tokens:100000,
      measurement:{status:'READY',impressions:[6240,4000,0][index],clicks:[112,74,0][index]}}));
    await page.route('**/api/admin/ad-assets/**',route=>route.fulfill({status:200,contentType:'image/svg+xml',
      body:'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="120"><rect width="900" height="120" fill="#f7e1c4"/><text x="30" y="70" font-size="27" fill="#6f3819">Coffee campaign · layout fixture</text></svg>'}));
    await page.route('**/api/admin/ads**',async route=>{
      const request=route.request(),url=new URL(request.url()),method=request.method();
      const json=body=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
      if(url.pathname.endsWith('/summary'))return json({counts:{ACTIVE:ads.filter(ad=>ad.status==='ACTIVE').length,RESERVED:1},
        measurement:{status:'READY',impressions:10240,clicks:186,as_of:'2026-10-16T05:00:00Z'},evaluated_at:'2026-10-16T05:00:00Z'});
      if(method==='GET')return json({items:ads.filter(ad=>(!url.searchParams.get('placement')||ad.placement===url.searchParams.get('placement'))&&
        (!url.searchParams.get('status')||ad.status===url.searchParams.get('status'))),next_cursor:null});
      const body=request.postDataJSON();operations.push({path:url.pathname,method,body});
      if(url.pathname.endsWith('/preview'))return json({...body,operational_delivery:false});
      const ad=ads.find(ad=>url.pathname.includes(ad.ad_id));
      if(!ad)return route.fulfill({status:404,body:'{}'});
      if(body.version!==ad.version)return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({code:'VERSION_CONFLICT',message:'최신 상태를 확인해 주세요.'})});
      if(url.pathname.endsWith('/stop'))Object.assign(ad,{paused:true,status:'STOPPED',version:ad.version+1});
      else Object.assign(ad,body,{version:ad.version+1});
      return json(ad);
    });
    await page.goto(base+'/login');
    await page.getByLabel('아이디',{exact:true}).fill('browser-reviewer');
    await page.getByLabel('비밀번호',{exact:true}).fill('Browser-test-only-123!');
    await page.getByRole('button',{name:'로그인',exact:true}).click();
    await page.waitForURL('**/admin/ads');
    await page.getByText('10,240',{exact:true}).waitFor();
    if(await page.locator('.ads-metric').count()!==4)throw new Error('Expected four summary cards');
    if(await page.locator('pre').count())throw new Error('Raw JSON must not replace the admin layout');
    const positions=await page.evaluate(()=>({left:document.querySelector('.ads-left').getBoundingClientRect().toJSON(),
      editor:document.querySelector('.ads-editor').getBoundingClientRect().toJSON(),viewport:innerWidth,scroll:document.body.scrollWidth}));
    if(Math.abs(positions.left.y-positions.editor.y)>1||positions.left.right>positions.editor.x)throw new Error('Desktop columns do not follow mockup: '+JSON.stringify(positions));
    if(positions.scroll>positions.viewport)throw new Error('Desktop page overflow');
    const directory=path.resolve(__dirname,'../../artifacts/browser');fs.mkdirSync(directory,{recursive:true});
    await page.screenshot({path:path.join(directory,'ads-admin-desktop.png'),fullPage:true});
    await page.locator('.ads-table tbody tr').first().getByRole('button',{name:'수정'}).click();
    await page.getByLabel('제목',{exact:true}).fill('수정된 카페 광고');
    await page.getByRole('button',{name:'저장',exact:true}).click();
    await page.getByRole('cell',{name:'수정된 카페 광고'}).waitFor();
    await page.locator('.ads-table tbody tr').first().getByRole('button',{name:'게시 중단'}).click();
    await page.locator('.ads-table tbody tr').first().getByText('● 중단',{exact:true}).waitFor();
    await page.locator('.ads-table tbody tr').nth(1).getByRole('button',{name:'수정'}).click();
    await page.getByRole('button',{name:'편집 내용 미리보기'}).click();
    await page.getByText('미리보기를 갱신했습니다.',{exact:true}).waitFor();
    if(!operations.some(operation=>operation.method==='PUT'&&operation.body.version===1))throw new Error('Edit must send expected ad version');
    if(!operations.some(operation=>operation.path.endsWith('/stop')&&operation.body.version===2))throw new Error('Stop must use refreshed version');
    if(!operations.some(operation=>operation.path.endsWith('/preview')))throw new Error('Preview API not used');
    await page.getByRole('button',{name:'모바일',exact:true}).click();
    if(await page.locator('.ads-preview-device').evaluate(element=>element.getBoundingClientRect().width)>390)throw new Error('Mobile preview too wide');
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(directory,'ads-admin-mobile.png'),fullPage:true});
    if(await page.evaluate(()=>document.body.scrollWidth>innerWidth))throw new Error('Mobile page overflow');
    if(errors.length)throw new Error(errors.join(', '));
    console.log('ads-layout-browser-ok: mockup columns/cards/table, edit/stop version, nonoperational preview, responsive widths (HTTP fixture)');
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
