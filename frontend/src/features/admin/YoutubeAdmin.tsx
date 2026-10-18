import {useEffect, useState} from 'react';
import {api} from '../../shared/api';
import {YoutubeReviewPanel} from '../recommendation/YoutubeReviewPanel';

type Me = {authenticated: boolean; role: string; allowed_menus: {path: string; label: string}[]};
export function YoutubeAdmin() {
  const [me, setMe] = useState<Me | null>(null), [error, setError] = useState('');
  useEffect(() => {void api<Me>('/api/auth/me').then(setMe).catch(e => setError(e.message));}, []);
  const allowed = me?.authenticated && me.role === 'ADMIN' && me.allowed_menus.some(menu => menu.path === '/admin/music/youtube');
  return <><header className="header"><a className="brand" href="/">café<span>운영 관리</span></a><nav>
    {me?.allowed_menus.map(menu => <a key={menu.path} href={menu.path} aria-current={menu.path === '/admin/music/youtube' ? 'page' : undefined}>{menu.label}</a>)}
    {me?.authenticated && <button onClick={() => void api('/api/auth/logout', 'POST', {}).then(() => location.assign('/login')).catch(e => setError(e.message))}>로그아웃</button>}
  </nav></header><main className="admin"><h1>YouTube 연결 검수</h1>
    {error && <p role="alert" className="notice error">{error}</p>}
    {allowed ? <YoutubeReviewPanel playlistId="" adminSession onUpdated={() => {}} onPreviewActive={() => {}}/> : <p>음악 관리 권한을 확인해 주세요. <a href="/login">로그인</a></p>}
  </main></>;
}
