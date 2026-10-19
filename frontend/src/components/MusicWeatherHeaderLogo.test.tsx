import {describe,expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {MusicWeatherHeaderLogo} from './MusicWeatherHeaderLogo';

describe('MUSIC X WEATHER header branding',()=>{
  it('renders the large screen-reader-labelled brand with weather and sound-wave artwork',()=>{
    const html=renderToStaticMarkup(<MusicWeatherHeaderLogo/>);
    expect(html).toContain('aria-label="MUSIC X WEATHER"');
    expect(html).toContain('muther-header-logo-art');
    expect(html).toContain('muther-header-logo-music');
    expect(html).toContain('muther-header-logo-x');
    expect(html).toContain('muther-header-logo-weather');
    expect(html).toContain('>MUSIC</span>');
    expect(html).toContain('>WEATHER</span>');
    expect(html).toContain('linearGradient');
  });
});
