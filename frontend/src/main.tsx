import {createRoot} from 'react-dom/client';
import {PublicPage} from './PublicPage';
import {Login,AdminPage} from './AdminPages';
import './style.css';
const path=location.pathname;
createRoot(document.getElementById('root')!).render(path==='/login'?<Login/>:path==='/admin/music'||path==='/admin/feedback/exclusions'?<AdminPage path={path}/>:path==='/admin/ads'?<main className="admin"><h1>광고 관리 연결 대기</h1><p>광고 관리 서비스에 연결할 수 없습니다.</p><a href="/">오늘의 선곡으로</a></main>:<PublicPage/>);
