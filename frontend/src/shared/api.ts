let csrf = '';
export function setCsrf(value:string){csrf=value;}
export class ApiError extends Error {
  constructor(public code:string,message:string,public details:Record<string,unknown>={},public status=0){super(message);}
}
export const key = () => crypto.randomUUID();
export async function api<T>(path:string,method='GET',body?:unknown,idempotencyKey?:string,signal?:AbortSignal,headers:Record<string,string>={}):Promise<T>{
  const token=csrf || document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.slice(10) || '';
  const response=await fetch(path,{method,credentials:'same-origin',cache:'no-store',signal,
    headers:{...headers,'Content-Type':'application/json',...(token?{'X-CSRFToken':token}:{}),...(idempotencyKey?{'Idempotency-Key':idempotencyKey}:{})},
    body:body===undefined?undefined:JSON.stringify(body)});
  const json=await response.json().catch(()=>null);
  if(!response.ok)throw new ApiError(json?.code || 'SERVICE_UNAVAILABLE',json?.message || '서비스 연결을 확인해 주세요.',json?.details,response.status);
  return json;
}
export const wait=(ms:number,signal:AbortSignal)=>new Promise<void>((resolve,reject)=>{
  const onAbort=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));};
  const timer=setTimeout(()=>{signal.removeEventListener('abort',onAbort);resolve();},ms);
  signal.addEventListener('abort',onAbort,{once:true});
});
export function canonical(value:unknown):string {
  if(Array.isArray(value))return JSON.stringify([...value].sort());
  if(value&&typeof value==='object')return JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>[k,canonical(v)])));
  return JSON.stringify(value);
}
