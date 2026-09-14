import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { usePal } from './palette';
import { Frame, type P } from './layouts';
import { T } from './theme';

const W = 1080 - T.PAD * 2;

type ChartItem = { label?: string; value: number };

/** Hàng nào cũng hiện sau hàng trước một nhịp, cách nhau tối đa ngần này. */
const STEP = 0.55;
/** Phần thời lượng thẻ dành cho việc hiện dần các hàng. */
const BUILD = 0.6;

const fmt = (v: number, unit: string) => {
  const n = Number.isInteger(v) ? String(v) : String(v);
  return unit ? (unit.length <= 2 ? `${unit}${n}` : `${n} ${unit}`) : n;
};

/**
 * Một hàng: nhãn trái + số phải, dưới là thanh bo tròn chạy từ trái sang.
 * Hàng đã đi qua thì chìm xuống xám, chỉ hàng mới nhất sáng trắng -- mắt
 * luôn bị kéo về con số đang được nói tới.
 */
const Row: React.FC<{
  item: ChartItem; max: number; unit: string; ff: string;
  at: number; active: boolean; ink: string; accent: string;
}> = ({ item, max, unit, ff, at, active, ink, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = frame - at * fps;
  const s = spring({ frame: local, fps, config: { damping: 20, stiffness: 150, mass: 0.8 } });
  const grow = interpolate(s, [0, 1], [0, 1]);
  const pct = max > 0 ? Math.max(0.02, item.value / max) : 0;
  const dim = !active;

  return (
    <div style={{
      marginBottom: 34,
      opacity: interpolate(s, [0, 1], [0, 1]),
      transform: `translateY(${interpolate(s, [0, 1], [18, 0])}px)`,
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
        marginBottom: 14, fontFamily: ff,
      }}>
        <span style={{ fontWeight: '800', fontSize: 40, color: dim ? '#8A8A88' : ink }}>
          {item.label ?? ''}
        </span>
        <span style={{ fontWeight: '900', fontSize: 44, color: dim ? '#8A8A88' : (active ? accent : ink) }}>
          {fmt(item.value, unit)}
        </span>
      </div>
      <div style={{
        height: 56, borderRadius: 28, width: '100%',
        background: 'rgba(255,255,255,0.045)',
        border: '1px solid rgba(255,255,255,0.07)',
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', borderRadius: 28,
          width: `${pct * grow * 100}%`,
          background: dim
            ? 'linear-gradient(90deg, #6E6E6C 0%, #8A8A88 100%)'
            : `linear-gradient(90deg, ${accent} 0%, #FF8A6B 100%)`,
        }} />
      </div>
    </div>
  );
};

/**
 * Khối SỐ LIỆU: hộp bo góc, nhãn nhỏ bên trái, con số to bên phải -- đúng
 * kiểu bản tham chiếu dùng cho thông số rời rạc (giá, dung lượng, tốc độ),
 * nơi vẽ thanh bar là vô nghĩa vì các số không cùng thang đo.
 */
const StatRow: React.FC<{
  item: ChartItem; unit: string; ff: string;
  at: number; active: boolean; ink: string; accent: string;
}> = ({ item, unit, ff, at, active, ink, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - at * fps, fps, config: { damping: 20, stiffness: 150, mass: 0.8 } });
  const dim = !active;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '34px 40px', marginBottom: 26, borderRadius: 26,
      background: 'rgba(255,255,255,0.045)',
      border: `1px solid ${active ? 'rgba(255,255,255,0.16)' : 'rgba(255,255,255,0.07)'}`,
      opacity: interpolate(s, [0, 1], [0, 1]),
      transform: `translateY(${interpolate(s, [0, 1], [22, 0])}px)`,
    }}>
      <span style={{
        fontFamily: ff, fontWeight: '700', fontSize: 38,
        color: dim ? '#8A8A88' : ink, letterSpacing: '0.01em',
      }}>{item.label ?? ''}</span>
      <span style={{
        fontFamily: ff, fontWeight: '900', fontSize: 72, lineHeight: 1,
        color: dim ? '#8A8A88' : (active ? accent : ink),
      }}>{fmt(item.value, unit)}</span>
    </div>
  );
};

/**
 * Biểu đồ dạng HÀNG NGANG, không phải đồ thị vẽ trục. Mọi kiểu (line/bar/
 * hbar) đều đổ về một cách trình bày: đọc được trên điện thoại ở khung dọc,
 * và hợp với nhịp nói -- mỗi hàng rơi vào đúng lúc con số đó được nhắc.
 */
export const ChartCard: React.FC<P> = ({ card, ff }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const chart = card.chart!;
  const items = chart.items ?? [];
  if (items.length === 0) return null;

  const t = frame / fps;
  const max = Math.max(...items.map((i) => i.value), 0);
  const span = Math.max(0.3, (card.out - card.start) * BUILD);
  const step = Math.min(STEP, span / items.length);
  const at = (i: number) => card.start + i * step;

  // hàng "đang nói tới" = hàng cuối cùng đã hiện
  let active = 0;
  items.forEach((_, i) => { if (t >= at(i)) active = i; });

  const title = card.lines.find((l) => !l.hidden)?.text ?? '';

  return (
    <Frame card={card} align="center">
      <div style={{ width: W }}>
        {title ? (
          <div style={{
            fontFamily: ff, fontWeight: '800', fontSize: 46, color: pal.ink,
            textAlign: 'center', marginBottom: 44, textShadow: pal.shadow,
          }}>{title}</div>
        ) : null}
        {items.map((it, i) =>
          chart.kind === 'stat' ? (
            <StatRow key={i} item={it} unit={chart.unit ?? ''} ff={ff}
                     at={at(i)} active={i === active} ink={pal.ink} accent={pal.accent} />
          ) : (
            <Row key={i} item={it} max={max} unit={chart.unit ?? ''} ff={ff}
                 at={at(i)} active={i === active} ink={pal.ink} accent={pal.accent} />
          ))}
      </div>
    </Frame>
  );
};
