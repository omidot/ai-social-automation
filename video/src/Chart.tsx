import React from 'react';
import { interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import { usePal } from './palette';
import { useMotion } from './anim';
import { Frame, shown, type P } from './layouts';
import { T } from './theme';

const W = 1080 - T.PAD * 2;

type ChartItem = { label?: string; value: number };

const LineChart: React.FC<{ items: ChartItem[]; unit: string; reveal: number; accent: string; ink: string }> = ({ items, unit, reveal, accent, ink }) => {
  const w = W, h = 420;
  const max = Math.max(...items.map((i) => i.value));
  const min = Math.min(0, ...items.map((i) => i.value));
  const span = max - min || 1;
  const pts = items.map((it, i) => {
    const x = (i / (items.length - 1)) * (w - 40) + 20;
    const y = h - 30 - ((it.value - min) / span) * (h - 60);
    return [x, y] as const;
  });
  const path = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ');
  const last = pts[pts.length - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <line x1={20} y1={h - 30} x2={w - 20} y2={h - 30} stroke={ink} strokeOpacity={0.35} strokeWidth={2} />
      <path d={path} fill="none" stroke={accent} strokeWidth={7}
           strokeDasharray={2000} strokeDashoffset={2000 - 2000 * reveal} />
      {reveal > 0.92 ? (
        <>
          <circle cx={last[0]} cy={last[1]} r={9} fill={accent} />
          <text x={last[0] - 10} y={last[1] - 20} fill={accent} fontWeight={900} fontSize={40} textAnchor="end">
            {items[items.length - 1].value}{unit}
          </text>
        </>
      ) : null}
    </svg>
  );
};

const BarChart: React.FC<{ items: ChartItem[]; unit: string; reveal: number; accent: string; ink: string }> = ({ items, unit, reveal, accent, ink }) => {
  const w = W, h = 420, barW = 220, gap = 90;
  const max = Math.max(...items.map((i) => i.value)) || 1;
  const totalW = items.length * barW + (items.length - 1) * gap;
  const startX = (w - totalW) / 2;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      {items.map((it, i) => {
        const bh = (it.value / max) * (h - 90) * reveal;
        const x = startX + i * (barW + gap);
        const y = h - 40 - bh;
        const isAccent = i === items.length - 1;
        const color = isAccent ? accent : ink;
        return (
          <g key={i}>
            <rect x={x} y={y} width={barW} height={bh} rx={14} fill={color} fillOpacity={isAccent ? 1 : 0.4} />
            <text x={x + barW / 2} y={y - 18} fill={color} fontWeight={900} fontSize={40} textAnchor="middle">
              {it.value}{unit}
            </text>
            {it.label ? (
              <text x={x + barW / 2} y={h - 12} fill={ink} fontWeight={700} fontSize={26} textAnchor="middle" opacity={0.8}>
                {it.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
};

const HBarChart: React.FC<{ items: ChartItem[]; unit: string; reveal: number; accent: string; ink: string }> = ({ items, unit, reveal, accent, ink }) => {
  const w = W, rowH = 96;
  const max = Math.max(...items.map((i) => i.value)) || 1;
  return (
    <svg width={w} height={items.length * rowH} viewBox={`0 0 ${w} ${items.length * rowH}`}>
      {items.map((it, i) => {
        const fillW = (it.value / max) * w * reveal;
        const y = i * rowH;
        const isAccent = i === 0;
        const color = isAccent ? accent : ink;
        return (
          <g key={i}>
            <text x={0} y={y + 22} fill={ink} fontWeight={700} fontSize={28}>{it.label ?? ''}</text>
            <rect x={0} y={y + 32} width={w} height={36} rx={10} fill={ink} fillOpacity={0.15} />
            <rect x={0} y={y + 32} width={fillW} height={36} rx={10} fill={color} fillOpacity={isAccent ? 1 : 0.55} />
            <text x={Math.max(fillW - 10, 40)} y={y + 57} fill="#fff" fontWeight={900} fontSize={26} textAnchor="end">
              {it.value}{unit}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

export const ChartCard: React.FC<P> = ({ card, ff, leaving }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const chart = card.chart!;
  const a = useMotion(frame, fps, card.start, leaving, T.EXIT, card.motion, card.exit);
  const reveal = interpolate(frame, [card.start * fps + 6, card.start * fps + 36], [0, 1],
                             { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const unit = chart.unit ?? '';
  return (
    <Frame card={card} align="center">
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center',
                    opacity: a.opacity, transform: a.transform, filter: a.filter }}>
        {chart.kind === 'line' ? <LineChart items={chart.items} unit={unit} reveal={reveal} accent={pal.accent} ink={pal.ink} /> : null}
        {chart.kind === 'bar' ? <BarChart items={chart.items} unit={unit} reveal={reveal} accent={pal.accent} ink={pal.ink} /> : null}
        {chart.kind === 'hbar' ? <HBarChart items={chart.items} unit={unit} reveal={reveal} accent={pal.accent} ink={pal.ink} /> : null}
        {ls.map((l, i) => (
          <span key={i} style={{
            fontFamily: ff, fontWeight: '800', fontSize: 56, lineHeight: 1.2, color: pal.ink,
            textShadow: pal.shadow, marginTop: 20, textAlign: 'center', whiteSpace: 'pre-wrap',
            textTransform: 'uppercase',
          }}>{l.text}</span>
        ))}
      </div>
    </Frame>
  );
};
