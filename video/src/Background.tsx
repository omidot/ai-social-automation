import { interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import { T } from './theme';

const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3'/%3E%3C/filter%3E%3Crect width='220' height='220' filter='url(%23n)' opacity='0.55'/%3E%3C/svg%3E\")";

export const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames: D, width: W, height: H } = useVideoConfig();
  const p = frame / D;
  const drift = interpolate(p, [0, 1], [0, 1]);
  const gx = Math.sin(drift * Math.PI * 2) * 16;
  const gy = Math.cos(drift * Math.PI * 2) * 12;
  const wedge = interpolate(p, [0, 1], [0, 26]);

  return (
    <>
      <div style={{ position: 'absolute', inset: 0, background: T.bg }} />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(120% 78% at 50% 40%, ${T.bgHi} 0%, #E6E4E1 52%, ${T.bgLo} 100%)`,
        }}
      />
      <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
        <defs>
          <linearGradient id="wg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#242424" />
            <stop offset="100%" stopColor="#0C0C0C" />
          </linearGradient>
          <clipPath id="gridClip">
            <rect x={W * 0.13} y={H * 0.27} width={W * 0.8} height={H * 0.44} />
          </clipPath>
        </defs>

        {/* nêm đen 2 góc — đa giác LÕM để có rãnh khuyết như bản tham chiếu */}
        <g transform={`translate(${-wedge * 0.6} ${-wedge * 0.4})`}>
          <polygon
            points={`0,${H * 0.012} ${W * 0.62},${H * 0.018} ${W * 0.115},${H * 0.245} ${W * 0.055},${H * 0.115}`}
            fill="url(#wg)"
          />
        </g>
        <g transform={`translate(${wedge * 0.6} ${wedge * 0.4})`}>
          <polygon
            points={`${W},${H * 0.988} ${W * 0.38},${H * 0.982} ${W * 0.885},${H * 0.755} ${W * 0.945},${H * 0.885}`}
            fill="url(#wg)"
          />
        </g>

        {/* lưới đứt nét kiểu công cụ thiết kế */}
        <g clipPath="url(#gridClip)" opacity={0.5} transform={`translate(${gx} ${gy})`}>
          {[0.18, 0.45, 0.72, 0.99].map((f) => (
            <line key={`v${f}`} x1={W * f} y1={H * 0.24} x2={W * f} y2={H * 0.75} stroke={T.grid} strokeWidth={2} strokeDasharray="12 14" />
          ))}
          {[0.3, 0.42, 0.54, 0.66].map((f) => (
            <line key={`h${f}`} x1={W * 0.1} y1={H * f} x2={W * 0.96} y2={H * f} stroke={T.grid} strokeWidth={2} strokeDasharray="12 14" />
          ))}
        </g>
      </svg>

      <div style={{ position: 'absolute', inset: 0, backgroundImage: GRAIN, backgroundSize: '220px 220px', opacity: 0.06, mixBlendMode: 'multiply' }} />
      <div style={{ position: 'absolute', inset: 0, boxShadow: 'inset 0 0 240px 20px rgba(62,60,57,0.20)' }} />
    </>
  );
};
