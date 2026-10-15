import {useEffect,useRef,useState} from 'react';
import {api,ApiError,key} from './api';
import type {Feedback,FeedbackRead,FeedbackValue} from './types';
type Intent={source:string;target:string;value:FeedbackValue['value'];revision:number;id:string};
type Failure={intent:Intent;message:string;conflict:boolean};
function fromRead(data:FeedbackRead):Feedback {
  return {source_playlist_id:data.source_playlist_id,
    track_reactions:data.track_reactions.map(r=>({track_id:r.track_id,value:r.reaction,revision:r.revision})),
    playlist_rating:{value:data.playlist_rating.rating,revision:data.playlist_rating.revision}};
}
export function useFeedback(playlistId:string|undefined){
  const [feedback,setFeedback]=useState<Feedback|null>(null),[readError,setReadError]=useState(''),[pending,setPending]=useState<string[]>([]);
  const [failures,setFailures]=useState<Record<string,Failure>>({}),[readAttempt,setReadAttempt]=useState(0);
  const currentId=useRef(playlistId);currentId.current=playlistId;
  const inflight=useRef(new Set<string>());
  useEffect(()=>{
    setFeedback(null);setReadError('');setFailures({});setPending([]);if(!playlistId)return;
    const abort=new AbortController();
    api<FeedbackRead>('/api/playlists/'+playlistId+'/feedback','GET',undefined,undefined,abort.signal).then(data=>{
      if(!abort.signal.aborted&&currentId.current===playlistId)setFeedback(fromRead(data));
    }).catch(error=>{if(!abort.signal.aborted&&currentId.current===playlistId)setReadError(error.message);});
    return()=>abort.abort();
  },[playlistId,readAttempt]);
  async function save(target:string,value:FeedbackValue['value'],attempt?:Intent){
    if(!playlistId||attempt&&attempt.source!==playlistId)return;
    const savingId=playlistId,identity=savingId+':'+target;
    if(inflight.current.has(identity))return;
    const current=target==='rating'?feedback?.playlist_rating:feedback?.track_reactions.find(track=>track.track_id===target);
    if(!current){setReadError('평가 서비스 연결을 확인해 주세요.');return;}
    const intent=attempt||{source:savingId,target,value,revision:current.revision,id:key()};
    inflight.current.add(identity);setPending(items=>[...items,target]);
    try{
      const result=await api<FeedbackValue>('/api/playlists/'+savingId+'/'+(target==='rating'?'rating':'tracks/'+encodeURIComponent(target)+'/reaction'),'PUT',
        {[target==='rating'?'rating':'reaction']:intent.value,expected_revision:intent.revision},intent.id);
      if(currentId.current===savingId){
        setFeedback(previous=>!previous?previous:target==='rating'?{...previous,playlist_rating:result}:
          {...previous,track_reactions:previous.track_reactions.map(track=>track.track_id===target?{...track,...result}:track)});
        setFailures(previous=>{const next={...previous};delete next[target];return next;});
      }
    }catch(error){
      if(currentId.current===savingId)setFailures(previous=>({...previous,[target]:{intent,message:(error as Error).message,
        conflict:error instanceof ApiError&&error.code==='FEEDBACK_REVISION_CONFLICT'}}));
    }finally{
      inflight.current.delete(identity);
      if(currentId.current===savingId)setPending(items=>items.filter(item=>item!==target));
    }
  }
  async function retrySave(failure:Failure){
    const {intent}=failure;if(!playlistId||intent.source!==playlistId)return;
    if(!failure.conflict){await save(intent.target,intent.value,intent);return;}
    try{
      const latest=fromRead(await api<FeedbackRead>('/api/playlists/'+playlistId+'/feedback'));
      if(currentId.current!==playlistId)return;
      setFeedback(latest);
      const revision=intent.target==='rating'?latest.playlist_rating.revision:latest.track_reactions.find(track=>track.track_id===intent.target)?.revision;
      if(revision===undefined)throw new Error('평가 대상을 확인할 수 없어요.');
      await save(intent.target,intent.value,{...intent,revision,id:key()});
    }catch(error){
      if(currentId.current===playlistId)setFailures(previous=>({...previous,[intent.target]:{...failure,message:(error as Error).message}}));
    }
  }
  const failure=Object.values(failures).find(item=>item.intent.source===playlistId);
  return {feedback,error:failure?.message||readError,pending,save,
    retry:failure?()=>retrySave(failure):readError?async()=>{setReadAttempt(value=>value+1);}:null,
    retryLabel:failure?'평가 다시 저장':'평가 다시 확인'};
}
