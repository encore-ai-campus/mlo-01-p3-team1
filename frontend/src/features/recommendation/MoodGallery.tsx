import {useState} from 'react';

type Mood={key:string;label:string;title:string;description:string;image:string;icon:string};
export const moods:Mood[]=[
  {key:'sunny',label:'맑음',title:'햇살 좋은 오후',description:'기분이 가벼워지는 밝은 음악',image:'/muther/sunny.jpg',icon:'☀'},
  {key:'sunset',label:'노을',title:'저녁 노을과 함께',description:'하루를 마무리하는 감성 음악',image:'/muther/sunset.jpg',icon:'☀'},
  {key:'rain',label:'비',title:'비 오는 날의 온도',description:'차분히 스며드는 사운드',image:'/muther/rain.jpg',icon:'☂'},
  {key:'cloudy',label:'흐림',title:'구름 낀 하루',description:'생각이 깊어지는 포근한 음악',image:'/muther/cloudy.jpg',icon:'☁'},
  {key:'snow',label:'눈',title:'조용히, 하얀 하루',description:'따뜻함이 필요한 겨울의 음악',image:'/muther/snow.jpg',icon:'❄'},
  {key:'night',label:'밤',title:'도시의 밤',description:'가만히 듣기 좋은 밤의 음악',image:'/muther/night.jpg',icon:'☾'},
];
const tabs=[{key:'all',label:'전체'},{key:'sunny',label:'맑음'},{key:'cloudy',label:'흐림'},
  {key:'rain',label:'비'},{key:'snow',label:'눈'},{key:'night',label:'밤'}];

export function MoodGallery(){
  const [active,setActive]=useState('all');
  const visible=active==='all'?moods:moods.filter(row=>row.key===active);
  return <section className="muther-moods" id="playlist-showcase" aria-labelledby="muther-moods-title">
    <header className="muther-moods-header">
      <div>
        <span className="muther-section-eyebrow">WEATHER × MUSIC</span>
        <h2 id="muther-moods-title">지금, 이 날씨의 추천 플레이리스트</h2>
        <p>날씨별 음악 분위기 미리보기 · 실제 선곡표는 아래에서 만들 수 있어요.</p>
      </div>
      <div className="muther-mood-tabs" role="group" aria-label="날씨별 분위기 필터">
        {tabs.map(tab=><button type="button" key={tab.key} aria-pressed={active===tab.key}
          onClick={()=>setActive(tab.key)}>{tab.label}</button>)}
      </div>
    </header>
    <div className="muther-mood-cards" aria-live="polite">
      {visible.map(mood=><article className="muther-mood-card" key={mood.key}
        style={{backgroundImage:'linear-gradient(0deg, rgba(3,15,43,.91), rgba(3,15,43,.04) 65%), url("'+mood.image+'")'}}>
        <div className="muther-mood-meta"><span aria-hidden="true">{mood.icon}</span> {mood.label}</div>
        <div className="muther-mood-info"><h3>{mood.title}</h3><p>{mood.description}</p></div>
      </article>)}
    </div>
  </section>;
}
