import {Icon} from './Icons';
export function Header({login=false,showGuide,isDemo=false}:{login?:boolean;showGuide?:()=>void;isDemo?:boolean}){
  return <header className={`header${login?' login-header':''}`}>
    <a className="brand" href="/">날씨 기반 <span>음악 선곡</span></a>
    {!login&&<a className="nav-active" href="/" aria-current="page">오늘의 선곡</a>}
    {isDemo&&<span className="demo-note" title="고정 검증 모드 · 실제 날씨·음악·평가 자료가 아닙니다.">검증 자료</span>}
    <nav>{login?<a className="home-link" href="/"><Icon name="home"/>선곡 페이지로 <Icon name="arrow"/></a>:<><button onClick={showGuide}>사용 안내</button><a href="/login">로그인</a></>}</nav>
  </header>;
}
