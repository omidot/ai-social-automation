import React from 'react';
import { AbsoluteFill } from 'remotion';
import { DARK, type Pal } from './palette';

/**
 * Nền tĩnh phẳng (không video): màu tối trơn + vân chéo mờ + một chút ánh
 * sáng góc trên phải — đúng phong cách tham chiếu (ainius.net), thay cho
 * video nền chuyển động trước đây.
 */
export const palAt = (_t: number): Pal => DARK;

const HATCH =
  'repeating-linear-gradient(45deg, rgba(255,255,255,0.035) 0px, rgba(255,255,255,0.035) 1px, transparent 1px, transparent 26px), ' +
  'repeating-linear-gradient(-45deg, rgba(255,255,255,0.035) 0px, rgba(255,255,255,0.035) 1px, transparent 1px, transparent 26px)';

const GLOW = 'radial-gradient(60% 40% at 82% 8%, rgba(255,145,95,0.12) 0%, rgba(255,145,95,0) 60%)';

export const BgVideo: React.FC = () => (
  <AbsoluteFill style={{ background: '#0A0A0A' }}>
    <AbsoluteFill style={{ background: HATCH }} />
    <AbsoluteFill style={{ background: GLOW }} />
  </AbsoluteFill>
);
