import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { ICONS } from './icons';
import { usePal } from './palette';

/**
 * Khối 3D thật: mỗi lớp là một bản sao của bóng khối, đẩy lùi theo trục Z trong
 * một container preserve-3d. Vì vậy khi rotateY, ta NHÌN THẤY cạnh bên của khối —
 * không phải mẹo đổ bóng giả 2D.
 */
export const Extruded: React.FC<{
  icon: string;
  size: number;
  depth?: number;
  layers?: number;
  rx: number;
  ry: number;
  rz?: number;
  light?: boolean;   // dùng trên card nền đen
  solid?: boolean;   // khối đặc tối — dùng cho vật thể nền trên nền sáng
}> = ({ icon, size, depth = 34, layers = 26, rx, ry, rz = 0, light, solid }) => {
  const def = ICONS[icon] ?? ICONS.cube;
  const step = depth / layers;
  const topFill = solid ? '#3A3937' : light ? '#F2F2F0' : '#FAFAF9';
  const topInk = solid ? '#151413' : light ? '#0A0A0A' : '#111111';

  return (
    <div style={{ perspective: 1100, width: size, height: size }}>
      <div style={{ transformStyle: 'preserve-3d', width: size, height: size, transform: `rotateX(${rx}deg) rotateY(${ry}deg) rotateZ(${rz}deg)` }}>
        {/* thân khối: lớp càng sâu càng tối, tạo chuyển sắc như vật thể có khối */}
        {Array.from({ length: layers }).map((_, i) => {
          const t = i / (layers - 1);
          const v = Math.round(interpolate(t, [0, 1], [solid ? 58 : light ? 118 : 96, solid ? 20 : light ? 26 : 14]));
          return (
            <svg
              key={i}
              viewBox="0 0 24 24"
              width={size}
              height={size}
              style={{ position: 'absolute', inset: 0, transform: `translateZ(${-i * step}px)` }}
            >
              {def.body(`rgb(${v},${v},${v - 1})`)}
            </svg>
          );
        })}
        {/* mặt trước có chi tiết */}
        <svg viewBox="0 0 24 24" width={size} height={size} style={{ position: 'absolute', inset: 0, transform: 'translateZ(0.6px)' }}>
          {def.face(topFill, topInk)}
        </svg>
      </div>
    </div>
  );
};

/** Icon 3D của chương — góc dưới trái, bật lên mỗi khi đổi chương */
export const Icon3D: React.FC<{ icon: string; since: number; light?: boolean }> = ({ icon, since, light }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: since, fps, config: { damping: 12, stiffness: 170, mass: 0.8 } });
  const t = frame / fps;

  const ry = Math.sin(t * 0.62) * 26 + interpolate(s, [0, 1], [-46, 0]);
  const rx = -13 + Math.sin(t * 0.43) * 6;
  const bob = Math.sin(t * 0.9) * 9;

  return (
    <div style={{
      position: 'absolute', left: 96, bottom: 178,
      opacity: interpolate(s, [0, 1], [0, 1]),
      transform: `translateY(${bob + interpolate(s, [0, 1], [40, 0])}px) scale(${interpolate(s, [0, 1], [0.55, 1])})`,
    }}>
      <Extruded icon={icon} size={252} depth={52} layers={32} rx={rx} ry={ry} light={light} />
      {/* bóng tiếp đất */}
      <div style={{
        position: 'absolute', left: 40, right: 40, bottom: -40, height: 30, borderRadius: '50%',
        background: light ? 'rgba(255,255,255,0.10)' : 'rgba(30,29,27,0.30)',
        filter: 'blur(21px)', transform: `scaleX(${1 - bob / 130})`,
      }} />
    </div>
  );
};

/** Vật thể 3D nền — to, mờ, xoay chậm suốt video để khung hình có chiều sâu */
export const Ambient3D: React.FC = () => {
  const pal = usePal();
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const t = frame / fps;
  const p = frame / durationInFrames;

  return (
    <>
      {/* khối lớn góc trên phải — khối đặc TỐI mới nổi được trên nền sáng */}
      <div style={{
        position: 'absolute', right: 40, top: 322, opacity: pal.dark ? 0.13 : 0.15,
        transform: `translateY(${Math.sin(t * 0.33) * 26}px)`,
      }}>
        <Extruded icon="cube" size={360} depth={116} layers={32} solid={!pal.dark} light={pal.dark} rx={-20 + Math.sin(t * 0.25) * 8} ry={t * 13} rz={interpolate(p, [0, 1], [-8, 8])} />
      </div>

      {/* vòng tròn mảnh phía dưới, nghiêng trong không gian */}
      <div style={{ position: 'absolute', left: -110, bottom: 430, opacity: pal.dark ? 0.16 : 0.12, perspective: 900 }}>
        <div style={{ transformStyle: 'preserve-3d', transform: `rotateX(64deg) rotateZ(${t * 9}deg)` }}>
          {Array.from({ length: 16 }).map((_, i) => (
            <svg key={i} width={470} height={470} viewBox="0 0 100 100" style={{ position: 'absolute', inset: 0, transform: `translateZ(${-i * 1.7}px)` }}>
              <circle cx={50} cy={50} r={40} fill="none" stroke={pal.dark ? `rgb(${228 - i * 9},${228 - i * 9},${226 - i * 9})` : `rgb(${92 - i * 5},${92 - i * 5},${91 - i * 5})`} strokeWidth={5} />
            </svg>
          ))}
        </div>
      </div>
    </>
  );
};
