// Isolated browser contract check; no real IdP, account issuance or Kibana calls.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.SMOKE_BASE_URL||'http://127.0.0.1:19175';
const allMenus=[
  {path:'/admin/ads',label:'광고 관리'},
  {path:'/admin/music',label:'음악 관리'},
  {path:'/admin/music/youtube',label:'YouTube 연결 검수'},
  {path:'/admin/feedback/exclusions',label:'제외 이력'},
  {path:'/api/admin/operations/kibana',label:'운영 대시보드'},
];
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'msedge'}:{})});
  try{
    const page=await browser.newPage();
    let authenticated=false,localLogin=false,adminRole='SUPER_ADMIN',operationsConfigured=true,logsConfigured=true;
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('https://identity.example.org/**',route=>route.fulfill({body:'Identity provider logout reached'}));
    await page.route('https://ops.example.org/**',route=>route.fulfill({body:'Kibana destination reached'}));
    await page.route('https://logs.example.org/**',route=>route.fulfill({body:'Log dashboard destination reached'}));
    await page.route('**/api/**',route=>{
      const url=new URL(route.request().url());
      const json=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
      if(url.pathname==='/api/auth/me'){
        const allowed=authenticated&&adminRole!=='ADS_ADMIN';
        const menus=adminRole==='ADS_ADMIN'?allMenus.filter(item=>item.path==='/admin/ads'):
          adminRole==='OPS_ADMIN'?allMenus.filter(item=>item.path!=='/admin/ads'):allMenus;
        return json({authenticated,role:authenticated?'ADMIN':null,admin_role:authenticated?adminRole:null,
          allowed_menus:authenticated?menus:[],sso_enabled:true,local_login_enabled:localLogin,csrf_token:'test-only-csrf',
          operations_dashboard:{allowed,configured:operationsConfigured,path:allowed&&operationsConfigured?'/api/admin/operations/dashboard':null},
          log_dashboard:{allowed,configured:logsConfigured,path:allowed&&logsConfigured?'/api/admin/operations/logs':null}});
      }
      if(url.pathname==='/api/admin/operations/dashboard')return route.fulfill({status:302,headers:{location:'https://ops.example.org/dashboard'}});
      if(url.pathname==='/api/admin/operations/logs')return route.fulfill({status:302,headers:{location:'https://logs.example.org/dashboard'}});
      if(url.pathname==='/api/auth/logout')return json({authenticated:false,logout_url:'https://identity.example.org/logout'});
      if(url.pathname==='/api/recommendation-options')return json({items:[]});
      if(url.pathname==='/api/admin/music/reviews')return json({items:[],next_cursor:null});
      if(url.pathname==='/api/admin/music/readiness')return json({registered_count:0,approved_review_count:0,
        common_eligible_count:0,weather_counts:{},catalog_versions:[]});
      return route.fulfill({status:404,contentType:'application/json',body:'{"message":"Unexpected test API"}'});
    });
    await page.goto(base+'/login');
    await page.getByRole('link',{name:'관리자 통합 로그인'}).waitFor();
    assert.equal(await page.locator('#username').count(),0,'SSO-only mode must hide the password form');
    assert.equal(await page.getByRole('link',{name:'관리자 통합 로그인'}).getAttribute('href'),'/api/auth/sso/login');
    localLogin=true;
    await page.reload();
    await page.locator('#username').waitFor();
    authenticated=true;
    const operationsButton=page.getByRole('button',{name:/^운영 대시보드/});
    const logsButton=page.getByRole('button',{name:/^사용자 행동 분석/});
    for(const role of ['SUPER_ADMIN','OPS_ADMIN']){
      adminRole=role;
      for(const [operations,logs] of [[false,false],[true,false],[false,true],[true,true]]){
        operationsConfigured=operations;logsConfigured=logs;
        await page.goto(base+'/admin/music');
        await operationsButton.waitFor();await logsButton.waitFor();
        assert.equal(await operationsButton.isEnabled(),operations);
        assert.equal(await logsButton.isEnabled(),logs);
        for(const [button,ready] of [[operationsButton,operations],[logsButton,logs]]){
          if(!ready)assert.match(await button.innerText(),/연결 준비 중/);
          await page.setViewportSize({width:390,height:844});
          assert.equal(await button.evaluate(element=>{
            const box=element.getBoundingClientRect();
            return box.left>=0&&box.right<=window.innerWidth;
          }),true,'Dashboard button must remain inside a narrow viewport');
        }
      }
      await operationsButton.click();await page.waitForURL('https://ops.example.org/dashboard');
      await page.goto(base+'/admin/music');await logsButton.waitFor();
      await logsButton.click();await page.waitForURL('https://logs.example.org/dashboard');
    }
    adminRole='ADS_ADMIN';
    await page.goto(base+'/admin/music');
    await page.getByRole('button',{name:'로그아웃',exact:true}).waitFor();
    assert.equal(await operationsButton.count(),0,'ADS_ADMIN must not see the operations button');
    assert.equal(await logsButton.count(),0,'ADS_ADMIN must not see the logs button');
    await page.getByRole('button',{name:'로그아웃',exact:true}).click();
    await page.waitForURL('https://identity.example.org/logout');
    assert.deepEqual(errors,[]);
    console.log('PASS: SSO login/local form; two independent dashboard states and destinations for SUPER_ADMIN/OPS_ADMIN; 390px viewport; ADS_ADMIN hides both; IdP logout; no page errors');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
