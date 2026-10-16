import {useRef} from 'react';
import {Icon,WeatherIcon} from './Icons';
export type Weather={region_name:string;as_of:string;valid_until:string;is_test:boolean;
  current?:{pty:number;sky:number|null;temperature?:number};
  segments:{pty:number;sky:number;status:string;start_at:string;end_at:string}[]};
export function weatherLabel(pty?:number,sky?:number|null){
  if(pty===undefined)return '확인 불가';
  if(pty===0)return sky===1?'맑음':sky===3?'구름많음':sky===4?'흐림':'강수 없음';
  return ['강수 없음','비','비·눈','눈','소나기','빗방울','빗방울·눈날림','눈날림'][pty]||'확인 불가';
}
const clock=(date:Date)=>date.toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',hour12:false});
export function WeatherPanel({region,regions,onRegion,locked,weather,error,onRetry,widget,onGuide,onHideWidget}:{
  region:string;regions:{region_id:string;name:string}[];onRegion:(id:string)=>void;locked:boolean;
  weather:Weather|null;error:string;onRetry:()=>void;widget:boolean;onGuide:()=>void;onHideWidget:()=>void;
}){
  const select=useRef<HTMLSelectElement>(null);
  const name=regions.find(r=>r.region_id===region)?.name.split(' · ')[0];
  const current=weather?.current;
  return <section className="weather-panel" aria-label="지역과 날씨" data-guide="region">
    <div className="region-section"><WeatherIcon pty={current?.pty} sky={current?.sky}/><div>
      <h1>{name?`${name}의 날씨에 맞춘 선곡`:'우리 동네의 날씨에 맞춘 선곡'}</h1>
      <div className="region-controls"><Icon name="pin"/><label className="sr-only" htmlFor="region">우리 동네</label><select ref={select} id="region" value={region} disabled={locked} onChange={e=>onRegion(e.target.value)}><option value="">지역을 선택해 주세요</option>{regions.map(r=><option key={r.region_id} value={r.region_id}>{r.name}</option>)}</select><button disabled={locked} onClick={()=>{select.current?.focus();try{select.current?.showPicker();}catch{/* Native select remains usable. */}}}>{region?'지역 변경':'지역 설정'}</button></div>
      <small>{weather?`갱신 ${clock(new Date(weather.as_of))}${weather.is_test?' · 검증 자료':''}`:'동 단위 지역을 선택해 주세요.'}</small>
      {error&&<small className="weather-error" role="alert">{error} <button onClick={onRetry} disabled={locked}>날씨 다시 확인</button></small>}
    </div></div>
    <div className="weather-current"><strong>{weatherLabel(current?.pty,current?.sky)}{current?.temperature!==undefined?` · ${current.temperature}°C`:''}</strong><span>앞으로 3시간</span></div>
    <div className="forecast" aria-label="시간대별 예보">{[0,1,2,3].map(hour=>{
      const at=weather?new Date(Date.parse(weather.as_of)+hour*3600000):null;
      const row=at?weather?.segments.find(s=>s.status==='valid'&&Date.parse(s.start_at)<=+at&&Date.parse(s.end_at)>+at):undefined;
      return <div className="forecast-hour" key={hour}><time dateTime={at?.toISOString()}>{at?clock(at):`${hour}시간 후`}</time><WeatherIcon pty={row?.pty} sky={row?.sky}/><span>{weatherLabel(row?.pty,row?.sky)}</span></div>;
    })}</div>
    {widget&&<div className="guide-widget"><div className="guide-bubble"><strong>사용 안내</strong><p>지역과 취향을 선택하면<br/>날씨에 맞춰 선곡해 드려요.</p><button onClick={onGuide}>안내 보기</button></div><img src="/penguin-guide-first.png" alt="펭귄 사용 안내"/><button className="widget-close" aria-label="안내 위젯 닫기" onClick={onHideWidget}>×</button></div>}
  </section>;
}
