import {useEffect,useRef,useState} from 'react';
import type {Choices,Option} from '../../shared/types';

type TagType='theme'|'genre';
type Props={
  options:Option[];
  choices:Choices;
  disabled:boolean;
  onToggle:(option:Option)=>void;
  onSelectGroup:(type:TagType,codes:string[])=>void;
};

const labels:Record<TagType,string>={theme:'테마',genre:'장르'};

export function TagPicker({options,choices,disabled,onToggle,onSelectGroup}:Props){
  const [open,setOpen]=useState<TagType|null>(null);
  const rootRef=useRef<HTMLDivElement>(null);
  const themeTrigger=useRef<HTMLButtonElement>(null);
  const genreTrigger=useRef<HTMLButtonElement>(null);

  useEffect(()=>{
    if(!open)return;
    const closeOutside=(event:MouseEvent)=>{
      if(!rootRef.current?.contains(event.target as Node))setOpen(null);
    };
    document.addEventListener('click',closeOutside);
    return()=>document.removeEventListener('click',closeOutside);
  },[open]);
  useEffect(()=>{if(disabled)setOpen(null);},[disabled]);

  const visibleOptions=options.filter(option=>option.type===open);
  const enabledCodes=visibleOptions.filter(option=>option.enabled).map(option=>option.code).sort();
  const selectedCodes=open==='genre'?choices.selected_genre_codes:choices.selected_theme_codes;
  const allSelected=enabledCodes.length>0&&enabledCodes.every(code=>selectedCodes.includes(code));
  return <div className="tag-selector" ref={rootRef}
    onKeyDown={event=>{
      if(event.key!=='Escape'||!open)return;
      event.stopPropagation();setOpen(null);
      (open==='theme'?themeTrigger:genreTrigger).current?.focus();
    }}>
    {(['theme','genre'] as const).map(type=>{
      const count=(type==='theme'?choices.selected_theme_codes:choices.selected_genre_codes).length;
      const available=options.some(option=>option.type===type);
      return <div className={`tag-group tag-group-${type}`} key={type}>
        <button type="button" className={`tag-category tag-category-${type}`}
          ref={type==='theme'?themeTrigger:genreTrigger}
          disabled={disabled||!available} aria-expanded={open===type}
          aria-controls={open===type?`tag-panel-${type}`:undefined}
          onClick={()=>setOpen(current=>current===type?null:type)}>
          <span className="tag-category-label">{labels[type]}</span>
          <span className="tag-category-count">{available?(count?`${count}개 선택`:'선택 없음'):'준비 중'}</span>
          <span className="tag-category-arrow" aria-hidden="true"/>
        </button>
        {open===type&&<div className={`tag-popover tag-popover-${type}`} id={`tag-panel-${type}`}
          role="group" aria-label={`${labels[type]} 선택`}>
          <strong>{labels[type]} 선택</strong>
          <p>여러 개 선택할 수 있어요.</p>
          <div className="tag-bulk-actions">
            <button type="button" disabled={disabled||!enabledCodes.length||allSelected}
              aria-label={`${labels[type]} 전체선택`} onClick={()=>onSelectGroup(type,enabledCodes)}>전체선택</button>
            <button type="button" disabled={disabled||!selectedCodes.length}
              aria-label={`${labels[type]} 전체선택 해제`} onClick={()=>onSelectGroup(type,[])}>전체선택 해제</button>
          </div>
          <div className="tag-option-grid">
            {visibleOptions.map(option=>{
              const selected=(type==='theme'?choices.selected_theme_codes:choices.selected_genre_codes).includes(option.code);
              return <button type="button" key={option.code} className="tag-option"
                aria-pressed={selected} aria-label={option.enabled?option.label:`${option.label}, 준비 중`}
                disabled={disabled||!option.enabled} onClick={()=>onToggle(option)}>{option.label}</button>;
            })}
          </div>
        </div>}
      </div>;
    })}
  </div>;
}
