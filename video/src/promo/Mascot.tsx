import React from 'react';
import { Img, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { prog, power3Out, C } from './theme';

/**
 * LINH VẬT 3D kiểu đất sét, dither 1-bit, dựng từ logo kênh.
 *
 * File ảnh được nướng sẵn 2 màu bằng src/pipeline/video/dither.py rồi đặt ở
 * public/promo/mascot.png. CHƯA CÓ FILE thì component tự lặng lẽ không vẽ gì
 * -- nhờ vậy toàn bộ bản dựng vẫn chạy và duyệt được trong lúc chờ logo, và
 * lúc có logo chỉ cần thả file vào đúng chỗ, không phải sửa một dòng code.
 */

export type MascotPose = 'peek' | 'travel' | 'wink';

export const Mascot: React.FC<{
  file?: string | null;
  pose: MascotPose;
  at: number;
  size?: number;
  style?: React.CSSProperties;
  /** Mốc nháy mắt, chỉ dùng cho pose 'wink'. */
  winkAt?: number;
}> = ({ file, pose, at, size = 340, style, winkAt }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  // Nhô lên từ dưới mép; travel thì trôi ngang rất chậm.
  const rise = power3Out(prog(t, at, 0.7));
  const drift = pose === 'travel' ? Math.sin((t - at) * 0.6) * 18 : 0;
  const bob = Math.sin((t - at) * 1.9) * 6 * rise;

  // Nháy mắt: mí sập xuống rồi mở, gọn trong ~0.22s.
  const wp = winkAt == null ? 0 : prog(t, winkAt, 0.22);
  const lid = wp > 0 && wp < 1 ? Math.sin(wp * Math.PI) : 0;

  if (!file) return null;

  return (
    <div style={{
      position: 'absolute',
      width: size,
      opacity: rise,
      transform: `translate(${drift.toFixed(2)}px, ${((1 - rise) * 140 - bob).toFixed(2)}px)`,
      ...style,
    }}>
      <div style={{ position: 'relative' }}>
        <Img src={staticFile(file)}
             style={{ width: '100%', height: 'auto', display: 'block' }} />
        {lid > 0 ? (
          /* mí mắt sập -- một vệt mực ngang đúng 2 màu, không glow */
          <div style={{
            position: 'absolute', left: '26%', width: '20%',
            top: '34%', height: `${(lid * 9).toFixed(1)}%`,
            background: C.ink, borderRadius: 3,
          }} />
        ) : null}
      </div>
    </div>
  );
};

/** Bong bóng thoại nhỏ cạnh linh vật ("psst"). */
export const Bubble: React.FC<{
  text: string; at: number; hand: string; style?: React.CSSProperties;
}> = ({ text, at, hand, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = power3Out(prog(frame / fps, at, 0.42));
  return (
    <div style={{
      position: 'absolute',
      background: '#FFFFFF', borderRadius: 20,
      padding: '12px 26px 16px',
      boxShadow: '0 12px 30px rgba(20,26,34,0.2)',
      opacity: p,
      transform: `scale(${(0.72 + 0.28 * p).toFixed(3)}) rotate(-5deg)`,
      ...style,
    }}>
      <span style={{ fontFamily: hand, fontSize: 46, color: C.ink, lineHeight: 1 }}>
        {text}
      </span>
    </div>
  );
};
