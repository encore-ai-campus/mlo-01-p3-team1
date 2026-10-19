import {Icon} from '../../components/Icons';

export function HeroBanner({onCreate}:{onCreate:()=>void}){
  return <section className="muther-hero" aria-labelledby="muther-hero-title">
    <div className="muther-hero-photo">
      <div className="muther-hero-copy">
        <span className="muther-hero-eyebrow">TODAY'S PLAYLIST</span>
        <h1 id="muther-hero-title">오늘의 선곡표</h1>
        <p>오늘의 날씨와 취향으로<br/>나만의 선곡표를 만들어 보세요</p>
        <button className="muther-hero-cta" type="button" onClick={onCreate}>
          <span className="muther-play-icon" aria-hidden="true">▶</span>
          오늘의 선곡표 만들기 <Icon name="arrow"/>
        </button>
      </div>
    </div>
    <div className="muther-hero-brand">
      <div className="muther-brand-orbit" aria-hidden="true"/>
      <span className="muther-brand-sun" aria-hidden="true"/>
      <span className="muther-brand-cloud cloud-a" aria-hidden="true">☁</span>
      <span className="muther-brand-cloud cloud-b" aria-hidden="true">☁</span>
      <svg className="muther-brand-wave left" viewBox="0 0 100 70" aria-hidden="true">
        {Array.from({length:11},(_,i)=><rect key={i} x={5+i*9} y={35-([8,18,29,16,9,32,17,26,13,8,4][i])/2}
          width="4" height={[8,18,29,16,9,32,17,26,13,8,4][i]} rx="2"/>)}
      </svg>
      <div className="muther-hero-logotype" aria-label="Music X Weather">
        <span className="muther-hero-music">MUSIC</span>
        <span className="muther-hero-cross">×</span>
        <span className="muther-hero-weather">WEATHER<span className="muther-hero-period">.</span></span>
      </div>
      <svg className="muther-brand-wave right" viewBox="0 0 100 70" aria-hidden="true">
        {Array.from({length:11},(_,i)=><rect key={i} x={5+i*9} y={35-([8,18,29,16,9,32,17,26,13,8,4][i])/2}
          width="4" height={[8,18,29,16,9,32,17,26,13,8,4][i]} rx="2"/>)}
      </svg>
      <p>날씨가 바뀌면,<br/>음악도 달라지니까.</p>
    </div>
  </section>;
}
