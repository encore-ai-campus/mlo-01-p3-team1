// Isolated UI contract/layout test. All API calls are intercepted; no real registration or approval.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.SMOKE_BASE_URL||'http://127.0.0.1:19073';
const output=path.resolve(__dirname,'../../.local-preview-logs/admin-dashboard-20261019');
const menus=[['/admin/ads','광고 관리'],['/admin/music','음악 관리'],['/admin/music/youtube','YouTube 연결 검수'],['/admin/feedback/exclusions','제외 이력']].map(([path,label])=>({path,label}));
const music=[{track_id:'song-a',track_name:'Sunrise',artists_name:'Norah Jones',review_status:'draft',revision:2,instrumental_review_value:null},{track_id:'song-b',track_name:'Better Together',artists_name:'Jack Johnson',review_status:'approved',revision:3,instrumental_review_value:false}];
const mapping={video_id:'abcdefghijk',video_url:'https://www.youtube.com/watch?v=abcdefghijk',status:'BLOCKED',reason:'EMBED_ERROR_150',native_verified:true,native_duration_seconds:180};
const tracks=music.map((row,i)=>({...row,duration_ms:180000,mappings:i?[]:[{...mapping}]}));
const history=music.map((row,i)=>({...row,event_id:'event-'+i,occurred_at:'2026-10-19T05:32:00Z',event_type:i?'TRACK_EXCLUSION_CANCELLED':'TRACK_EXCLUDED',selected_theme_codes:['CALM'],selected_genre_codes:['JAZZ'],track_theme_codes:['CALM'],track_genre_codes:['JAZZ'],context_snapshot:{options:{weather_influence_mode:'ON',tempo_preference:'auto'},weather_code:'CLEAR',catalog_version:'catalog-1',exclusion_revision:3},source_playlist_id:'playlist-1',related_exclusion_event_id:i?'event-0':null,state:i?'CANCELLED':'EXCLUDED',context_status:'ACTIVE',is_test:true}));
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({headless:true,...process.platform==='win32'?{channel:'msedge'}:{}});
  try{
    const page=await browser.newPage({viewport:{width:1536,height:1024}}),errors=[],operations=[];
    page.setDefaultTimeout(10000);
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/api/**',async route=>{
      const req=route.request(),url=new URL(req.url()),p=url.pathname,method=req.method();
      const json=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
      if(p==='/api/auth/me')return json({authenticated:true,role:'ADMIN',allowed_menus:menus});
      if(p==='/api/recommendation-options')return json({items:[{code:'CALM',label:'잔잔한',type:'theme',enabled:true},{code:'JAZZ',label:'재즈',type:'genre',enabled:true}]});
      if(p==='/api/admin/ads/summary')return json({counts:{ACTIVE:0,RESERVED:0},measurement:{impressions:null,clicks:null},evaluated_at:'2026-10-19T05:32:00Z'});
      if(p==='/api/admin/ads')return json({items:[],next_cursor:null});
      if(p==='/api/admin/music/readiness')return json({registered_count:89740,approved_review_count:89500,common_eligible_count:86485,weather_counts:{CLEAR:42000},catalog_versions:[{version:'catalog-1',ready:true,is_test:true}]});
      if(p==='/api/admin/music/reviews')return json({items:music.filter(row=>!url.searchParams.get('status')||row.review_status===url.searchParams.get('status')),next_cursor:url.searchParams.get('cursor')?null:'cursor-music',as_of:'2026-10-19T05:32:00Z'});
      if(p==='/api/admin/music/imports'){operations.push({p,method});return json({source_ref:'music-source:'+'a'.repeat(64),source_sha256:'a'.repeat(64),normalized_tracks:2});}
      if(p==='/api/admin/music/catalogs'){operations.push({p,body:req.postDataJSON()});return json({catalog_version:'catalog-2',ready:true});}
      if(p.endsWith('/reviews')){const body=req.postDataJSON();operations.push({p,body});return json({track_id:'song-a',revision:3,review_status:body.review_status});}
      if(p==='/api/admin/feedback/exclusions')return json({items:history.filter(row=>!url.searchParams.get('action')||row.event_type===url.searchParams.get('action')),next_cursor:null,as_of:'2026-10-19T05:32:00Z'});
      if(p.startsWith('/api/admin/feedback/exclusions/'))return json(history.find(row=>p.endsWith(row.event_id)));
      if(p==='/api/admin/youtube-review/status')return json({enabled:true,is_test:true});
      if(p==='/api/admin/youtube-review/tracks')return json({items:tracks,total:2,page:1,page_size:30,summary:{total:2,unmapped:1,pending:0,verified:1,blocked:0}});
      if(p.startsWith('/api/admin/youtube-review/')&&method==='POST'){const body=req.postDataJSON();operations.push({p,body});return json({track_id:tracks[0].track_id,revision:3,mappings:tracks[0].mappings});}
      return json({message:'Unexpected test API: '+p},501);
    });
    await page.goto(base+'/admin/music');
    await page.getByRole('heading',{name:'음악 목록',exact:true}).waitFor();
    await page.getByRole('button',{name:'Sunrise 검수',exact:true}).waitFor();
    assert.equal(await page.locator('.admin-metric').count(),4);
    await page.screenshot({path:path.join(output,'music-management.png'),fullPage:true});
    await page.getByLabel('검수 근거',{exact:true}).fill('브라우저 검증용 입력');
    await page.getByRole('button',{name:'승인',exact:true}).last().click();
    await page.waitForTimeout(100);
    const review=operations.find(op=>op.p.endsWith('/song-a/reviews'));
    assert.equal(review.body.expected_revision,2);assert.equal(review.body.reason,'브라우저 검증용 입력');assert.equal(review.body.review_status,'approved');
    await page.getByRole('button',{name:'검수 대기',exact:true}).click();
    await page.getByRole('button',{name:'Better Together 검수',exact:true}).waitFor({state:'detached'});
    assert.equal(await page.locator('.admin-table tbody tr').count(),1);
    await page.getByRole('button',{name:'전체',exact:true}).click();
    await page.getByRole('button',{name:'Better Together 검수',exact:true}).waitFor();
    await page.getByLabel('현재 음악 목록 검색').fill('Jack');
    assert.equal(await page.locator('.admin-table tbody tr').count(),1);
    await page.getByLabel('현재 음악 목록 검색').fill('');
    await page.locator('input[type=file]').setInputFiles({name:'music.csv',mimeType:'text/csv',buffer:Buffer.from('track_id,track_name\nsong-a,Sunrise')});
    await page.getByRole('button',{name:'등록 검사',exact:true}).click();
    await page.getByText('CSV 등록 결과를 확인해 주세요.',{exact:false}).waitFor();
    await page.getByLabel('카탈로그 버전',{exact:true}).fill('catalog-2');
    await page.getByRole('button',{name:'새 카탈로그 발행',exact:true}).click();
    await page.getByText('승인된 곡의 새 카탈로그를 발행했습니다.',{exact:true}).waitFor();
    assert.equal(operations.find(op=>op.p.endsWith('/catalogs')).body.source_sha256,'a'.repeat(64));
    await page.goto(base+'/admin/feedback/exclusions');
    await page.getByRole('button',{name:'Sunrise 이력 보기'}).click();
    await page.getByRole('heading',{name:'당시 추천 조건'}).waitFor();
    assert.equal(await page.locator('.admin-detail-panel').getByRole('button').count(),1);
    await page.screenshot({path:path.join(output,'exclusion-history.png'),fullPage:true});
    await page.getByRole('combobox').filter({has:page.locator('option[value="TRACK_EXCLUSION_CANCELLED"]')}).selectOption('TRACK_EXCLUSION_CANCELLED');
    await page.getByRole('button',{name:'검색',exact:true}).click();
    await page.getByRole('button',{name:'Sunrise 이력 보기'}).waitFor({state:'detached'});
    assert.equal(await page.locator('.admin-table tbody tr').count(),1);
    await page.goto(base+'/admin/music/youtube');
    await page.getByRole('button',{name:'Sunrise 영상 검수'}).waitFor();
    const first=page.locator('.admin-table tbody tr').first();
    await first.getByText('승인',{exact:true}).waitFor();await first.getByText('차단',{exact:true}).waitFor();
    await page.screenshot({path:path.join(output,'youtube-review.png'),fullPage:true});
    await page.getByRole('button',{name:'외부 재생 확인',exact:true}).click();
    await page.getByLabel('외부 YouTube에서 재생을 확인했어요.',{exact:true}).check();
    await page.getByLabel('곡·아티스트·버전이 원곡 정보와 일치함을 확인했어요.',{exact:true}).check();
    await page.getByLabel('외부 영상에서 확인한 전체 길이 (초)',{exact:true}).fill('180');
    await page.getByRole('button',{name:'외부 재생 확인 저장',exact:true}).click();
    await page.waitForTimeout(100);
    const native=operations.find(op=>op.p.endsWith('/native-verify'));assert.equal(native.body.duration_seconds,180);assert.equal(native.body.expected_revision,2);
    for(const route of ['/admin/music','/admin/music/youtube','/admin/feedback/exclusions']){
      await page.setViewportSize({width:390,height:844});await page.goto(base+route);await page.waitForTimeout(200);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'mobile overflow: '+route);
      await page.screenshot({path:path.join(output,route.split('/').pop()+'-mobile.png'),fullPage:true});
    }
    for(const width of [1536,1280,1024,390]){
      await page.setViewportSize({width,height:1024});let baseline;
      for(const route of ['/admin/ads','/admin/music','/admin/music/youtube','/admin/feedback/exclusions']){
        await page.goto(base+route);await page.getByRole('navigation',{name:'관리자 메뉴'}).getByRole('link',{name:'음악 관리',exact:true}).waitFor();
        const geometry=await page.evaluate(()=>{
          const rect=selector=>{const el=document.querySelector(selector);const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};
          return {header:rect('.admin-dashboard-header'),brand:rect('.admin-dashboard-header .brand'),badge:rect('.admin-role'),nav:rect('.admin-dashboard-header nav'),links:[...document.querySelectorAll('.admin-dashboard-header nav a')].map(el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};}),title:{x:rect('main>h1').x,y:rect('main>h1').y,size:getComputedStyle(document.querySelector('main>h1')).fontSize},brandColor:getComputedStyle(document.querySelector('.admin-dashboard-header .brand span')).color};
        });
        if(!baseline)baseline=geometry;else assert.deepEqual(geometry,baseline,`shared admin header/title mismatch at ${width}: ${route}`);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'header overflow: '+route);
        if(width===1536)await page.screenshot({path:path.join(output,route.split('/').pop()+'-header.png'),clip:{x:0,y:0,width,height:230}});
      }
    }
    assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,views:3,mobile_views:3,shared_headers:16,mutations:operations.map(op=>op.p),screenshots:output}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
