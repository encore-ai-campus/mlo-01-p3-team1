import {describe,it,expect} from 'vitest';
import {canonical} from './api';
describe('request condition equality',()=>{
  it('ignores selection ordering but detects changed groups and versions',()=>{
    expect(canonical({genre:['JAZZ','POP'],tempo:'auto'})).toBe(canonical({tempo:'auto',genre:['POP','JAZZ']}));
    expect(canonical({tempo:'slow'})).not.toBe(canonical({tempo:'auto'}));
    expect(canonical({option_version:'v1'})).not.toBe(canonical({option_version:'v2'}));
  });
});
