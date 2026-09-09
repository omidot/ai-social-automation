import React from 'react';
import { AbsoluteFill, interpolate, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { LIGHT, DARK, type Pal } from './palette';

/** Nền cố định — một video xuyên suốt mọi clip của kênh. */
export const BG = [
  { from: 0.0, file: 'bg.mp4', pal: DARK, rate: 1 },
];

const FADE = 14; // số frame chuyển cảnh giữa hai nền

export const palAt = (t: number): Pal => {
  let p = BG[0].pal;
  for (const b of BG) if (t >= b.from) p = b.pal;
  return p;
};

export const BgVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  let idx = 0;
  BG.forEach((b, i) => { if (t >= b.from) idx = i; });
  const cur = BG[idx];
  const prev = idx > 0 ? BG[idx - 1] : null;
  const into = frame - cur.from * fps;
  const mix = interpolate(into, [0, FADE], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  const layer = (b: typeof BG[number], opacity: number, key: string) => (
    <AbsoluteFill key={key} style={{ opacity }}>
      <OffthreadVideo
        src={staticFile(b.file)}
        muted
        loop
        playbackRate={b.rate}
        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
      />
    </AbsoluteFill>
  );

  return (
    <AbsoluteFill>
      {prev && mix < 1 ? layer(prev, 1, 'prev') : null}
      {layer(cur, mix, 'cur')}
      {/* lớp phủ — thứ duy nhất bảo đảm chữ luôn đọc được trên nền video động */}
      <AbsoluteFill style={{ background: cur.pal.scrim }} />
    </AbsoluteFill>
  );
};
