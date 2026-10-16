// B API fixtures verify C UI against the checked-in FeedbackRead/Put contract.
const { chromium }=require('playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.SMOKE_BROWSER||'msedge'});
  try{
    const context=await browser.newContext(),page=await context.newPage();
    const states=new Map(),cached=new Map();let failRating=true,failedKey=null,failRead=true;
    async function state(id){
      if(!states.has(id)){
        const r=await context.request.get(`http://127.0.0.1:5173/api/playlists/${id}`);const p=await r.json();
        states.set(id,{source_playlist_id:id,track_reactions:p.items.map(t=>({track_id:t.track_id,reaction:null,revision:0})),playlist_rating:{rating:null,revision:0}});
      }
      return states.get(id);
    }
    await page.route(/\/api\/playlists\/[^/]+\/(feedback|rating|tracks\/[^/]+\/reaction)$/,async route=>{
      const req=route.request(),url=new URL(req.url()),parts=url.pathname.split('/'),id=parts[3],s=await state(id);
      if(req.method()==='GET'){
        if(failRead){failRead=false;return route.fulfill({status:503,json:{code:'TEMPORARY',message:'평가 연결을 다시 확인해 주세요.'}});}
        return route.fulfill({json:s});
      }
      const body=req.postDataJSON(),isRating=parts[4]==='rating',key=req.headers()['idempotency-key'];
      if(isRating&&failRating){failRating=false;failedKey=key;return route.fulfill({status:503,json:{code:'TEMPORARY',message:'평가 저장을 다시 시도해 주세요.',details:{},request_id:'test'}});}
      if(isRating&&failedKey&&key!==failedKey)throw new Error('Transport retry changed Idempotency-Key');
      if(isRating&&failedKey===key)failedKey=null;
      if(cached.has(key))return route.fulfill({json:cached.get(key)});
      const target=isRating?s.playlist_rating:s.track_reactions.find(t=>t.track_id===parts[5]);
      const field=isRating?'rating':'reaction';
      if(body.expected_revision!==target.revision)return route.fulfill({status:409,json:{code:'FEEDBACK_REVISION_CONFLICT',message:'최신 평가를 확인해 주세요.',details:{},request_id:'test'}});
      if(target[field]!==body[field]){target[field]=body[field];target.revision++;}
      const response={source_playlist_id:id,target_kind:isRating?'PLAYLIST_RATING':'TRACK_REACTION',track_id:isRating?null:parts[5],value:target[field],revision:target.revision,updated_at:new Date().toISOString(),event_id:'test-event'};
      cached.set(key,response);return route.fulfill({json:response});
    });
    await page.goto('http://127.0.0.1:5173');
    await page.getByLabel('우리 동네').selectOption('demo-region');
    await page.getByRole('button',{name:'선곡표 받기',exact:true}).click();
    await page.getByText('45곡',{exact:true}).waitFor();
    await page.getByRole('button',{name:'평가 다시 확인',exact:true}).click();
    const like=page.locator('.tracks li').first().getByRole('button',{name:/ 좋아요$/});
    await like.click();await page.waitForFunction(()=>document.querySelector('.tracks li button[aria-label$=" 좋아요"]').getAttribute('aria-pressed')==='true');
    await like.click();await page.waitForFunction(()=>document.querySelector('.tracks li button[aria-label$=" 좋아요"]').getAttribute('aria-pressed')==='false');
    const dislike=page.locator('.tracks li').first().getByRole('button',{name:/ 싫어요$/});
    await dislike.click();await page.waitForFunction(()=>document.querySelector('.tracks li button[aria-label$=" 싫어요"]').getAttribute('aria-pressed')==='true');
    await like.click();await page.waitForFunction(()=>document.querySelector('.tracks li button[aria-label$=" 싫어요"]').getAttribute('aria-pressed')==='false');
    await like.click();await page.waitForFunction(()=>document.querySelector('.tracks li button[aria-label$=" 좋아요"]').getAttribute('aria-pressed')==='false');
    await page.getByRole('radio',{name:'5점',exact:true}).click();
    await page.getByText('평가 저장을 다시 시도해 주세요.',{exact:false}).waitFor();
    await like.click();
    await page.waitForFunction(()=>document.querySelector('.tracks li button[aria-label$=" 좋아요"]').getAttribute('aria-pressed')==='true');
    await page.getByRole('button',{name:'평가 다시 저장'}).waitFor();
    if(await page.getByRole('button',{name:'이 선곡표 승인'}).isDisabled())throw new Error('Rating save failure blocked approval');
    await page.getByRole('button',{name:'평가 다시 저장'}).click();
    await page.waitForFunction(()=>document.querySelector('[aria-label="5점"]').getAttribute('aria-checked')==='true');
    await page.getByRole('button',{name:'평가 취소',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('[aria-label="5점"]').getAttribute('aria-checked')==='false');
    await page.getByRole('radio',{name:'1점',exact:true}).focus();
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction(()=>document.querySelector('[aria-label="2점"]').getAttribute('aria-checked')==='true');
    console.log(JSON.stringify({fixtureOnly:true,checks:['FeedbackRead reaction/rating mapping','initial read retry','reaction toggle clear and opposite switch','rating failure leaves approval available','other target success preserves failed retry','same-key retry','rating clear','keyboard rating radio selection']}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
