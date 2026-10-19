import {YoutubeReviewPanel} from '../recommendation/YoutubeReviewPanel';
import {AdminLayout,NoAdminAccess,useAdminSession} from './AdminLayout';

export function YoutubeAdmin() {
  const path='/admin/music/youtube',session=useAdminSession(path);
  return <AdminLayout me={session.me} path={path} title="YouTube 연결 검수" subtitle="곡과 영상의 연결을 확인하고 외부 재생과 삽입 재생을 각각 검수하세요." error={session.error} onRetry={session.retry}>
    {session.allowed?<YoutubeReviewPanel playlistId="" adminSession onUpdated={()=>{}} onPreviewActive={()=>{}}/>:<NoAdminAccess loaded={!!session.me}/>}
  </AdminLayout>;
}
