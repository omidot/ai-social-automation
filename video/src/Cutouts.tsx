import React from 'react';
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';

/**
 * B-roll dạng "cutout giấy dán" kiểu Vox — ảnh thật đã xoá nền + viền giấy trắng
 * (xử lý bằng vox/process_cutout.py), bay vào góc màn hình đúng lúc từ khoá được đọc.
 * KHÔNG đổi nền video (BgVideo giữ nguyên) — đây chỉ là lớp B-roll chồng lên trên.
 */
type Corner = 'tl' | 'tr' | 'bl' | 'br' | 'bc';
type Variant = 'grow' | 'punch' | 'rise' | 'flip';

type Cutout = {
  file: string; at: number; dur: number; corner: Corner; w: number;
  rotate: number; variant: Variant;
};

export const CUTOUTS: Cutout[] = [
  { file: 'cutouts/bulb.png',       at: 1.95,  dur: 3.35, corner: 'tr', w: 300, rotate: -6,  variant: 'grow' },
  { file: 'cutouts/robothand.png',  at: 8.75,  dur: 3.1,  corner: 'tl', w: 300, rotate: 5,   variant: 'punch' },
  { file: 'cutouts/moon.png',       at: 23.55, dur: 1.65, corner: 'tr', w: 260, rotate: -4,  variant: 'rise' },
  { file: 'cutouts/robotA.png',     at: 24.7,  dur: 1.35, corner: 'bl', w: 260, rotate: -7,  variant: 'punch' },
  { file: 'cutouts/robotB.png',     at: 25.25, dur: 1.55, corner: 'br', w: 270, rotate: 6,   variant: 'flip' },
  { file: 'cutouts/robotC.png',     at: 26.4,  dur: 2.0,  corner: 'bc', w: 340, rotate: -3,  variant: 'grow' },
  { file: 'cutouts/phone.png',      at: 28.85, dur: 2.6,  corner: 'tr', w: 300, rotate: 5,   variant: 'rise' },
  { file: 'cutouts/user1.png',      at: 33.25, dur: 3.6,  corner: 'bl', w: 340, rotate: -5,  variant: 'punch' },
  { file: 'cutouts/skyscraper.png', at: 38.75, dur: 2.4,  corner: 'tr', w: 320, rotate: 4,   variant: 'flip' },
];

const cornerStyle = (c: Corner, w: number): React.CSSProperties => {
  switch (c) {
    case 'tl': return { top: 190, left: -34 };
    case 'tr': return { top: 190, right: -34 };
    case 'bl': return { bottom: 90, left: -34 };
    case 'br': return { bottom: 90, right: -34 };
    case 'bc': return { bottom: 76, left: '50%', transform: `translateX(-50%)` };
  }
};

const CutoutView: React.FC<{ c: Cutout }> = ({ c }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = frame - c.at * fps;
  const outAt = c.dur * fps - 8;
  const s = spring({ frame: local, fps, config: { damping: 13, stiffness: 190, mass: 0.7 } });
  const outP = interpolate(local, [outAt, outAt + 8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const opacity = interpolate(local, [0, 5], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) * (1 - outP);

  // độ lắc/thở nhẹ liên tục sau khi "đáp" xuống — tránh cảm giác ảnh cứng đơ
  const idle = Math.sin((frame / fps) * 2.1 + c.at) * 3;

  let scale = 1, rotate = c.rotate, ty = 0;
  if (c.variant === 'grow') {
    scale = interpolate(s, [0, 1], [0.3, 1]);
    rotate = c.rotate + interpolate(s, [0, 1], [14, 0]);
  } else if (c.variant === 'punch') {
    scale = interpolate(s, [0, 0.6, 1], [0.5, 1.12, 1]);
  } else if (c.variant === 'rise') {
    ty = interpolate(s, [0, 1], [70, 0]);
    scale = interpolate(s, [0, 1], [0.85, 1]);
  } else if (c.variant === 'flip') {
    rotate = c.rotate + interpolate(s, [0, 1], [-130, 0]);
    scale = interpolate(s, [0, 1], [0.6, 1]);
  }

  return (
    <div
      style={{
        position: 'absolute', width: c.w, ...cornerStyle(c.corner, c.w),
        opacity,
        transform: `${c.corner === 'bc' ? 'translateX(-50%) ' : ''}translateY(${ty - outP * 40 + idle}px) rotate(${rotate + idle * 0.5}deg) scale(${scale * (1 - outP * 0.08)})`,
        filter: 'drop-shadow(0 18px 30px rgba(0,0,0,0.45))',
      }}
    >
      <Img src={staticFile(c.file)} style={{ width: '100%', height: 'auto', display: 'block' }} />
    </div>
  );
};

export const Cutouts: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  return (
    <>
      {CUTOUTS.filter((c) => t >= c.at - 0.15 && t < c.at + c.dur).map((c) => (
        <CutoutView key={c.file} c={c} />
      ))}
    </>
  );
};
