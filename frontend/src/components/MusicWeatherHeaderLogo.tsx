/**
 * The centered MUSIC X WEATHER identity from the accepted public-home mockup.
 * Inline SVG keeps the sound wave and sunny weather mark sharp at every size.
 */
export function MusicWeatherHeaderLogo(){
  const bars=[8,14,22,34,44,51,39,28,20,13,7];
  return <span className="muther-header-logo" role="img" aria-label="MUSIC X WEATHER">
    <svg className="muther-header-logo-art" viewBox="0 0 410 60" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="muther-header-soundwave" x1="0" x2="1">
          <stop offset="0%" stopColor="#b1d9ff"/>
          <stop offset="70%" stopColor="#3078e9"/>
          <stop offset="100%" stopColor="#789ce7"/>
        </linearGradient>
        <linearGradient id="muther-header-sun" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#ffe9a6"/>
          <stop offset="100%" stopColor="#f99c2a"/>
        </linearGradient>
      </defs>
      <path d="M3 49C23 50 38 37 54 35C69 33 80 41 96 39" fill="none" stroke="#739bdb" strokeWidth="2.5" strokeLinecap="round"/>
      {bars.map((height,index)=><rect key={index} x={99+index*7} y={32-height/2} width="3.8" height={height} rx="1.9" fill="url(#muther-header-soundwave)"/>)}
      <path d="M182 39C195 45 207 49 218 42C231 31 243 34 255 43" fill="none" stroke="#8db4ee" strokeWidth="2.8" strokeLinecap="round"/>
      <circle cx="252" cy="25" r="16" fill="url(#muther-header-sun)"/>
      <g stroke="#eeaa54" strokeWidth="2.4" strokeLinecap="round">
        <path d="M252 1v5M252 44v5M229 25h5M270 25h6M236 9l4 4M265 38l4 4M268 9l-4 4M236 40l4-4"/>
      </g>
      <path d="M227 45c2-10 15-13 23-6c6-6 15-4 19 2c8-1 13 5 12 11h-55c-6-1-7-5-5-9z" fill="#eaf4ff" opacity=".94"/>
      <path d="M273 45C284 47 288 29 302 33C317 37 315 48 329 44C342 39 342 31 354 35C367 41 376 46 407 42" fill="none" stroke="#253c75" strokeWidth="2.8" strokeLinecap="round"/>
      <circle cx="315" cy="34" r="4.1" fill="#3c82ec"/>
    </svg>
    <span className="muther-header-logo-type" aria-hidden="true">
      <span className="muther-header-logo-music">MUSIC</span>
      <span className="muther-header-logo-x">X</span>
      <span className="muther-header-logo-weather">WEATHER</span>
    </span>
  </span>;
}
