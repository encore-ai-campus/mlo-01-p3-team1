import {describe,it,expect,vi} from 'vitest';
import {api,ApiError,wait} from './api';
import {RecommendationRun} from './recommendationRun';

const intent={path:'/api/recommendation-jobs',body:{region_id:null},id:'original-create-key'};
const cancelled={job_id:'job-1',status:'CANCELLED',playlist_id:null};
describe('server-confirmed recommendation cancellation',()=>{
  it('waits for registration before cancelling, while stopping late UI reads immediately',async()=>{
    let accept!:(value:{job_id:string})=>void;
    const registration=new Promise(resolve=>{accept=resolve;});
    const transport=vi.fn().mockReturnValueOnce(registration).mockResolvedValue(cancelled);
    const run=new RecommendationRun(intent,transport as typeof api);
    const cancellation=run.cancel();
    expect(run.signal.aborted).toBe(true);
    expect(transport).toHaveBeenCalledTimes(1);
    expect((transport.mock.calls[0][4] as AbortSignal).aborted).toBe(false);
    accept({job_id:'job-1'});
    expect(await cancellation).toEqual(cancelled);
    expect(transport.mock.calls[1].slice(0,3)).toEqual(['/api/recommendation-jobs/job-1/cancel','POST',{}]);
  });
  it('replays an uncertain create with the original idempotency key before cancellation',async()=>{
    const transport=vi.fn().mockRejectedValueOnce(new Error('lost response'))
      .mockResolvedValueOnce({job_id:'job-1'}).mockResolvedValueOnce(cancelled);
    const run=new RecommendationRun(intent,transport as typeof api);
    expect(await run.cancel()).toEqual(cancelled);
    expect(transport.mock.calls[0][3]).toBe(intent.id);
    expect(transport.mock.calls[1][3]).toBe(intent.id);
  });
  it('allows retrying an uncertain cancellation without creating a second job or key',async()=>{
    const transport=vi.fn().mockResolvedValueOnce({job_id:'job-1'})
      .mockRejectedValueOnce(new Error('lost cancel response')).mockResolvedValueOnce(cancelled);
    const run=new RecommendationRun(intent,transport as typeof api);
    await expect(run.cancel()).rejects.toThrow('lost cancel response');
    expect(await run.cancel()).toEqual(cancelled);
    expect(transport.mock.calls[1][3]).toBe(transport.mock.calls[2][3]);
    expect(transport.mock.calls.filter(call=>call[0]===intent.path)).toHaveLength(1);
  });
  it('reports a completion that won the race without claiming it was cancelled',async()=>{
    const complete={job_id:'job-1',status:'SUCCEEDED',playlist_id:'result-1'};
    const transport=vi.fn().mockResolvedValueOnce({job_id:'job-1'}).mockResolvedValueOnce(complete);
    const run=new RecommendationRun(intent,transport as typeof api);
    expect(await run.cancel()).toEqual(complete);
  });
  it('handles a no-change weather refresh without sending an invalid cancel URL',async()=>{
    const transport=vi.fn().mockResolvedValue({changed:false,playlist_id:'existing'});
    const run=new RecommendationRun(intent,transport as typeof api);
    expect(await run.cancel()).toBeNull();expect(transport).toHaveBeenCalledTimes(1);
  });
  it('does not lock cancellation after a definite registration rejection',async()=>{
    const transport=vi.fn().mockRejectedValue(new ApiError('VALIDATION_ERROR','invalid',{},422));
    const run=new RecommendationRun(intent,transport as typeof api);
    expect(await run.cancel()).toBeNull();expect(transport).toHaveBeenCalledTimes(1);
  });
  it('rejects a polling wait whose signal was already cancelled',async()=>{
    const controller=new AbortController();controller.abort();
    await expect(wait(60000,controller.signal)).rejects.toMatchObject({name:'AbortError'});
  });
});
