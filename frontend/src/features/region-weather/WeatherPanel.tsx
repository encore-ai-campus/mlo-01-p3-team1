import {WeatherIcon} from '../../components/Icons';
import {RegionPicker,type RegionOption} from './RegionPicker';
export type Weather={region_name:string;as_of:string;valid_until:string;is_test:boolean;
  source?:string;collected_at?:string;forecast_issued_at?:string;
  weather_code?:string;bundle_version?:string;recommendation_ready?:boolean;recommendation_error?:string;
  current?:{pty:number;sky:number|null;temperature?:number;observed_at?:string;status?:string};
  segments:{pty:number;sky:number;status:string;start_at:string;end_at:string}[]};
export function weatherLabel(pty?:number,sky?:number|null){
  if(pty===undefined)return '확인 불가';
  if(pty===0)return sky===1?'맑음':sky===3?'구름많음':sky===4?'흐림':'강수 없음';
  return ['강수 없음','비','비·눈','눈','소나기','빗방울','빗방울·눈날림','눈날림'][pty]||'확인 불가';
}
const clock=(date:Date)=>date.toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',hour12:false});
export function WeatherPanel({region,regions,onRegion,regionLoading,regionError,onRegionsRetry,locked,weather,error,onRetry,widget,onGuide,onHideWidget}:{
  region:string;regions:RegionOption[];onRegion:(id:string)=>void;locked:boolean;
  weather:Weather|null;error:string;onRetry:()=>void;widget:boolean;onGuide:()=>void;onHideWidget:()=>void;
  regionLoading?:boolean;regionError?:string;onRegionsRetry?:()=>void;
}){
  const current=weather?.current?.status==='stale'||weather?.current?.status==='missing'?undefined:weather?.current;
  return <section className="weather-panel" aria-label="지역과 날씨" data-guide="region">
    <div className="region-section"><WeatherIcon pty={current?.pty} sky={current?.sky}/><div>
      <h1>우리 동네 날씨에 맞춘 선곡</h1>
      <RegionPicker region={region} regions={regions} locked={locked} onRegion={onRegion} loading={regionLoading} error={regionError} onRetry={onRegionsRetry}/>
      {weather&&<small>{weather.is_test?`갱신 ${clock(new Date(weather.as_of))} · 검증 자료`:`관측 ${current?.observed_at?clock(new Date(current.observed_at)):'확인 불가'}${weather.forecast_issued_at?` · 예보 ${clock(new Date(weather.forecast_issued_at))}`:''} · 기상청`}</small>}
      {error&&<small className="weather-error" role="alert">{error} <button onClick={onRetry} disabled={locked}>날씨 다시 확인</button></small>}
      {weather?.recommendation_ready===false&&<small role="status">선곡용 날씨가 누락되거나 만료됐습니다. 기존 선곡표는 유지됩니다.</small>}
    </div></div>
    <div className="weather-current"><strong>{!region?'지역 미설정':!weather&&!error?'날씨 확인 중…':weatherLabel(current?.pty,current?.sky)}{current?.temperature!==undefined?` · ${current.temperature}°C`:''}</strong><span>{region?'앞으로 3시간':'지역을 선택하면 날씨를 보여드려요.'}</span></div>
    <div className="forecast" aria-label="시간대별 예보">{[0,1,2,3].map(hour=>{
      const at=weather?new Date(Date.parse(weather.as_of)+hour*3600000):null;
      const row=at?weather?.segments.find(s=>s.status==='valid'&&Date.parse(s.start_at)<=+at&&Date.parse(s.end_at)>+at):undefined;
      return <div className="forecast-hour" key={hour}><time dateTime={at?.toISOString()}>{at?clock(at):hour===0?'현재':`${hour}시간 후`}</time>{region?<WeatherIcon pty={row?.pty} sky={row?.sky}/>:<div className="forecast-placeholder" aria-hidden="true">—</div>}<span>{region?weatherLabel(row?.pty,row?.sky):'—'}</span></div>;
    })}</div>
    {widget&&<div className="guide-widget"><div className="guide-bubble"><strong>사용 안내</strong><p>지역과 취향을 선택하면<br/>날씨에 맞춰 선곡해 드려요.</p><button onClick={onGuide}>안내 보기</button></div><img src="/penguin-guide-first.png" alt="펭귄 사용 안내"/><button className="widget-close" aria-label="안내 위젯 닫기" onClick={onHideWidget}>×</button></div>}
  </section>;
}
