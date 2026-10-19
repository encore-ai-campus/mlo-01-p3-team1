import {Icon,WeatherIcon} from '../../components/Icons';
import {RegionPicker,type RegionOption} from './RegionPicker';

export type Weather={
  region_name:string;as_of:string;valid_until:string;is_test:boolean;
  source?:string;collected_at?:string;forecast_issued_at?:string;
  weather_code?:string;bundle_version?:string;recommendation_ready?:boolean;recommendation_error?:string;
  current?:{pty:number;sky:number|null;temperature?:number;observed_at?:string;status?:string};
  segments:{pty:number;sky:number|null;status:string;start_at:string;end_at:string;temperature?:number|null}[];
};
export function weatherLabel(pty?:number,sky?:number|null){
  if(pty===undefined)return '확인 불가';
  if(pty===0)return sky===1?'맑음':sky===3?'구름많음':sky===4?'흐림':'강수 없음';
  return ['강수 없음','비','비·눈','눈','소나기','빗방울','빗방울·눈날림','눈날림'][pty]||'확인 불가';
}
const clock=(date:Date)=>date.toLocaleTimeString('ko-KR',{
  timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',hour12:false,
});

/** Use the observed temperature for the current hour and hourly forecast
 * temperatures for later hours. Never invent an unavailable forecast. */
export function forecastHours(weather:Weather|null){
  const current=weather?.current?.status==='stale'||weather?.current?.status==='missing'?undefined:weather?.current;
  const reference=weather?Date.parse(weather.as_of):NaN;
  return Array.from({length:4},(_,hour)=>{
    const at=Number.isFinite(reference)?new Date(reference+hour*3600000):null;
    const segment=at?weather?.segments?.find(s=>
      s.status==='valid'&&Date.parse(s.start_at)<=+at&&Date.parse(s.end_at)>+at):undefined;
    return {
      hour,at,
      pty:hour===0?current?.pty??segment?.pty:segment?.pty,
      sky:hour===0?current?.sky??segment?.sky:segment?.sky,
      temperature:hour===0?current?.temperature:segment?.temperature,
    };
  });
}

export function WeatherPanel({region,regions,onRegion,regionLoading,regionError,onRegionsRetry,locked,weather,error,onRetry,widget,onGuide,onHideWidget}:{
  region:string;regions:RegionOption[];onRegion:(id:string)=>void;locked:boolean;
  weather:Weather|null;error:string;onRetry:()=>void;widget:boolean;onGuide:()=>void;onHideWidget:()=>void;
  regionLoading?:boolean;regionError?:string;onRegionsRetry?:()=>void;
}){
  const selectedRegion=regions.find(row=>row.region_id===region);
  const forecast=forecastHours(weather);
  return <section id="weather" className="weather-panel muther-weather-panel" aria-label="우리 동네 날씨와 지역 선택" data-guide="region">
    <div className="muther-region-side">
      <div className="muther-weather-title">
        <span className="muther-title-icon"><Icon name="pin"/></span>
        <div>
          <h2>우리 동네 날씨</h2>
          <p>지역을 선택하면 오늘의 날씨와 앞으로 3시간의 날씨를 볼 수 있어요.</p>
        </div>
      </div>
      <RegionPicker region={region} regions={regions} locked={locked} onRegion={onRegion}
        loading={regionLoading} error={regionError} onRetry={onRegionsRetry}/>
      {error&&<p className="weather-error" role="alert">{error}
        <button type="button" onClick={onRetry} disabled={locked}>날씨 다시 확인</button>
      </p>}
      {weather?.recommendation_ready===false&&<p className="weather-readiness" role="status">
        선곡용 날씨가 누락되거나 만료됐어요. 기존 선곡표는 유지됩니다.
      </p>}
    </div>
    <div className="muther-forecast-side">
      <div className="muther-forecast-heading">
        <h2><span className="muther-clock-icon" aria-hidden="true">◷</span> 앞으로 3시간 날씨</h2>
        <span>{weather?.is_test?'날씨 샘플 · ':weather?'기상청 · ':''}
          {weather?.forecast_issued_at?'예보 '+clock(new Date(weather.forecast_issued_at))+' 기준':
            weather?'조회 '+clock(new Date(weather.as_of))+' 기준':'지역 선택 후 표시'}
        </span>
      </div>
      <div className="muther-forecast-cells" role="list" aria-label="시간대별 날씨 예보">
        {forecast.map(({hour,at,pty,sky,temperature})=><div className={'muther-forecast-cell'+(hour===0?' current':'')} key={hour} role="listitem">
          <time dateTime={at?.toISOString()}>{at?(hour===0?'현재 ':'')+clock(at):hour===0?'현재':hour+'시간 후'}</time>
          <WeatherIcon pty={region?pty:undefined} sky={region?sky:undefined}/>
          <strong>{region&&typeof temperature==='number'&&Number.isFinite(temperature)?temperature+'°':'—'}</strong>
          <span>{region?weatherLabel(pty,sky):'지역 미선택'}</span>
        </div>)}
      </div>
      <p className="muther-forecast-note" aria-live="polite">
        {selectedRegion?selectedRegion.name+' · ':''}미제공 시간대의 기온은 —로 표시됩니다.
      </p>
    </div>
    {widget&&<div className="guide-widget muther-guide-widget">
      <button className="widget-close" type="button" aria-label="안내 위젯 닫기" onClick={onHideWidget}>×</button>
      <div className="guide-bubble"><strong>날씨를 바꾸면<br/>음악도 달라져요!</strong>
        <p>동네와 취향을 고르고 오늘의 선곡표를 받아보세요.</p>
        <button type="button" onClick={onGuide}>사용 안내</button>
      </div>
      <img src="/penguin-guide-first.png" alt="친절한 펭귄 음악 안내"/>
    </div>}
  </section>;
}
