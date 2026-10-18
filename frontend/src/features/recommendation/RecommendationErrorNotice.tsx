export type RecommendationFailure = {code?:string;message:string};

export function RecommendationErrorNotice({failure,pendingRequest,locked,onResume,onReconnect,onReviewConditions}:{
  failure:RecommendationFailure;pendingRequest:boolean;locked:boolean;
  onResume:()=>void;onReconnect:()=>void;onReviewConditions:()=>void;
}){
  const recommendationFailure=['CANDIDATE_SHORTAGE','NO_MEANINGFUL_CHANGE','SEARCH_INCOMPLETE'].includes(failure.code||'');
  return <div role="alert" className="notice error">{failure.message}
    {pendingRequest?<button onClick={onResume} disabled={locked}>같은 요청 다시 확인</button>:
      recommendationFailure?<button onClick={onReviewConditions} disabled={locked}>선택 조건 확인</button>:
      <button onClick={onReconnect} disabled={locked}>연결 다시 확인</button>}
  </div>;
}
