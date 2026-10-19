import {expect,test} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {RegionPicker,regionHierarchy,type RegionOption} from '../src/features/region-weather/RegionPicker';
import {Header} from '../src/components/Header';
import {HeroBanner} from '../src/features/recommendation/HeroBanner';
import {weatherLabel} from '../src/features/region-weather/WeatherPanel';
import {MoodGallery} from '../src/features/recommendation/MoodGallery';

const rows:RegionOption[]=[
  {region_id:'g1',name:'서울특별시 구로구 구로제1동',province:'서울특별시',district:'구로구',locality:'구로제1동'},
  {region_id:'g2',name:'서울특별시 구로구 구로제2동',province:'서울특별시',district:'구로구',locality:'구로제2동'},
  {region_id:'s1',name:'서울특별시 중구 명동',province:'서울특별시',district:'중구',locality:'명동'},
  {region_id:'b1',name:'부산광역시 중구 중앙동',province:'부산광역시',district:'중구',locality:'중앙동'},
  {region_id:'b2',name:'부산광역시 중구 중앙동',province:'부산광역시',district:'중구',locality:'중앙동'},
];
test('지역 계층 목록은 상위 지역에 따라 분리하고 원래 ID를 보존한다',()=>{
  expect(regionHierarchy(rows,'','').provinces).toEqual(['부산광역시','서울특별시']);
  expect(regionHierarchy(rows,'서울특별시','').districts).toEqual(['구로구','중구']);
  expect(regionHierarchy(rows,'서울특별시','구로구').localities.map(x=>x.region_id)).toEqual(['g1','g2']);
  expect(regionHierarchy(rows,'부산광역시','중구').localities.map(x=>x.region_id)).toEqual(['b1','b2']);
  expect(regionHierarchy(rows,'서울특별시','중구').localities.map(x=>x.region_id)).toEqual(['s1']);
  expect(regionHierarchy(rows,'부산광역시','구로구').localities).toEqual([]);
});
test('시·도, 시·군·구, 읍·면·동은 별도 라벨을 가지며 미선택 상태를 막는다',()=>{
  const html=renderToStaticMarkup(createElement(RegionPicker,{region:'',regions:rows,locked:false,onRegion:()=>{}}));
  expect(html).toContain('aria-label="시·도"');
  expect(html).toContain('aria-label="시·군·구"');
  expect(html).toContain('aria-label="읍·면·동"');
  expect(html).toContain('선택한 지역으로 날씨 변경');
  expect(html).toContain('disabled=""');
  expect(html).not.toContain('동네 이름을 검색해 주세요');
});
test('변경된 슬로건, 기존 페이지 이동 주소와 사용 가능한 선곡 버튼을 표시한다',()=>{
  const header=renderToStaticMarkup(createElement(Header,{currentPage:'playlist',onNavigate:()=>{}}));
  expect(header).toContain('오늘의 날씨를 들어보세요');
  expect(header).toContain('href="/playlist"');
  expect(header).toContain('aria-current="page"');
  const hero=renderToStaticMarkup(createElement(HeroBanner,{onCreate:()=>{}}));
  expect(hero).toContain('오늘의 선곡표 만들기');
  expect(hero).toContain('WEATHER');
  expect(renderToStaticMarkup(createElement(MoodGallery))).toContain('실제 선곡표는 아래에서 만들 수 있어요');
});
test('없는 예보를 임의로 채우지 않는다',()=>{
  expect(weatherLabel()).toBe('확인 불가');
  expect(weatherLabel(0,1)).toBe('맑음');
  expect(weatherLabel(1,1)).toBe('비');
});