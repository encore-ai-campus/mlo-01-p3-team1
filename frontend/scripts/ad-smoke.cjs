// B delivery/measurement fixtures only; no real ad service, accounting or external navigation.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.SMOKE_BROWSER||'msedge'});
  try{
    const context=await browser.newContext({viewport:{width:1536,height:1024}}),page=await context.newPage();
    const requests=[],events=[];let topReady=false,failFirst=true,mode='active',staleAt;
    await context.route('https://example.invalid/**',route=>route.fulfill({body:'Local navigation fixture',contentType:'text/html'}));
    context.on('page',popup=>{if(popup!==page)void popup.waitForLoadState().then(()=>popup.close());});
    await page.route('**/api/ads?*',async route=>{
      const url=new URL(route.request().url()),placement=url.searchParams.get('placement');
      assert.ok(placement==='top'||placement==='bottom');
      if(placement==='bottom')assert.ok(topReady,'Bottom requested before top bootstrap completed');
      requests.push({placement,id:url.searchParams.get('delivery_id')});
      if(mode==='failure')return route.fulfill({status:503,json:{code:'UNAVAILABLE',message:'fixture unavailable'}});
      if(!topReady){await new Promise(resolve=>setTimeout(resolve,150));topReady=true;}
      const evaluated=mode==='stale'?staleAt:Date.now();
      return route.fulfill({json:{ad:mode==='empty'?null:{ad_id:'ad-'+placement,creative_version:1,placement,
        title:'검증용 카페 광고',image_url:'/default-cover.svg',link_url:'https://example.invalid/cafe',delivery_id:'fixture-'+placement},
        evaluated_at:new Date(evaluated).toISOString(),valid_until:new Date(evaluated+3000).toISOString()}});
    });
    await page.route('**/api/ad-events',async route=>{
      const body=route.request().postDataJSON();events.push(body);
      assert.deepEqual(Object.keys(body).sort(),['delivery_id','event_id','event_type','occurred_at']);
      if(body.delivery_id==='fixture-top'&&body.event_type==='VIEWABLE_IMPRESSION'&&failFirst){
        failFirst=false;return route.fulfill({status:503,json:{code:'TEMPORARY',message:'fixture retry'}});
      }
      return route.fulfill({json:{...body,counted:true,result:'COUNTED'}});
    });
    await page.goto('http://127.0.0.1:5173');
    await page.locator('.banner-top a').waitFor();
    await page.locator('.banner-bottom a').waitFor();
    const started=Date.now();
    while(events.filter(e=>e.delivery_id==='fixture-top'&&e.event_type==='VIEWABLE_IMPRESSION').length<2){
      if(Date.now()-started>8000)throw new Error('Expected bounded measurement retry');
      await page.waitForTimeout(100);
    }
    const topEvents=events.filter(e=>e.delivery_id==='fixture-top'&&e.event_type==='VIEWABLE_IMPRESSION');
    assert.deepEqual(topEvents[0],topEvents[1],'Retry must preserve event ID, timestamp and complete body');
    assert.equal(events.filter(e=>e.delivery_id==='fixture-bottom'&&e.event_type==='VIEWABLE_IMPRESSION').length,1);
    assert.ok(requests.some(r=>r.placement==='top'&&r.id==='fixture-top'),'Reconfirmation must reuse delivery');
    assert.equal(await page.locator('.banner-top a').getAttribute('target'),'_blank');
    assert.equal(await page.locator('.banner-top a').getAttribute('rel'),'noopener noreferrer');
    await page.locator('.banner-top a').click();
    await page.locator('.banner-top a').click();
    assert.equal(events.filter(e=>e.event_type==='CLICK').length,1,'Same delivery click reports only once');
    const beforeGuide=events.length;
    await page.getByRole('button',{name:'사용 안내',exact:true}).click();
    await page.getByRole('dialog').waitFor();
    assert.equal(await page.locator('.banner a').count(),0,'Guide must suspend visible ads');
    await page.waitForTimeout(1200);
    assert.equal(events.length,beforeGuide,'Guide must not create measurement events');
    await page.keyboard.press('Escape');
    await page.locator('.banner-top a').waitFor();
    mode='failure';const stopped=Date.now();
    await page.locator('.banner-top a').waitFor({state:'hidden',timeout:3500});
    assert.ok(Date.now()-stopped<3100,'Failed confirmation must hide within 3 seconds');
    mode='empty';
    await page.locator('.banner-top .ad-empty').filter({hasText:/^광고$/}).waitFor();
    mode='stale';staleAt=Date.now()-10000;
    await page.waitForTimeout(1300);
    assert.equal(await page.locator('.banner a').count(),0,'Expired cached response must not restore an ad');
    console.log(JSON.stringify({fixtureOnly:true,checks:['link_url and nested delivery_id','top bootstrap before bottom',
      'delivery reconfirmation','one-second visible impression','same complete body on retry','per-delivery click deduplication',
      'guide isolation','failure hides within 3s','ad:null differs from failure','expired response rejected'],eventRequests:events.length}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
