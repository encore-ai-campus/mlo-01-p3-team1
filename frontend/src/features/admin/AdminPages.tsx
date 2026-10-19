import {useEffect,useState} from 'react';
import {api} from '../../shared/api';
import {MusicAdmin} from './MusicAdmin';
import {ExclusionsAdmin} from './ExclusionsAdmin';
import {Header} from '../../components/Header';
import {Icon,WeatherIcon} from '../../components/Icons';
type Menu={path:string;label:string};
type Me={authenticated:boolean;role?:string;admin_role?:string|null;allowed_menus:Menu[];sso_enabled?:boolean;local_login_enabled?:boolean};
export function Login(){
  const [authConfig,setAuthConfig]=useState<Me|null>(null);
  const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[show,setShow]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{void api<Me>('/api/auth/me').then(setAuthConfig).catch(()=>setError('로그인 서비스 연결을 기다리고 있어요.'));},[]);
  return <><Header login/><main className="login-layout"><section className="card login-card" aria-labelledby="login-title">
    <div className="login-symbol"><WeatherIcon pty={0} sky={3}/><Icon name="music"/></div>
    <h1 id="login-title">로그인</h1><p className="login-description">계정으로 로그인해 주세요.</p>
    {authConfig?.sso_enabled&&<a className="primary" href="/api/auth/sso/login">관리자 통합 로그인</a>}
    {new URLSearchParams(location.search).get('sso_logout')==='incomplete'&&<p role="alert">서비스에서는 로그아웃되었습니다. 통합 인증 연결이 끊겨 다른 대시보드의 로그아웃은 확인하지 못했습니다.</p>}
    {authConfig?.local_login_enabled!==false&&<form onSubmit={async e=>{
      e.preventDefault();setBusy(true);setError('');
      try{
        const response=await api<{role:string;landing_path:string;allowed_menus:Menu[]}>('/api/auth/login','POST',{username,password});
        if(response.role!=='ADMIN'||!['/admin/ads','/admin/music','/admin/music/youtube','/admin/feedback/exclusions','/api/admin/operations/kibana'].includes(response.landing_path)||!response.allowed_menus.some(menu=>menu.path===response.landing_path))throw new Error('계정 권한을 확인해 주세요.');
        location.assign(response.landing_path);
      }catch(error){setError((error as Error).message);}
      finally{setBusy(false);setPassword('');}
    }}>
      <label htmlFor="username">아이디</label>
      <input id="username" autoComplete="username" placeholder="아이디를 입력해 주세요" required value={username}
        onChange={e=>setUsername(e.target.value)} disabled={busy}/>
      <label htmlFor="password">비밀번호</label>
      <div className="password-field"><input id="password" type={show?'text':'password'} autoComplete="current-password"
        placeholder="비밀번호를 입력해 주세요" required value={password} onChange={e=>setPassword(e.target.value)} disabled={busy}/>
        <button type="button" aria-label={show?'비밀번호 숨기기':'비밀번호 표시'} aria-pressed={show} disabled={busy}
          onClick={()=>setShow(value=>!value)}><Icon name={show?'eye-off':'eye'}/></button>
      </div>
      {error&&<p className="notice error" role="alert">{error}</p>}
      <button className="primary" disabled={busy}>{busy?'로그인 중…':'로그인'}</button>
    </form>}
    <a className="guest-link" href="/"><Icon name="home"/>로그인 없이 선곡 이용하기</a>
    <p className="login-caption">관리자 계정의 권한에 맞는 관리 페이지로 이동합니다.</p>
  </section></main></>;
}
export function AdminPage({path}:{path:string}){return path==='/admin/music'?<MusicAdmin/>:<ExclusionsAdmin/>;}
