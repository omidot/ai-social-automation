import React, { useContext } from 'react';

export type Pal = {
  dark: boolean;
  ink: string;      // chữ chính
  ink2: string;     // chữ phụ
  gray: string;     // dòng accent
  panel: string;    // nền tấm card "invert"
  panelInk: string; // chữ trên tấm invert
  boxInk: string;   // viền + chấm khung chọn
  boxRim: string;   // viền ngoài chấm (tương phản ngược)
  scrim: string;    // lớp phủ đảm bảo chữ đọc được trên video
  shadow: string;   // đổ bóng chữ
};

/** nền SÁNG → chữ đen */
export const LIGHT: Pal = {
  dark: false,
  ink: '#0B0B0B',
  ink2: '#2E2D2B',
  gray: '#7E7C79',
  panel: '#0A0A0A',
  panelInk: '#FFFFFF',
  boxInk: '#0B0B0B',
  boxRim: '#FFFFFF',
  scrim: 'radial-gradient(78% 46% at 50% 48%, rgba(255,255,255,0.80) 0%, rgba(255,255,255,0.52) 55%, rgba(255,255,255,0.16) 100%)',
  shadow: '0 2px 26px rgba(255,255,255,0.55)',
};

/** nền TỐI → chữ trắng, tấm invert đảo thành trắng */
export const DARK: Pal = {
  dark: true,
  ink: '#FFFFFF',
  ink2: '#DEDEDC',
  gray: '#9E9E9B',
  panel: '#FAFAF8',
  panelInk: '#0A0A0A',
  boxInk: '#FFFFFF',
  boxRim: '#0A0A0A',
  scrim: 'radial-gradient(80% 48% at 50% 48%, rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.46) 56%, rgba(0,0,0,0.10) 100%)',
  shadow: '0 2px 30px rgba(0,0,0,0.72)',
};

export const PalCtx = React.createContext<Pal>(LIGHT);
export const usePal = () => useContext(PalCtx);
