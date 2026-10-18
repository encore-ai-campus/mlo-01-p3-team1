import {expect,test} from 'vitest';
import {findRegions} from '../src/features/region-weather/regionSearch';
const rows=[
 {region_id:'a',name:'서울특별시 성동구 성수1가제1동',province:'서울특별시',district:'성동구',locality:'성수1가제1동'},
 {region_id:'b',name:'서울특별시 성동구 성수동',province:'서울특별시',district:'성동구',locality:'성수동'},
 {region_id:'c',name:'경기도 가평군 성수동',province:'경기도',district:'가평군',locality:'성수동'},
];
test('복수 지역어 검색과 동명이동 구분',()=>{
 expect(findRegions(rows,'  서울   성수 ').map(r=>r.region_id)).toEqual(['a','b']);
 expect(findRegions(rows,'경기 성수동').map(r=>r.region_id)).toEqual(['c']);
 expect(rows.map(r=>r.region_id)).toEqual(['a','b','c']);
});
test('정확한 동 이름을 우선하며 빈 검색과 미일치는 선택하지 않는다',()=>{
 expect(findRegions([...rows,{region_id:'d',name:'서울 성수동가',locality:'성수동가'}],'성수동').at(-1)?.region_id).toBe('d');
 expect(findRegions(rows,'  ')).toEqual([]);expect(findRegions(rows,'없는지역')).toEqual([]);
});
