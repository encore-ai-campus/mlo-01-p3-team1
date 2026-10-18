import {Icon} from './Icons';
export function Header({login=false,showGuide,isDemo=false,musicSource,weatherIsTest}:{login?:boolean;showGuide?:()=>void;isDemo?:boolean;musicSource?:string;weatherIsTest?:boolean}){
  const weatherSource=weatherIsTest===false?'기상청 날씨':weatherIsTest===true?'날씨 샘플':'';
  return <header className={`header${login?' login-header':''}`}>
    <a className="brand" href="/">날씨 기반 <span>음악 선곡</span></a>
    {!login&&<a className="nav-active" href="/" aria-current="page">오늘의 선곡</a>}
    {isDemo&&<span className="demo-note" title={`음악: ${musicSource==='CSV'?'제공 CSV의 실제 곡 정보(수동 검수 미완료)':'로컬 자료'} · 날씨: ${weatherSource||'지역 선택 후 조회'} · 평가는 이 PC에 저장됩니다.`}>{[musicSource==='CSV'?'CSV 음악':'로컬 실행',weatherSource].filter(Boolean).join(' · ')}</span>}
    <nav>{login?<a className="home-link" href="/"><Icon name="home"/>선곡 페이지로 <Icon name="arrow"/></a>:<><button onClick={showGuide}>사용 안내</button><a href="/login">로그인</a></>}</nav>
  </header>;
}
