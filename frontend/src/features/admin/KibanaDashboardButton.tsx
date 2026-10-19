export type KibanaDashboardAccess={allowed:boolean;configured:boolean;path:string|null};
const dashboards={operations:{label:'운영 대시보드',path:'/api/admin/operations/dashboard'},
  logs:{label:'로그 대시보드',path:'/api/admin/operations/logs'}};

export function KibanaDashboardButton({access,kind}:{access?:KibanaDashboardAccess;kind:'operations'|'logs'}){
  if(!access?.allowed)return null;
  const dashboard=dashboards[kind];
  const ready=access.configured&&access.path===dashboard.path;
  return <button type="button" className="kibana-dashboard-button" disabled={!ready}
    onClick={()=>location.assign(dashboard.path)}>
    <span>{dashboard.label}</span>
    {ready?<span aria-hidden="true">↗</span>:<small>연결 준비 중</small>}
  </button>;
}
