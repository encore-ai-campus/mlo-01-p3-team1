import {WeatherIcon} from '../../components/Icons';
import {weatherLabel,type Weather} from '../region-weather/WeatherPanel';

export function PlaylistIntro({regionName,weather}:{regionName?:string;weather:Weather|null}){
  const current=weather?.current?.status==='stale'||weather?.current?.status==='missing'?undefined:weather?.current;
  const status=regionName?weather?weatherLabel(current?.pty,current?.sky):'날씨 확인 중':'지역을 먼저 선택해 주세요';
  return <section className="muther-playlist-intro" aria-labelledby="playlist-intro-title">
    <div className="muther-playlist-intro-copy">
      <span className="muther-section-eyebrow">YOUR MUSIC, YOUR WEATHER</span>
      <h1 id="playlist-intro-title">오늘의 선곡을<br/><span>시작해 볼까요?</span></h1>
      <p>하늘의 분위기와 나의 취향을 조합해<br/>3시간을 채울 선곡표를 만들어 보세요.</p>
      <div className="muther-intro-context">
        <WeatherIcon pty={current?.pty} sky={current?.sky}/>
        <div><strong>{regionName||'선택한 지역 없음'}</strong><span>{status}</span></div>
      </div>
    </div>
    <div className="muther-playlist-deco" aria-hidden="true">
      <div className="muther-deco-sun"/>
      <div className="muther-deco-disc"><div className="muther-deco-disc-center"/></div>
      <span className="muther-deco-cloud">☁</span>
      <div className="muther-deco-words">FEEL THE<br/><strong>WEATHER</strong><br/>HEAR THE MUSIC</div>
    </div>
  </section>;
}
