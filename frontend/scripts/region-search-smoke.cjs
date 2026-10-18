// UI contract test with fixed region/weather responses; no external services or real API writes.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
const base=process.env.SMOKE_BASE_URL||'http://127.0.0.1:19136';
const rows=[
 {region_id:'region:1120065000',name:'서울특별시 성동구 성수1가제1동',province:'서울특별시',district:'성동구',locality:'성수1가제1동'},
 {region_id:'region:1120066000',name:'서울특별시 성동구 성수1가제2동',province:'서울특별시',district:'성동구',locality:'성수1가제2동'},
 {region_id:'region:other',name:'경기도 가평군 성수동',province:'경기도',district:'가평군',locality:'성수동'},
];
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 const output=path.resolve(__dirname,'../../artifacts/region-search');fs.mkdirSync(output,{recursive:true});
 try{
  const context=await browser.newContext({viewport:{width:1536,height:1000}}),page=await context.newPage();
  let failRegions=false,posts=0,body=null,errors=[];const weatherRequests=[];
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/api/**',async route=>{
   const req=route.request(),url=new URL(req.url());let data={};let status=200;
   if(req.method()!=='GET')posts++;
   if(url.pathname==='/api/auth/me')data={role:'GUEST'};
   else if(url.pathname==='/api/recommendation-options')data={option_version:'test',items:[]};
   else if(url.pathname==='/api/regions/tree'){data=failRegions?{message:'Unavailable'}:{items:rows};status=failRegions?503:200;}
   else if(url.pathname==='/api/c-demo/context')data={csrf_token:'test',regions:rows};
   else if(url.pathname==='/api/weather'){
    weatherRequests.push(url.searchParams.get('region_id'));const now=new Date().toISOString();
    data={region_name:rows.find(r=>r.region_id===url.searchParams.get('region_id'))?.name,as_of:now,valid_until:new Date(Date.now()+14400000).toISOString(),is_test:true,recommendation_ready:true,current:{pty:0,sky:1,temperature:23,status:'valid'},segments:[{pty:0,sky:1,status:'valid',start_at:now,end_at:new Date(Date.now()+14400000).toISOString()}]};
   }else if(url.pathname==='/api/ads'){
    const top=url.searchParams.get('placement')==='top';data={ad:{ad_id:'test',title:'광고 예시',image_url:top?'/ad-examples/cafe-supplies-top-1536x120.jpg':'/ad-examples/cafe-plants-bottom-1536x104.jpg',link_url:'https://example.com',delivery_id:'test-'+(top?'top':'bottom')},evaluated_at:new Date().toISOString(),valid_until:new Date(Date.now()+3000).toISOString()};
   }else if(url.pathname==='/api/recommendation-jobs'&&req.method()==='POST'){body=req.postDataJSON();data={job_id:'test-job'};}
   else if(url.pathname==='/api/recommendation-jobs/test-job')data={status:'SUCCEEDED',playlist_id:'test-playlist'};
   else if(url.pathname==='/api/playlists/test-playlist')data={playlist_id:'test-playlist',family_id:'test-family',items:[{track_id:'test-track',track_name:'유지할 기존 곡',artists_name:'테스트 아티스트',cover_image_url:null}],generation_method:'RULE_BASED',summary:'화면 시험',context:{options:body,excluded_track_ids:[]},approval_revision:0,approved_playlist_id:null};
   else if(url.pathname==='/api/playlist-families/test-family/exclusions')data={family_id:'test-family',revision:0,excluded_track_ids:[],items:[]};
   else if(url.pathname.includes('feedback'))data={source_playlist_id:'test-playlist',track_reactions:[{track_id:'test-track',reaction:null,revision:0}],playlist_rating:{rating:null,revision:0}};
   await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto(base);const search=page.getByRole('combobox',{name:'지역 검색'});
  await search.waitFor();await page.getByRole('button',{name:/지역을 직접 선택하기/}).waitFor();
  await page.waitForFunction(()=>!document.querySelector('.region-direct')?.disabled);
  assert(await search.isVisible());assert.match(await page.locator('.weather-current').innerText(),/지역 미설정/);
  assert(await page.getByRole('radio',{name:'반영하지 않음'}).isChecked());
  await page.screenshot({path:path.join(output,'initial-desktop.png'),fullPage:true});
  await search.fill('서울 성수');assert.equal(await page.getByRole('option').count(),2);
  await page.screenshot({path:path.join(output,'search-desktop.png'),fullPage:true});
  await search.press('ArrowDown');await search.press('Enter');
  await page.waitForFunction(()=>document.querySelector('.weather-current')?.textContent.includes('23°C'));
  assert.equal(weatherRequests.at(-1),rows[0].region_id);
  await page.getByRole('radio',{name:'반영하지 않음'}).check();
  await page.getByRole('button',{name:'선곡표 받기',exact:true}).click();
  await page.getByText('유지할 기존 곡',{exact:true}).first().waitFor();
  const originalPosts=posts;
  await search.fill('없는동');await page.getByText(/일치하는 지역이 없어요/).waitFor();await search.press('Enter');
  assert.equal(weatherRequests.at(-1),rows[0].region_id);await search.press('Escape');
  assert.equal(await search.getAttribute('aria-expanded'),'false');
  await page.getByRole('button',{name:/지역을 직접 선택하기/}).click();
  await page.getByLabel('시·도',{exact:true}).selectOption('경기도');
  assert.equal(await page.getByLabel('시·군·구',{exact:true}).inputValue(),'');
  assert(await page.getByRole('button',{name:'이 지역으로 설정'}).isDisabled());
  await page.keyboard.press('Escape');assert.match(await page.locator('.region-selected').innerText(),/서울특별시/);
  await page.getByRole('button',{name:/지역을 직접 선택하기/}).click();
  assert.equal(await page.getByLabel('시·도',{exact:true}).inputValue(),'서울특별시');
  await page.getByLabel('읍·면·동',{exact:true}).selectOption(rows[1].region_id);
  await page.getByRole('button',{name:'이 지역으로 설정'}).click();
  await page.waitForFunction(()=>document.querySelector('.region-selected')?.textContent.includes('성수1가제2동'));
  assert(await page.getByRole('radio',{name:'반영하지 않음'}).isChecked());
  assert.equal(await page.locator('.tracks li').count(),1);assert.equal(posts,originalPosts);
  assert.match(await page.locator('.playlist-status').innerText(),/변경 사항 미반영/);
  await page.reload();await page.locator('.region-selected').waitFor();assert.match(await page.locator('.region-selected').innerText(),/성수1가제2동/);
  await page.setViewportSize({width:390,height:844});await search.fill('성수');
  assert.equal(await page.getByRole('option').count(),3);
  await page.getByRole('option').filter({hasText:'경기도'}).click();
  await page.getByRole('button',{name:/지역을 직접 선택하기/}).click();
  await page.screenshot({path:path.join(output,'direct-mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.getByRole('button',{name:'검색으로 찾기'}).click();assert(await search.evaluate(el=>document.activeElement===el));
  await page.evaluate(()=>localStorage.removeItem('cafe-region'));await page.reload();
  await page.waitForFunction(()=>!document.querySelector('.region-direct')?.disabled);
  await page.screenshot({path:path.join(output,'initial-mobile.png'),fullPage:true});
  failRegions=true;await page.reload();await page.getByText('지역 목록을 불러오지 못했어요.').waitFor();
  assert(await page.getByRole('button',{name:'선곡표 받기',exact:true}).isEnabled());
  failRegions=false;await page.getByRole('button',{name:'지역 목록 다시 확인'}).click();
  await page.waitForFunction(()=>!document.querySelector('.region-direct')?.disabled);
  assert.deepEqual(errors,[]);console.log('PASS: inline search, keyboard, no matches, draft/cancel/apply, OFF preserved, playlist preserved/no generation, restoration, mobile, region retry/OFF availability. Fixed API responses only.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
