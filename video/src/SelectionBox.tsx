import { interpolate, spring, useVideoConfig } from 'remotion';
import { Cursor } from './Cursor';
import { usePal } from './palette';

/** Khung chọn kiểu Figma: viền đứt nét + 4 chấm góc + con trỏ chuột */
export const SelectionBox: React.FC<{ since: number; leaving: number; mirror?: boolean; light?: boolean }> = ({
  since, leaving, mirror, light,
}) => {
  const { fps } = useVideoConfig();
  const pal = usePal();
  const s = spring({ frame: since, fps, config: { damping: 14, stiffness: 260, mass: 0.5 } });
  const snap = interpolate(s, [0, 1], [1.09, 1]);
  const appear = interpolate(since, [0, 4], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const opacity = appear * interpolate(leaving, [0, 4], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const H = 15;
  const ink = pal.boxInk;
  const rim = pal.boxRim;

  return (
    <div style={{ position: 'absolute', inset: -10, opacity, transform: `scale(${snap})`, pointerEvents: 'none' }}>
      <div style={{ position: 'absolute', inset: 0, border: `2.5px dashed ${ink}`, borderRadius: 2 }} />
      {[[0, 0], [1, 0], [0, 1], [1, 1]].map(([x, y]) => (
        <div
          key={`${x}${y}`}
          style={{
            position: 'absolute', width: H, height: H, background: ink, border: `2px solid ${rim}`,
            left: x ? '100%' : 0, top: y ? '100%' : 0, transform: 'translate(-50%,-50%)',
          }}
        />
      ))}
      <div
        style={{
          position: 'absolute',
          left: mirror ? 0 : '100%',
          top: '100%',
          transform: mirror ? 'translate(-46px, -4px) scaleX(-1)' : 'translate(-6px, -4px)',
        }}
      >
        <Cursor light={pal.dark} />
      </div>
    </div>
  );
};
