import {useId} from 'react';

type Name='home'|'pin'|'eye'|'eye-off'|'thumb-up'|'thumb-down'|'music'|'arrow';
const paths:Record<Name,string>={
  home:'M3 10.5 12 3l9 7.5M5.5 9v11h5v-6h3v6h5V9',
  pin:'M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0ZM14 10a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z',
  eye:'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  'eye-off':'m3 3 18 18M10.5 5.1 12 5c6.5 0 10 7 10 7a23 23 0 0 1-3 3.7M6.2 6.2A23 23 0 0 0 2 12s3.5 7 10 7c1.8 0 3.4-.5 4.8-1.2M9.9 9.9a3 3 0 0 0 4.2 4.2',
  'thumb-up':'M7 10v11H3V10h4Zm0 0 5-8c3 0 2 5 1 7h6a2 2 0 0 1 2 2l-2 8a2 2 0 0 1-2 2H7',
  'thumb-down':'M7 14V3H3v11h4Zm0 0 5 8c3 0 2-5 1-7h6a2 2 0 0 0 2-2l-2-8a2 2 0 0 0-2-2H7',
  music:'M9 18V5l12-3v13M9 8l12-3M9 18a3 3 0 1 1-3-3c1.7 0 3 1.3 3 3Zm12-3a3 3 0 1 1-3-3c1.7 0 3 1.3 3 3Z',
  arrow:'m9 5 7 7-7 7',
};
export function Icon({name,className=''}:{name:Name;className?:string}){
  return <svg className={`icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]}/></svg>;
}
export function WeatherIcon({pty,sky,className=''}:{pty?:number;sky?:number|null;className?:string}){
  const id=useId();const known=pty!==undefined;
  const rainy=pty!==undefined&&[1,2,4,5,6].includes(pty),snowy=pty!==undefined&&[2,3,6,7].includes(pty);
  const clear=pty===0&&sky===1;
  return <svg className={`weather-icon ${className}`} viewBox="0 0 80 72" aria-hidden="true">
    <defs><linearGradient id={id} x2=".8" y2="1"><stop stopColor="#e5f4ff"/><stop offset="1" stopColor="#83adcb"/></linearGradient></defs>
    {clear?<><circle cx="39" cy="29" r="17" fill="#ffc554"/>{[0,45,90,135,180,225,270,315].map(a=><path key={a} d="M39 3v5" stroke="#f0b442" strokeWidth="3" strokeLinecap="round" transform={`rotate(${a} 39 29)`}/>)}</>:<path d="M19 52a15 15 0 0 1-1-30 21 21 0 0 1 40-1 16 16 0 0 1 1 31Z" fill={`url(#${id})`} stroke="#b7d1e6"/>}
    {!known&&<text x="40" y="43" textAnchor="middle" fill="#7187ac" fontSize="25">?</text>}
    {rainy&&[26,42,58].map(x=><path key={x} d={`m${x} 57-4 7`} stroke="#168cff" strokeWidth="4" strokeLinecap="round"/>)}
    {snowy&&[28,52].map(x=><text key={x} x={x} y="70" textAnchor="middle" fill="#358edc" fontSize="17">✳</text>)}
  </svg>;
}
