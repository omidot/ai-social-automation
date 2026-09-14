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
 * THANH ĐO có mũi tên: một điểm số trên thang cố định (vd 98.6 / 100).
 * Mũi tên chạy tới đúng vị trí đạt được -- nhìn ra ngay "gần chạm trần".
 */
const Gauge: React.FC<{
  items: ChartItem[]; unit: string; ff: string; at: number; ink: string; accent: string;
}> = ({ items, unit, ff, at, ink, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - at * fps, fps, config: { damping: 22, stiffness: 120, mass: 1 } });
  const got = items[0]?.value ?? 0;
  const max = items[1]?.value || 1;
  const pct = Math.max(0, Math.min(1, got / max));
  const run = interpolate(s, [0, 1], [0, pct]);
  return (
    <div>
      <div style={{
        fontFamily: ff, fontWeight: '900', fontSize: 96, color: accent,
        textAlign: 'center', lineHeight: 1, marginBottom: 10,
        opacity: interpolate(s, [0, 1], [0, 1]),
      }}>
        {fmt(got, unit)}<span style={{ color: ink, opacity: 0.5, fontSize: 52 }}> / {max}</span>
      </div>
      <div style={{
        fontFamily: ff, fontWeight: '700', fontSize: 32, color: ink, opacity: 0.55,
        textAlign: 'center', marginBottom: 40, letterSpacing: '0.12em',
      }}>{(items[0]?.label ?? '').toUpperCase()}</div>
      <div style={{ position: 'relative', height: 22 }}>
        <div style={{
          position: 'absolute', inset: 0, borderRadius: 11,
          background: 'rgba(255,255,255,0.07)',
        }} />
        <div style={{
          position: 'absolute', left: 0, top: 0, bottom: 0, borderRadius: 11,
          width: `${run * 100}%`,
          background: `linear-gradient(90deg, rgba(255,77,46,0.35) 0%, ${accent} 100%)`,
        }} />
        {/* mũi tên đứng ngay mốc đạt được */}
        <div style={{
          position: 'absolute', top: -16, left: `${run * 100}%`, transform: 'translateX(-50%)',
          width: 0, height: 0,
          borderLeft: '18px solid transparent', borderRight: '18px solid transparent',
          borderTop: `26px solid ${accent}`,
        }} />
      </div>
    </div>
  );
};

/**
 * CHIP tên: vài cái tên mới nằm cạnh nhau, mỗi cái một thẻ bo tròn viền
 * nhấn. Dùng khi bài điểm tên sản phẩm/tính năng, nơi con số không có ý
 * nghĩa gì để mà vẽ.
 */
const Chips: React.FC<{
  items: ChartItem[]; ff: string; at: (i: number) => number; active: number;
  ink: string; accent: string;
}> = ({ items, ff, at, active, ink, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 26 }}>
      {items.map((it, i) => {
        const s = spring({ frame: frame - at(i) * fps, fps, config: { damping: 17, stiffness: 180, mass: 0.7 } });
        const on = i === active;
        return (
          <div key={i} style={{
            padding: '26px 44px', borderRadius: 999,
            border: `3px solid ${on ? accent : 'rgba(255,255,255,0.18)'}`,
            background: on ? 'rgba(255,77,46,0.14)' : 'rgba(255,255,255,0.04)',
            fontFamily: ff, fontWeight: '900', fontSize: 52,
            color: on ? accent : ink,
            letterSpacing: '0.02em', whiteSpace: 'nowrap',
            opacity: interpolate(s, [0, 1], [0, 1]),
            transform: `translateY(${interpolate(s, [0, 1], [20, 0])}px) scale(${interpolate(s, [0, 1], [0.85, 1])})`,
          }}>{it.label ?? ''}</div>
        );
      })}
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
  // Biểu đồ đứng nguyên suốt cả đoạn kịch bản -> dựng hình tính từ mốc
  // card đầu của nhóm, nếu không mỗi card nhỏ sẽ dựng lại từ đầu.
  const base = card.visualAt ?? card.start;
  const span = Math.max(0.3, (card.out - base) * BUILD);
  const step = Math.min(STEP, span / items.length);
  const at = (i: number) => base + i * step;

  // hàng "đang nói tới" = hàng cuối cùng đã hiện
  let active = 0;
  items.forEach((_, i) => { if (t >= at(i)) active = i; });

  // Không in tiêu đề ở đây nữa: lớp Headline phía trên đã nói CHỦ ĐỀ bằng
  // chữ kịch bản, còn caption dưới đáy chạy theo lời nói. In thêm ở giữa
  // là chữ chồng chữ ba lần trên cùng một khung.
  return (
    <Frame card={card} align="center">
      <div style={{ width: W }}>
        {chart.kind === 'gauge' ? (
          <Gauge items={items} unit={chart.unit ?? ''} ff={ff} at={at(0)}
                 ink={pal.ink} accent={pal.accent} />
        ) : chart.kind === 'chips' ? (
          <Chips items={items} ff={ff} at={at} active={active}
                 ink={pal.ink} accent={pal.accent} />
        ) : items.map((it, i) =>
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
