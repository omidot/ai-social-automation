import React from 'react';
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { usePal } from './palette';

/**
 * Ảnh chụp màn hình thật, mỗi ảnh gắn với đúng TỪ KHÓA đang được đọc.
 * `at` = giây bắt đầu, `dur` = thời gian ở lại.
 */
export const SHOTS = [
  { at: 20.1, dur: 3.0, file: 'shots/claude-code.png', src: 'claude.com/product/claude-code', key: 'vào Claude Code' },
];

const W = 872;                      // to hơn hẳn bản trước (690)
const H = Math.round(W / 1.553);    // khớp tỉ lệ khung chụp 1180×760

const Shot: React.FC<{ shot: typeof SHOTS[number]; ff: string }> = ({ shot, ff }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const local = frame - shot.at * fps;
  const quick = shot.dur < 2;                       // ảnh chớp nhanh thì vào dứt khoát hơn
  const outAt = shot.dur * fps - (quick ? 5 : 9);

  const s = spring({
    frame: local, fps,
    config: quick ? { damping: 20, stiffness: 260, mass: 0.6 } : { damping: 15, stiffness: 160, mass: 0.85 },
  });
  const x = interpolate(s, [0, 1], [quick ? 60 : 150, 0]);
  const ry = interpolate(s, [0, 1], [quick ? -12 : -22, -5]);
  const outP = interpolate(local, [outAt, outAt + (quick ? 5 : 9)], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const opacity = interpolate(local, [0, quick ? 3 : 5], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) * (1 - outP);

  return (
    <div style={{ position: 'absolute', top: 198, left: 0, right: 0, display: 'flex', justifyContent: 'center', perspective: 1700 }}>
      <div style={{
        transformStyle: 'preserve-3d',
        transform: `translateX(${x}px) translateY(${outP * -26}px) rotateY(${ry}deg) scale(${interpolate(s, [0, 1], [0.92, 1]) * (1 - outP * 0.05)})`,
        opacity,
      }}>
        <div style={{
          width: W, height: H, borderRadius: 18, overflow: 'hidden', position: 'relative',
          border: `3px solid ${pal.dark ? 'rgba(255,255,255,0.9)' : 'rgba(11,11,11,0.9)'}`,
          boxShadow: pal.dark ? '0 40px 90px rgba(0,0,0,0.78)' : '0 40px 90px rgba(24,23,21,0.48)',
          background: '#fff',
        }}>
          {/* phóng nhẹ + neo lên đầu trang: chữ trong ảnh to hơn, dễ đọc trên điện thoại */}
          <Img src={staticFile(shot.file)} style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top center', transform: 'scale(1.12)', transformOrigin: 'top center' }} />
          {/* ghi nguồn nằm TRONG ảnh, tránh đụng huy hiệu số của card */}
          <div style={{
            position: 'absolute', left: 0, right: 0, bottom: 0,
            padding: '30px 22px 13px',
            background: 'linear-gradient(to top, rgba(8,8,8,0.88) 0%, rgba(8,8,8,0) 100%)',
            fontFamily: ff, fontWeight: '700', fontSize: 23, letterSpacing: '0.11em',
            textTransform: 'uppercase', color: '#FFFFFF',
          }}>
            {shot.src}
          </div>
        </div>
      </div>
    </div>
  );
};

export const Shots: React.FC<{ ff: string }> = ({ ff }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  return (
    <>
      {SHOTS.filter((s) => t >= s.at - 0.2 && t < s.at + s.dur).map((s, i) => (
        <Shot key={`${s.file}-${i}`} shot={s} ff={ff} />
      ))}
    </>
  );
};

/** icon 3D nhường chỗ khi ảnh chụp đang hiện */
export const shotVisible = (t: number) => SHOTS.some((s) => t >= s.at - 0.2 && t < s.at + s.dur);

/**
 * Khi ảnh đang hiện, khối chữ phải TỤT XUỐNG để không bị khung ảnh đè lên
 * (rõ nhất là huy hiệu số của các card numeral). Trả về 0..1 có dốc lên/xuống
 * để chữ trượt mượt chứ không nhảy giật.
 */
export const shotPushAt = (t: number) => {
  let v = 0;
  for (const s of SHOTS) {
    const a = s.at - 0.2, b = s.at + s.dur;
    if (t < a || t >= b) continue;
    const inR = Math.min(1, (t - a) / 0.28);
    const outR = Math.min(1, (b - t) / 0.28);
    v = Math.max(v, Math.min(inR, outR));
  }
  return v;
};
