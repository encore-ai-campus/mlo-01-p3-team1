import {expect,test} from 'vitest';
import {forecastHours,type Weather} from '../src/features/region-weather/WeatherPanel';

function sample():Weather{
  return {
    region_name:'서울특별시 구로구 구로제1동',
    as_of:'2026-10-19T02:02:00Z',valid_until:'2026-10-19T02:07:00Z',is_test:false,
    current:{pty:0,sky:1,temperature:17.4,status:'valid'},
    segments:[
      {start_at:'2026-10-19T02:00:00Z',end_at:'2026-10-19T03:00:00Z',temperature:19,pty:0,sky:4,status:'valid'},
      {start_at:'2026-10-19T03:00:00Z',end_at:'2026-10-19T04:00:00Z',temperature:18,pty:0,sky:3,status:'valid'},
      {start_at:'2026-10-19T04:00:00Z',end_at:'2026-10-19T05:00:00Z',temperature:19,pty:0,sky:4,status:'valid'},
      {start_at:'2026-10-19T05:00:00Z',end_at:'2026-10-19T06:00:00Z',temperature:19,pty:1,sky:4,status:'valid'},
    ],
  };
}
test('운영 API 시간 구간에서 실제 현재 관측 + 향후 3시간 예보 기온을 표시',()=>{
  const hours=forecastHours(sample());
  expect(hours).toHaveLength(4);
  expect(hours.map(h=>h.temperature)).toEqual([17.4,18,19,19]);
  expect(hours.map(h=>h.sky)).toEqual([1,3,4,4]);
  expect(hours.map(h=>h.pty)).toEqual([0,0,0,1]);
});
test('0도는 정상 기온이고, 누락·무효 예보는 임의로 채우지 않는다',()=>{
  const weather=sample();
  weather.segments[1].temperature=0;
  weather.segments[2].status='stale';
  weather.segments[3].temperature=undefined;
  expect(forecastHours(weather).map(h=>h.temperature)).toEqual([17.4,0,undefined,undefined]);
});
test('현재 관측이 만료됐거나 온도 제공이 없으면 현행 온도를 예보값으로 대체하지 않는다',()=>{
  const weather=sample();
  weather.current!.status='stale';
  expect(forecastHours(weather).map(h=>h.temperature)).toEqual([undefined,18,19,19]);
  expect(forecastHours(null).every(h=>h.temperature===undefined)).toBe(true);
});
test('6시간을 한 구간으로 반환하는 로컬 합성 데이터도 각 시각에 매핑한다',()=>{
  const weather=sample();
  weather.is_test=true;
  weather.segments=[{start_at:'2026-10-19T02:00:00Z',end_at:'2026-10-19T08:00:00Z',
    temperature:22,pty:0,sky:1,status:'valid'}];
  expect(forecastHours(weather).map(h=>h.temperature)).toEqual([17.4,22,22,22]);
});
