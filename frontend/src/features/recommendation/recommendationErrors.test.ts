import {describe,expect,it} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {RecommendationErrorNotice} from './RecommendationErrorNotice';

const callbacks={onResume:()=>{},onReconnect:()=>{},onReviewConditions:()=>{}};
describe('Recommendation failure recovery',()=>{
  it('shows candidate evidence and directs shortage to the existing choices',()=>{
    const html=renderToStaticMarkup(createElement(RecommendationErrorNotice,{
      ...callbacks,failure:{code:'CANDIDATE_SHORTAGE',message:'조건에 맞는 후보 3곡, 총 12분 38초로 최소 176분보다 짧아요.'},
      pendingRequest:false,locked:false}));
    expect(html).toContain('후보 3곡');
    expect(html).toContain('12분 38초');
    expect(html).toContain('선택 조건 확인');
    expect(html).not.toContain('연결 다시 확인');
  });
  it('keeps incomplete search and unchanged results separate from connection errors',()=>{
    for(const code of ['SEARCH_INCOMPLETE','NO_MEANINGFUL_CHANGE']){
      const html=renderToStaticMarkup(createElement(RecommendationErrorNotice,{
        ...callbacks,failure:{code,message:'현재 선곡표는 유지됩니다.'},pendingRequest:false,locked:false}));
      expect(html).toContain('현재 선곡표는 유지됩니다.');
      expect(html).toContain('선택 조건 확인');
      expect(html).not.toContain('연결 다시 확인');
    }
  });
  it('resumes an uncertain pending request without replacing it with a new request',()=>{
    const html=renderToStaticMarkup(createElement(RecommendationErrorNotice,{
      ...callbacks,failure:{message:'작업 조회를 잠시 멈췄어요.'},pendingRequest:true,locked:false}));
    expect(html).toContain('같은 요청 다시 확인');
    expect(html).not.toContain('선택 조건 확인');
    expect(html).not.toContain('연결 다시 확인');
  });
  it('retains reconnect recovery for initialization or network failures',()=>{
    const html=renderToStaticMarkup(createElement(RecommendationErrorNotice,{
      ...callbacks,failure:{code:'SERVICE_UNAVAILABLE',message:'서비스 연결을 확인해 주세요.'},pendingRequest:false,locked:true}));
    expect(html).toContain('연결 다시 확인');
    expect(html).toContain('disabled');
  });
});
