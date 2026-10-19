// Actual Banner component, common API and browser; only advertisement HTTP is mocked.
// The fixture enforces the same proof header as the advertisement API unit tests.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base=process.env.SMOKE_BASE_URL;
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'msedge'}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const issues={top:0,bottom:0},rechecks=[],events=[],failures=[];
    let failRecheck=false,clickFailures=2,rotate=false,active='top-1';
    await page.route('**/api/ads?*',async route=>{
      const url=new URL(route.request().url()),placement=url.searchParams.get('placement');
      const previous=url.searchParams.get('delivery_id'),proof=route.request().headers()['x-ad-delivery-token'];
      const json=(status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
      if(previous){
        rechecks.push({placement,previous,proof});
        if(proof!=='proof-'+previous){failures.push('missing_recheck_proof');return json(422,{code:'VALIDATION_ERROR'});}
        if(failRecheck&&placement==='top')return json(503,{code:'TEMPORARY_UNAVAILABLE'});
        if(rotate&&placement==='top'){rotate=false;return json(200,{ad:null});}
      }else issues[placement]++;
      const id=previous||placement+'-'+issues[placement];
      if(placement==='top')active=id;
      const now=Date.now();
      return json(200,{ad:{ad_id:'fixture',delivery_id:id,delivery_token:'proof-'+id,
        title:'Fixture '+id,link_url:'https://example.com/',
        image_url:'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="red"/></svg>'},
        evaluated_at:new Date(now).toISOString(),valid_until:new Date(now+3000).toISOString()});
    });
    await page.route('**/api/ad-events',async route=>{
      const body=route.request().postDataJSON(),proof=route.request().headers()['x-ad-delivery-token'];
      events.push({body,proof});
      assert.equal(proof,'proof-'+body.delivery_id);
      assert.equal('delivery_token' in body,false);
      if(body.event_type==='CLICK'&&clickFailures>0){clickFailures--;
        return route.fulfill({status:503,contentType:'application/json',body:'{"code":"TEMPORARY_UNAVAILABLE"}'});}
      return route.fulfill({status:200,contentType:'application/json',body:'{"counted":true}'});
    });
    await page.goto(base+'/');
    await page.locator('.banner-top img').waitFor();
    await page.waitForFunction(()=>document.querySelector('.banner-top img')?.complete);
    await page.evaluate(()=>{
      const anchor=document.querySelector('.banner-top a');
      anchor.addEventListener('click',event=>event.preventDefault(),{once:true});anchor.click();
    });
    // Replace the displayed delivery while a legitimate old event is awaiting retry.
    rotate=true;
    await page.waitForFunction(()=>document.querySelector('.banner-top span')?.textContent.includes('top-2'));
    await page.waitForTimeout(1800);
    const clicks=events.filter(row=>row.body.event_type==='CLICK');
    assert.equal(clicks.length,3);assert.deepEqual(clicks[0],clicks[1]);assert.deepEqual(clicks[0],clicks[2]);
    assert.equal(clicks[0].proof,'proof-top-1');
    assert.equal(active,'top-2');
    const originalIssues=issues.top;
    await page.evaluate(()=>{
      window.__fixtureHidden=true;
      Object.defineProperty(document,'hidden',{configurable:true,get:()=>window.__fixtureHidden});
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.locator('.banner-top img').waitFor({state:'detached'});
    await page.evaluate(()=>{window.__fixtureHidden=false;document.dispatchEvent(new Event('visibilitychange'));});
    await page.locator('.banner-top img').waitFor();
    assert.equal(issues.top,originalIssues);
    assert.equal(rechecks.filter(row=>row.placement==='top').at(-1).previous,'top-2');
    failRecheck=true;
    await page.locator('.banner-top img').waitFor({state:'detached'});
    failRecheck=false;
    await page.locator('.banner-top img').waitFor();
    assert.equal(issues.top,originalIssues);
    await page.waitForTimeout(1600);
    const counted=events.filter(row=>row.body.event_type==='VIEWABLE_IMPRESSION'&&row.body.delivery_id==='top-2');
    assert.equal(counted.length,1);
    assert.equal(failures.length,0);
    console.log('ads-banner-browser-ok: proof headers, old-event retry identity/token, same delivery after visibility/network recovery, one impression');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
