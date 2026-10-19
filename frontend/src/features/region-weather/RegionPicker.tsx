import {useEffect,useMemo,useState} from 'react';
import {Icon} from '../../components/Icons';
import './region-picker.css';

export type RegionOption={
  region_id:string;
  name:string;
  province?:string;
  district?:string;
  locality?:string;
};

export function regionHierarchy(regions:RegionOption[],province:string,district:string){
  const names=(values:(string|undefined)[])=>[...new Set(values.filter((v):v is string=>!!v?.trim()))]
    .sort((a,b)=>a.localeCompare(b,'ko'));
  const provinces=names(regions.map(row=>row.province));
  const districts=province?names(regions.filter(row=>row.province===province).map(row=>row.district)):[];
  const localities=province&&district?regions
    .filter(row=>row.province===province&&row.district===district)
    .sort((a,b)=>(a.locality||a.name).localeCompare(b.locality||b.name,'ko')||a.region_id.localeCompare(b.region_id)):[];
  return {provinces,districts,localities};
}

export function RegionPicker({region,regions,locked,onRegion,loading=false,error='',onRetry}:{
  region:string;
  regions:RegionOption[];
  locked:boolean;
  onRegion:(id:string)=>void;
  loading?:boolean;
  error?:string;
  onRetry?:()=>void;
}){
  const selected=regions.find(row=>row.region_id===region);
  const [province,setProvince]=useState('');
  const [district,setDistrict]=useState('');
  const [draft,setDraft]=useState('');
  useEffect(()=>{
    setProvince(selected?.province||'');
    setDistrict(selected?.district||'');
    setDraft(selected?.region_id||'');
  },[region,regions]);

  const provinces=useMemo(()=>regionHierarchy(regions,'','').provinces,[regions]);
  const districts=useMemo(()=>regionHierarchy(regions,province,'').districts,[regions,province]);
  const localities=useMemo(()=>regionHierarchy(regions,province,district).localities,[regions,province,district]);
  const pendingRegion=localities.find(row=>row.region_id===draft);
  const ready=!!pendingRegion&&draft!==region&&!locked&&!loading&&!error;

  return <div className="region-picker">
    <div className="region-selectors">
      <label className="region-select-label">
        <span>시·도</span>
        <select aria-label="시·도" value={province} disabled={locked||loading||!!error||!regions.length}
          onChange={event=>{setProvince(event.target.value);setDistrict('');setDraft('');}}>
          <option value="">시·도 선택</option>
          {provinces.map(name=><option value={name} key={name}>{name}</option>)}
        </select>
      </label>
      <label className="region-select-label">
        <span>시·군·구</span>
        <select aria-label="시·군·구" value={district} disabled={locked||!province||loading||!!error}
          onChange={event=>{setDistrict(event.target.value);setDraft('');}}>
          <option value="">시·군·구 선택</option>
          {districts.map(name=><option value={name} key={name}>{name}</option>)}
        </select>
      </label>
      <label className="region-select-label">
        <span>읍·면·동</span>
        <select aria-label="읍·면·동" value={draft} disabled={locked||!district||loading||!!error}
          onChange={event=>setDraft(event.target.value)}>
          <option value="">읍·면·동 선택</option>
          {localities.map(row=><option value={row.region_id} key={row.region_id}>
            {row.locality||row.name}
          </option>)}
        </select>
      </label>
      <button type="button" className="region-apply" disabled={!ready}
        aria-label="선택한 지역으로 날씨 변경" onClick={()=>onRegion(draft)}>
        <Icon name="arrow"/> <span>지역 변경</span>
      </button>
    </div>
    {loading&&<p className="region-message" role="status">지역 목록을 불러오고 있어요.</p>}
    {!loading&&(error||!regions.length)&&<p className="region-message" role="alert">
      {error||'선택 가능한 지역이 없어요.'}
      {onRetry&&<button type="button" onClick={onRetry} disabled={locked}>지역 목록 다시 확인</button>}
    </p>}
    {selected&&<p className="region-selected" aria-live="polite">
      <Icon name="pin"/> 현재 선택한 지역: {selected.name}
    </p>}
  </div>;
}
