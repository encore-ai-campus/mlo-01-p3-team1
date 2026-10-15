import {useEffect,useRef,useState} from 'react';
import {api,ApiError,key} from './api';
type Delivery={ad:null|{ad_id:string;title:string;image_url:string;link_url:string;delivery_id:string};evaluated_at:string;valid_until:string};
type Report={body:{delivery_id:string;event_id:string;event_type:string;occurred_at:string};attempts:number;next:number;created:number;done:boolean;inflight:boolean};
// Transport defaults for this draft; B/INF must confirm production retry settings.
const maxAttempts=3,retryDelayMs=1000;
export function Banner({placement,blocked,enabled=true,onReady}:{placement:'top'|'bottom';blocked:boolean;enabled?:boolean;onReady?:()=>void}){
  const [delivery,setDelivery]=useState<Delivery|null>(null);
  const [empty,setEmpty]=useState(false);
  const root=useRef<HTMLElement>(null),last=useRef<Delivery|null>(null),deadline=useRef(0),visible=useRef(false),loaded=useRef(false);
  const latestEvaluation=useRef(0),ready=useRef(onReady);ready.current=onReady;
  const blockedRef=useRef(blocked);blockedRef.current=blocked;
  const reports=useRef(new Map<string,Report>());
  async function transmit(report:Report){
    if(report.done||report.inflight||performance.now()<report.next)return;
    if(performance.now()-report.created>300000||report.attempts>=maxAttempts){report.done=true;return;}
    report.inflight=true;report.attempts++;
    try{await api('/api/ad-events','POST',report.body);report.done=true;}
    catch(error){
      if(error instanceof ApiError&&error.status<500)report.done=true;
      else report.next=performance.now()+retryDelayMs*report.attempts;
    }finally{report.inflight=false;}
  }
  function report(type:string){
    const current=last.current;
    if(!current?.ad||blockedRef.current||document.hidden||performance.now()>=deadline.current)return;
    const identity=current.ad.delivery_id+':'+type;
    let record=reports.current.get(identity);
    if(!record){
      if(reports.current.size>=128)reports.current.delete(reports.current.keys().next().value!);
      record={body:{delivery_id:current.ad.delivery_id,event_id:key(),event_type:type,occurred_at:new Date().toISOString()},
        attempts:0,next:0,created:performance.now(),done:false,inflight:false};
      reports.current.set(identity,record);
    }
    void transmit(record);
  }
  useEffect(()=>{
    let stopped=false,inflight=false;const abort=new AbortController();
    const hide=(noAd=false)=>{last.current=null;deadline.current=0;setDelivery(null);loaded.current=false;setEmpty(noAd);};
    async function refresh(){
      if(inflight)return;
      if(!enabled||document.hidden||blockedRef.current){hide();return;}
      inflight=true;const started=performance.now();
      try{
        const previous=last.current?.ad;
        const data=await api<Delivery>('/api/ads?placement='+placement+(previous?'&delivery_id='+encodeURIComponent(previous.delivery_id):''),'GET',undefined,undefined,abort.signal);
        if(stopped)return;
        ready.current?.();
        if(!data.ad){hide(true);return;}
        const evaluated=Date.parse(data.evaluated_at),valid=Date.parse(data.valid_until);
        const remaining=Math.min(3000,valid-evaluated,valid-Date.now())-(performance.now()-started);
        if(!Number.isFinite(remaining)||remaining<=0||evaluated<latestEvaluation.current||
          new URL(data.ad.link_url).protocol!=='https:'){hide();return;}
        const expires=performance.now()+remaining;
        if(evaluated===latestEvaluation.current){
          if(!previous||previous.delivery_id!==data.ad.delivery_id){hide();return;}
          deadline.current=Math.min(deadline.current,expires);
        }else{
          latestEvaluation.current=evaluated;deadline.current=expires;
        }
        if(previous?.delivery_id!==data.ad.delivery_id)loaded.current=false;
        last.current=data;setDelivery(data);
      }catch{if(!stopped)hide();}finally{inflight=false;}
    }
    hide();void refresh();
    const poll=setInterval(()=>void refresh(),1000);
    const expiry=setInterval(()=>{if(last.current&&performance.now()>=deadline.current)hide();},100);
    const change=()=>{hide();if(!document.hidden)void refresh();};document.addEventListener('visibilitychange',change);
    return()=>{stopped=true;abort.abort();clearInterval(poll);clearInterval(expiry);document.removeEventListener('visibilitychange',change);};
  },[placement,blocked,enabled]);
  useEffect(()=>{
    const observer=new IntersectionObserver(entries=>{visible.current=entries[0].intersectionRatio>=.5;},{threshold:[0,.5,1]});
    if(root.current)observer.observe(root.current);
    let since:number|null=null;
    const timer=setInterval(()=>{
      if(!blockedRef.current&&!document.hidden&&visible.current&&loaded.current&&last.current?.ad&&performance.now()<deadline.current){
        if(since===null)since=performance.now();
        if(performance.now()-since>=1000)report('VIEWABLE_IMPRESSION');
      }else since=null;
      for(const record of reports.current.values())if(!record.done)void transmit(record);
    },100);
    return()=>{observer.disconnect();clearInterval(timer);};
  },[delivery?.ad?.delivery_id,blocked]);
  return <aside className={'banner banner-'+placement} ref={root} aria-label={(placement==='top'?'상단':'하단')+' 광고'}>
    {!blocked&&delivery?.ad?<a href={delivery.ad.link_url} target="_blank" rel="noopener noreferrer" onClick={()=>report('CLICK')}>
      <img src={delivery.ad.image_url} alt={delivery.ad.title} onLoad={()=>{loaded.current=true;}}
        onError={()=>{last.current=null;loaded.current=false;setDelivery(null);}}/>
      <span>광고 · {delivery.ad.title}</span>
    </a>:<span className="ad-empty">{empty?'광고':'광고 연결 대기'}</span>}
  </aside>;
}
