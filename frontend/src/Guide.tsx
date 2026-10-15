import {useEffect,useRef,useState} from 'react';
const steps=[
  ['지역과 날씨를 확인해 주세요','동 단위 지역을 선택하면 현재 날씨와 앞으로 3시간 예보를 확인할 수 있어요. 비·눈 소식도 날씨 패널에서 함께 확인해 주세요.'],
  ['매장의 분위기를 골라 주세요','보컬·빠르기는 선택 사항이에요. 테마와 장르는 여러 개 고를 수 있고, 지역만 선택해도 선곡표를 받을 수 있어요.'],
  ['선곡표를 살펴보고 승인해 주세요','곡을 제외한 뒤 다른 선곡표를 요청할 수 있어요. 좋아요·싫어요와 전체 별점은 선택 사항이며, 새 선곡표는 따로 승인해 주세요.']
];
const version='guide-3step-v1';
export function Guide({close}:{close:()=>void}){
  const [step,setStep]=useState(0); const panel=useRef<HTMLDivElement>(null);
  const [target,setTarget]=useState<{left:number;top:number;width:number;height:number}|null>(null);
  const [position,setPosition]=useState<{left:number;top:number}|undefined>();
  function finish(skipped=false){try{localStorage.setItem('cafe-guide',JSON.stringify({guideVersion:version,completed:!skipped,skipped}));}catch{/* optional convenience storage */}close();}
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null;
    const previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden';
    panel.current?.focus();
    const keyboard=(e:KeyboardEvent)=>{
      if(e.key==='Escape'){e.preventDefault();finish(true);}
      if(e.key==='Tab'){
        const buttons=panel.current?.querySelectorAll<HTMLButtonElement>('button'); if(!buttons?.length)return;
        const first=buttons[0],last=buttons[buttons.length-1];
        if(e.shiftKey&&(document.activeElement===first||document.activeElement===panel.current)){e.preventDefault();last.focus();}
        else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
      }
    };
    document.addEventListener('keydown',keyboard);return()=>{document.removeEventListener('keydown',keyboard);document.body.style.overflow=previousOverflow;previous?.focus();};
  },[]);
  useEffect(()=>{
    const element=document.querySelector<HTMLElement>('[data-guide="'+['region','selection','playlist'][step]+'"]');
    if(!element)return;
    if(innerWidth<1100)element.scrollIntoView({block:'center'});
    function measure(){
      const rect=element!.getBoundingClientRect();
      const widget=step===0?element!.querySelector('.guide-widget')?.getBoundingClientRect():null;
      setTarget({left:rect.left-4,top:rect.top-4,width:(widget?widget.left-rect.left-12:rect.width)+8,height:rect.height+8});
      const dialog=panel.current?.getBoundingClientRect();
      if(innerWidth>=1100&&dialog){
        const left=step===0?(innerWidth-dialog.width)/2:step===1?rect.right+24:rect.left-dialog.width-24;
        const top=step===0?rect.bottom+24:rect.top+12;
        setPosition({left:Math.max(24,Math.min(innerWidth-dialog.width-24,left)),top:Math.max(24,Math.min(innerHeight-dialog.height-24,top))});
      }else setPosition(undefined);
    }
    measure();addEventListener('resize',measure);addEventListener('scroll',measure,true);
    return()=>{removeEventListener('resize',measure);removeEventListener('scroll',measure,true);};
  },[step]);
  function next(){if(step===2)finish();else setStep(step+1);}
  return <div className="guide-shade" onClick={next}>
    {target&&<div className="guide-focus" style={target} aria-hidden="true"/>}
    <div className="guide-dialog" style={position} role="dialog" aria-modal="true" aria-labelledby="guide-title" tabIndex={-1} ref={panel}>
      <button className="guide-close" aria-label="안내 닫기" onClick={e=>{e.stopPropagation();finish(true);}}>×</button>
      <img src="/penguin-guide-first.png" alt="목도리를 두른 펭귄 안내"/>
      <span className="eyebrow">{['지역 · 날씨','음악 선택','선곡표 확인'][step]} · {step+1} / 3 <span className="guide-progress" aria-hidden="true">{[0,1,2].map(n=><i key={n} className={n===step?'current':''}/>)}</span></span><h2 id="guide-title">{steps[step][0]}</h2><p>{steps[step][1]}</p>
      <small>안내 중에는 실제 선택이나 평가가 변경되지 않아요.</small>
      <div className="guide-actions" onClick={e=>e.stopPropagation()}>
        {step>0&&<button onClick={()=>setStep(step-1)}>이전</button>}
        {step<2&&<button onClick={()=>finish(true)}>건너뛰기</button>}
        <button onClick={next}>{step===2?'안내 마치기':'다음'}</button>
      </div>
    </div>
  </div>;
}
