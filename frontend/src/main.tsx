import {createRoot} from 'react-dom/client';
import {PublicPage} from './features/recommendation/PublicPage';
import {Login,AdminPage} from './features/admin/AdminPages';
import {AdsAdmin} from './features/admin-ads/AdsAdmin';
import './style.css';
import './features/admin-ads/ads-admin.css';
const path=location.pathname;
createRoot(document.getElementById('root')!).render(path==='/login'?<Login/>:path==='/admin/music'||path==='/admin/feedback/exclusions'?<AdminPage path={path}/>:path==='/admin/ads'?<AdsAdmin/>:<PublicPage/>);
