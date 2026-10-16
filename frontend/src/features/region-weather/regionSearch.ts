import type {RegionOption} from './RegionPicker';
const compact=(text:string)=>text.normalize('NFKC').toLocaleLowerCase('ko-KR').replace(/\s/g,'');
export function findRegions(regions:RegionOption[],query:string){
  const tokens=query.trim().split(/\s+/).map(compact).filter(Boolean);
  if(!tokens.length)return [];
  const rank=(row:RegionOption)=>{const name=compact(row.locality||row.name),text=compact(query);return name===text?0:name.startsWith(text)?1:2;};
  return regions.filter(row=>{const address=compact([row.name,row.province,row.district,row.locality].join(' '));return tokens.every(token=>address.includes(token));})
    .sort((a,b)=>rank(a)-rank(b)||a.name.localeCompare(b.name,'ko')||a.region_id.localeCompare(b.region_id));
}
