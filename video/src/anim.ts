import { interpolate, spring } from 'remotion';

export type Motion = 'rise' | 'fall' | 'slideL' | 'slideR' | 'pop' | 'slam' | 'wipe' | 'spread';
export type Exit = 'up' | 'down' | 'shrink' | 'dissolve' | 'wipeOut';

const CLAMP = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

/** Mỗi kiểu vào có spring riêng — đó là thứ làm chúng KHÁC NHAU, không chỉ khác hướng */
const SPRING: Record<Motion, { damping: number; stiffness: number; mass: number }> = {
  rise:   { damping: 11,  stiffness: 200, mass: 0.72 },  // nảy vọt lố
  fall:   { damping: 13,  stiffness: 240, mass: 0.6 },   // rơi xuống, dứt khoát
  slideL: { damping: 16,  stiffness: 150, mass: 0.8 },   // trượt mượt, không nảy
  slideR: { damping: 16,  stiffness: 150, mass: 0.8 },
  pop:    { damping: 8.5, stiffness: 230, mass: 0.7 },   // nảy mạnh nhất
  slam:   { damping: 22,  stiffness: 300, mass: 1.0 },   // đập vào, dừng phắt
  wipe:   { damping: 200, stiffness: 120, mass: 0.7 },   // tuyến tính, không nảy
  spread: { damping: 200, stiffness: 90,  mass: 0.8 },   // giãn chữ, chậm rãi
};

export type AnimOut = {
  s: number; local: number; outP: number; opacity: number;
  transform: string; filter?: string; clipPath?: string; letterSpacing?: string;
};

export const useMotion = (
  frame: number, fps: number, startSec: number, leaving: number, exitFrames: number,
  motion: Motion, exit: Exit, delay = 0,
): AnimOut => {
  const local = frame - startSec * fps - delay;
  const s = spring({ frame: local, fps, config: SPRING[motion] });
  const outP = interpolate(leaving, [0, exitFrames], [0, 1], CLAMP);

  let x = 0, y = 0, scale = 1, rot = 0, blur = 0;
  let clipPath: string | undefined;
  let letterSpacing: string | undefined;
  // wipe/spread hiện ngay rồi mới lộ dần — nếu fade nữa thì mất hiệu ứng
  let appear = interpolate(local, [0, 5], [0, 1], CLAMP);

  switch (motion) {
    case 'rise':
      y = interpolate(s, [0, 1], [46, 0]); scale = interpolate(s, [0, 1], [0.8, 1]);
      blur = interpolate(local, [0, 9], [14, 0], CLAMP); break;
    case 'fall':
      y = interpolate(s, [0, 1], [-58, 0]); scale = interpolate(s, [0, 1], [1.1, 1]);
      blur = interpolate(local, [0, 8], [10, 0], CLAMP); break;
    case 'slideL':
      x = interpolate(s, [0, 1], [-130, 0]); rot = interpolate(s, [0, 1], [-3.5, 0]);
      blur = interpolate(local, [0, 8], [9, 0], CLAMP); break;
    case 'slideR':
      x = interpolate(s, [0, 1], [130, 0]); rot = interpolate(s, [0, 1], [3.5, 0]);
      blur = interpolate(local, [0, 8], [9, 0], CLAMP); break;
    case 'pop':
      scale = interpolate(s, [0, 1], [0.32, 1]); y = interpolate(s, [0, 1], [18, 0]);
      blur = interpolate(local, [0, 7], [8, 0], CLAMP); break;
    case 'slam':
      scale = interpolate(s, [0, 1], [1.45, 1]);
      blur = interpolate(local, [0, 9], [26, 0], CLAMP); break;
    case 'wipe':
      clipPath = `inset(0 ${interpolate(s, [0, 1], [100, 0])}% 0 0)`;
      appear = interpolate(local, [0, 1], [0, 1], CLAMP); break;
    case 'spread':
      letterSpacing = `${interpolate(s, [0, 1], [0.16, -0.02])}em`;
      blur = interpolate(local, [0, 11], [12, 0], CLAMP);
      appear = interpolate(local, [0, 8], [0, 1], CLAMP); break;
  }

  switch (exit) {
    case 'up':       y -= outP * 26; scale *= 1 - outP * 0.04; blur += outP * 6; break;
    case 'down':     y += outP * 34; scale *= 1 - outP * 0.04; blur += outP * 6; break;
    case 'shrink':   scale *= 1 - outP * 0.16; blur += outP * 3; break;
    case 'dissolve': blur += outP * 18; break;
    case 'wipeOut':  clipPath = `inset(0 0 0 ${outP * 100}%)`; break;
  }
  const fade = exit === 'wipeOut' ? interpolate(outP, [0.85, 1], [1, 0], CLAMP) : 1 - outP;

  return {
    s, local, outP,
    opacity: appear * fade,
    transform: `translate(${x}px, ${y}px) rotate(${rot}deg) scale(${scale})`,
    filter: blur > 0.15 ? `blur(${blur}px)` : undefined,
    clipPath,
    letterSpacing,
  };
};
