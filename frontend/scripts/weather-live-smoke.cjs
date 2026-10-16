// Running app -> actual KMA cache -> browser. No fixture weather or playlist writes.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.SMOKE_BASE_URL||'http://127.0.0.1:19073';
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try{
    const page=await browser.newPage({viewport:{width:1536,height:1000}});
    const regions=await (await page.request.get(base+'/api/regions/tree')).json();
    const selected=regions.items.find(row=>row.region_id==='region:1211075700');
    if(!selected)throw new Error('Mokpo region missing');
    await page.goto(base+'/');
    await page.getByRole('button',{name:/지역을 직접 선택하기/}).click();
    await page.getByLabel('시·도',{exact:true}).selectOption(selected.province);
    await page.getByLabel('시·군·구',{exact:true}).selectOption(selected.district);
    const response=page.waitForResponse(r=>{
      const url=new URL(r.url());
      return url.pathname==='/api/weather'&&url.searchParams.get('region_id')===selected.region_id;
    });
    await page.getByLabel('읍·면·동',{exact:true}).selectOption(selected.region_id);
    await page.getByRole('button',{name:'이 지역으로 설정',exact:true}).click();
    const data=await (await response).json();
    if(data.is_test!==false||data.source!=='KMA_API_HUB'||data.bundle_version==='demo-weather-v1')throw new Error('Synthetic weather received');
    if(data.current?.status!=='valid'||!data.current?.observed_at)throw new Error('No valid observation');
    const expected=data.current.pty===0?({1:'맑음',3:'구름많음',4:'흐림'}[data.current.sky]):'비';
    await page.locator('.weather-current').filter({hasText:expected}).waitFor();
    const text=await page.locator('.weather-current').innerText();
    if(!text.includes(String(data.current.temperature)))throw new Error('Temperature differs from actual response');
    await page.locator('.demo-note').filter({hasText:'기상청 날씨'}).waitFor();
    const timestamps=await page.locator('.region-section small').first().innerText();
    if(!timestamps.includes('관측')||!timestamps.includes('예보')||!timestamps.includes('기상청'))throw new Error('Source timestamps missing');
    const folder=path.resolve('artifacts/local-demo-edfcd850');
    await page.screenshot({path:path.join(folder,'live-weather-mokpo.png'),fullPage:true});
    const report={region_id:selected.region_id,is_test:data.is_test,source:data.source,
      text,timestamps,observed_at:data.current.observed_at,forecast_issued_at:data.forecast_issued_at,
      recommendation_ready:data.recommendation_ready};
    fs.writeFileSync(path.join(folder,'live-weather-browser.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report));
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
