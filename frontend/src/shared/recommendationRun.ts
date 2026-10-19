import {api,ApiError,key} from './api';

export type JobIntent={path:string;body:unknown;id:string};
export type JobState={job_id:string;status:string;playlist_id:string|null;error?:{message:string}|null};
type Accepted={job_id?:string};

// Cancelling a fetch alone cannot cancel a job already accepted by the server.
export class RecommendationRun {
  private lifetime=new AbortController();
  private polling=new AbortController();
  private cancelKey=key();
  private submission:Promise<Accepted>;
  constructor(readonly intent:JobIntent,private transport:typeof api=api){
    this.submission=this.submit();
  }
  private submit(){
    return this.transport<Accepted>(this.intent.path,'POST',this.intent.body,this.intent.id,this.lifetime.signal);
  }
  get accepted(){return this.submission;}
  get signal(){return this.polling.signal;}
  async cancel():Promise<JobState|null>{
    // Suppress late UI results immediately; keep registration alive to learn the job ID.
    this.polling.abort();
    const accepted=await this.submission.catch(error=>{
      // A definite registration rejection created no job; do not leave the UI locked.
      if(error instanceof ApiError&&error.status>=400&&error.status<500)return {job_id:undefined};
      // An uncertain POST is replayed with its original idempotency key.
      this.submission=this.submit();return this.submission;
    });
    if(!accepted.job_id)return null; // Weather refresh found no change.
    return this.transport<JobState>(`/api/recommendation-jobs/${encodeURIComponent(accepted.job_id)}/cancel`,
      'POST',{},this.cancelKey,this.lifetime.signal);
  }
  dispose(){this.polling.abort();this.lifetime.abort();}
}
