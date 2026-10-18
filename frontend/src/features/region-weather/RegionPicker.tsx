import {useEffect,useId,useRef,useState} from 'react';
import {Icon} from '../../components/Icons';
import {findRegions} from './regionSearch';
import './region-picker.css';

export type RegionOption={region_id:string;name:string;province?:string;district?:string;locality?:string};
export function RegionPicker({region,regions,locked,onRegion,loading=false,error='',onRetry}:{
  region:string;regions:RegionOption[];locked:boolean;onRegion:(id:string)=>void;
  loading?:boolean;error?:string;onRetry?:()=>void;
}){
  const selected=regions.find(row=>row.region_id===region);
  const [query,setQuery]=useState(''),[open,setOpen]=useState(false),[active,setActive]=useState(-1);
  const [province,setProvince]=useState(''),[district,setDistrict]=useState(''),[draft,setDraft]=useState('');
  const root=useRef<HTMLDivElement>(null),input=useRef<HTMLInputElement>(null),dialog=useRef<HTMLDialogElement>(null);
  const listId=useId(),titleId=useId();
  const matches=findRegions(regions,query),visible=matches.slice(0,30);
  const unavailable=loading||!!error||!regions.length;
  useEffect(()=>{
    const outside=(event:Event)=>{if(!root.current?.contains(event.target as Node))setOpen(false);};
    document.addEventListener('pointerdown',outside);document.addEventListener('focusin',outside);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('focusin',outside);};
  },[]);
  useEffect(()=>{if(locked){setOpen(false);dialog.current?.close();}},[locked]);
  useEffect(()=>{if(open&&active>=0)document.getElementById(`${listId}-${active}`)?.scrollIntoView({block:'nearest'});},[active,open,listId]);
  function apply(id:string){if(locked||!regions.some(row=>row.region_id===id))return;onRegion(id);setQuery('');setOpen(false);setActive(-1);input.current?.focus();}
  function direct(){setOpen(false);setProvince(selected?.province||'');setDistrict(selected?.district||'');setDraft(selected?.region_id||'');dialog.current?.showModal();}
  const provinces=[...new Set(regions.map(row=>row.province).filter((name):name is string=>!!name))].sort();
  const districts=[...new Set(regions.filter(row=>row.province===province).map(row=>row.district).filter((name):name is string=>!!name))].sort();
  const localities=regions.filter(row=>row.province===province&&row.district===district);
  return <div className="region-picker" ref={root}>
    <div className="region-search-field"><Icon name="pin"/>
      <input ref={input} type="search" role="combobox" aria-label="지역 검색" placeholder="동네 이름을 검색해 주세요"
        aria-expanded={open&&!!query.trim()} aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={open&&active>=0&&visible[active]?`${listId}-${active}`:undefined}
        value={query} disabled={locked||loading} autoComplete="off"
        onFocus={()=>{setActive(-1);setOpen(true);}} onChange={event=>{setQuery(event.target.value);setActive(-1);setOpen(true);}}
        onKeyDown={event=>{
          if(event.nativeEvent.isComposing)return;
          if(event.key==='Escape'){setOpen(false);setActive(-1);return;}
          if(['ArrowDown','ArrowUp'].includes(event.key)&&visible.length){event.preventDefault();setOpen(true);setActive(index=>event.key==='ArrowDown'?(index+1)%visible.length:(index<=0?visible.length:index)-1);}
          if(event.key==='Enter'){event.preventDefault();if(open&&active>=0&&visible[active])apply(visible[active].region_id);}
        }}/>
    </div>
    <div className="region-picker-links"><button type="button" className="region-direct" disabled={locked||unavailable} onClick={direct}>지역을 직접 선택하기 <span aria-hidden="true">›</span></button>
      {selected&&<span className="region-selected" title={selected.name}>{selected.name}</span>}
    </div>
    {loading&&<p className="region-message" role="status">지역 목록을 불러오고 있어요.</p>}
    {!loading&&(error||!regions.length)&&<p className="region-message" role="status">{error||'선택 가능한 지역이 없어요.'} {onRetry&&<button type="button" disabled={locked} onClick={onRetry}>지역 목록 다시 확인</button>}</p>}
    {open&&!!query.trim()&&<div className="region-results">
      <ul id={listId} role="listbox" aria-label="지역 검색 결과">{!unavailable&&visible.map((row,index)=><li key={row.region_id} id={`${listId}-${index}`} role="option" aria-selected={index===active}
        onPointerDown={event=>event.preventDefault()} onMouseEnter={()=>setActive(index)} onClick={()=>apply(row.region_id)}>
        <Icon name="pin"/><div><strong>{row.locality||row.name}</strong><span>{[row.province,row.district].filter(Boolean).join(' ')||row.name}</span></div>
      </li>)}</ul>
      <p role="status">{unavailable?'지역 목록을 확인한 후 검색해 주세요.':!matches.length?'일치하는 지역이 없어요. 시·군·구 또는 동 이름을 확인해 주세요.':matches.length>30?`${matches.length}개 중 30개 표시 · 시·군·구를 함께 입력하면 더 좁힐 수 있어요.`:`${matches.length}개 지역 · 검색 결과를 선택해 주세요.`}</p>
    </div>}
    <dialog ref={dialog} className="region-dialog" aria-labelledby={titleId} onClick={event=>{
      if(event.target===event.currentTarget){const box=event.currentTarget.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)dialog.current?.close();}
    }}>
      <div className="region-dialog-heading"><h2 id={titleId}>지역 직접 선택</h2><button type="button" aria-label="지역 선택 닫기" onClick={()=>dialog.current?.close()}>×</button></div>
      <p>시·도부터 차례로 선택해 주세요. 설정 전까지 현재 지역은 유지됩니다.</p>
      <div className="region-hierarchy">
        <label>시·도<select autoFocus aria-label="시·도" value={province} disabled={locked} onChange={event=>{setProvince(event.target.value);setDistrict('');setDraft('');}}><option value="">시·도 선택</option>{provinces.map(name=><option key={name}>{name}</option>)}</select></label>
        <label>시·군·구<select aria-label="시·군·구" value={district} disabled={locked||!province} onChange={event=>{setDistrict(event.target.value);setDraft('');}}><option value="">시·군·구 선택</option>{districts.map(name=><option key={name}>{name}</option>)}</select></label>
        <label>읍·면·동<select aria-label="읍·면·동" value={draft} disabled={locked||!district} onChange={event=>setDraft(event.target.value)}><option value="">읍·면·동 선택</option>{localities.map(row=><option key={row.region_id} value={row.region_id}>{row.locality||row.name}</option>)}</select></label>
      </div>
      <div className="region-dialog-actions"><button type="button" onClick={()=>{dialog.current?.close();input.current?.focus();}}>검색으로 찾기</button><button type="button" className="primary" disabled={locked||!draft} onClick={()=>{apply(draft);dialog.current?.close();}}>이 지역으로 설정</button></div>
    </dialog>
  </div>;
}
