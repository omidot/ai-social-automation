import React from 'react';
import { AbsoluteFill, interpolate, interpolateColors, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fitText } from '@remotion/layout-utils';
import { SelectionBox } from './SelectionBox';
import { useMotion, type Motion, type Exit } from './anim';
import { usePal } from './palette';
import { shotPushAt } from './Shots';
import { T } from './theme';

export type Line = { text: string; start: number; end: number; hidden?: boolean };
export type Card = {
  index: number; lines: Line[]; start: number; end: number; out: number; section: string;
  variant: string; anchor: 'top' | 'mid' | 'low'; num?: number; motion: Motion; exit: Exit;
};
export type P = { card: Card; ff: string; leaving: number; activeIdx: number };

const MAXW = 1080 - T.PAD * 2;
const fit = (text: string, ff: string, w: string, cap: number, within = MAXW) =>
  Math.min(cap, fitText({ text, withinWidth: within, fontFamily: ff, fontWeight: w, letterSpacing: '-0.02em' }).fontSize);

/** chỉ những dòng không bị đánh dấu "~" mới hiện; dòng ẩn vẫn giữ chỗ tính giờ */
export const shown = (c: Card) => c.lines.filter((l) => !l.hidden);

export const anchorStyle = (a: string, push = 0): React.CSSProperties =>
  a === 'top'
    ? { justifyContent: 'flex-start', paddingTop: 1920 * 0.28 + push * 270 }
    : a === 'low'
      ? { justifyContent: 'flex-end', paddingBottom: 1920 * 0.24 }   // card thấp không bị ảnh che
      : { justifyContent: 'center', transform: `translateY(${-46 + push * 150}px)` };

const Frame: React.FC<{ card: Card; align: 'flex-start' | 'center' | 'flex-end'; children: React.ReactNode }> = ({ card, align, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const push = shotPushAt(frame / fps);
  return (
    <AbsoluteFill style={{ paddingLeft: T.PAD, paddingRight: T.PAD, alignItems: align, ...anchorStyle(card.anchor, push) }}>
      {children}
    </AbsoluteFill>
  );
};

/* ---------- 1. STACK (và RIGHT khi mirror) ---------- */
export const Stack: React.FC<P & { mirror?: boolean }> = ({ card, ff, leaving, activeIdx, mirror }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const n = ls.length;
  return (
    <Frame card={card} align={mirror ? 'flex-end' : 'flex-start'}>
      {ls.map((l, i) => {
        const role = i === n - 1 ? 'accent' : n === 3 && i === 0 ? 'small' : 'big';
        const w = T.WEIGHT[role];
        const size = fit(l.text, ff, w, T.SIZE[role]);
        const a = useMotion(frame, fps, Math.max(l.start, card.start), leaving, T.EXIT, card.motion, card.exit);
        const color = role === 'accent' ? (n === 1 ? pal.ink : pal.gray) : role === 'small' ? pal.ink2 : pal.ink;
        return (
          <div key={i} style={{
            position: 'relative', display: 'inline-block', margin: '9px 0', opacity: a.opacity,
            transform: a.transform, filter: a.filter, clipPath: a.clipPath,
            transformOrigin: mirror ? 'right center' : 'left center',
          }}>
            <span style={{
              fontFamily: ff, fontWeight: w, fontSize: size, lineHeight: 1.04, color,
              letterSpacing: a.letterSpacing ?? '-0.02em', display: 'block', whiteSpace: 'pre', textShadow: pal.shadow,
            }}>{l.text}</span>
            {i === activeIdx ? <SelectionBox since={frame - ls[activeIdx].start * fps} leaving={leaving} mirror={mirror} /> : null}
          </div>
        );
      })}
    </Frame>
  );
};

/* ---------- 2. HERO — chữ khổng lồ, chuyển động lan theo TỪNG TỪ ---------- */
export const Hero: React.FC<P> = ({ card, ff, leaving }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const size = Math.min(...ls.map((l) => fit(l.text, ff, '900', 168)));
  return (
    <Frame card={card} align="center">
      {ls.map((l, i) => (
        <div key={i} style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '0 22px', margin: '4px 0' }}>
          {l.text.split(' ').map((wd, j) => {
            const a = useMotion(frame, fps, Math.max(l.start, card.start), leaving, T.EXIT, card.motion, card.exit, j * 2.5);
            return (
              <span key={j} style={{
                fontFamily: ff, fontWeight: '900', fontSize: size, lineHeight: 1.0, color: pal.ink,
                letterSpacing: a.letterSpacing ?? '-0.03em', display: 'inline-block', textShadow: pal.shadow,
                opacity: a.opacity, transform: a.transform, filter: a.filter, clipPath: a.clipPath,
              }}>{wd}</span>
            );
          })}
        </div>
      ))}
    </Frame>
  );
};

/* ---------- 3. INVERT — tấm phủ toàn khung, ĐẢO NGƯỢC hẳn nền đang dùng ---------- */
export const Invert: React.FC<P> = ({ card, ff, leaving }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const p = spring({ frame: frame - card.start * fps, fps, config: { damping: 200, stiffness: 130, mass: 0.6 } });
  const outP = interpolate(leaving, [0, T.EXIT], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const dim = pal.dark ? '#6E6E6C' : '#9A9A9A';
  return (
    <>
      <AbsoluteFill style={{ background: pal.panel, clipPath: `inset(${interpolate(p, [0, 1], [100, 0])}% 0 0 0)`, opacity: 1 - outP * 0.9 }} />
      <Frame card={card} align="flex-start">
        {ls.map((l, i) => {
          const size = fit(l.text, ff, '900', 132);
          const a = useMotion(frame, fps, Math.max(l.start, card.start), leaving, T.EXIT, card.motion, card.exit);
          return (
            <span key={i} style={{
              fontFamily: ff, fontWeight: '900', fontSize: size, lineHeight: 1.08,
              letterSpacing: a.letterSpacing ?? '-0.02em', color: i === ls.length - 1 ? pal.panelInk : dim,
              margin: '8px 0', whiteSpace: 'pre',
              opacity: a.opacity, transform: a.transform, filter: a.filter, clipPath: a.clipPath,
            }}>{l.text}</span>
          );
        })}
      </Frame>
    </>
  );
};

/* ---------- 4. MARK — thanh quét ngang, chữ đảo màu ---------- */
export const Mark: React.FC<P> = ({ card, ff, leaving }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const n = ls.length;
  const onBar = pal.dark ? '#0A0A0A' : '#FFFFFF';
  return (
    <Frame card={card} align="flex-start">
      {ls.map((l, i) => {
        const last = i === n - 1;
        const w = last ? '900' : n === 3 && i === 0 ? '700' : '800';
        const size = fit(l.text, ff, w, last ? 104 : 72, MAXW - 44);
        const base = Math.max(l.start, card.start);
        const a = useMotion(frame, fps, base, leaving, T.EXIT, card.motion, card.exit);
        const bar = interpolate(frame - base * fps, [3, 14], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
        const col = last ? interpolateColors(bar, [0.35, 0.75], [pal.ink, onBar]) : pal.ink2;
        return (
          <div key={i} style={{
            position: 'relative', display: 'inline-block', margin: '9px 0', padding: last ? '8px 22px' : 0,
            opacity: a.opacity, transform: a.transform, filter: a.filter, transformOrigin: 'left center',
          }}>
            {last ? <div style={{ position: 'absolute', inset: 0, background: pal.ink, transform: `scaleX(${bar})`, transformOrigin: 'left center' }} /> : null}
            <span style={{
              position: 'relative', fontFamily: ff, fontWeight: w, fontSize: size, lineHeight: 1.06, color: col,
              letterSpacing: a.letterSpacing ?? '-0.02em', display: 'block', whiteSpace: 'pre',
              textShadow: last ? 'none' : pal.shadow,
            }}>{l.text}</span>
          </div>
        );
      })}
    </Frame>
  );
};

/* ---------- 5. STAIR — bậc thang thụt dần ---------- */
export const Stair: React.FC<P> = ({ card, ff, leaving, activeIdx }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const n = ls.length;
  return (
    <Frame card={card} align="flex-start">
      {ls.map((l, i) => {
        const w = i === n - 1 ? '900' : '800';
        const size = fit(l.text, ff, w, i === n - 1 ? 108 : 84, MAXW - i * 72);
        const a = useMotion(frame, fps, Math.max(l.start, card.start), leaving, T.EXIT, card.motion, card.exit);
        return (
          <div key={i} style={{
            position: 'relative', display: 'inline-block', margin: `9px 0 9px ${i * 72}px`,
            opacity: a.opacity, transform: a.transform, filter: a.filter, clipPath: a.clipPath, transformOrigin: 'left center',
          }}>
            <span style={{
              fontFamily: ff, fontWeight: w, fontSize: size, lineHeight: 1.05, color: i === n - 1 ? pal.ink : pal.gray,
              letterSpacing: a.letterSpacing ?? '-0.02em', display: 'block', whiteSpace: 'pre', textShadow: pal.shadow,
            }}>{l.text}</span>
            {i === activeIdx ? <SelectionBox since={frame - ls[activeIdx].start * fps} leaving={leaving} /> : null}
          </div>
        );
      })}
    </Frame>
  );
};

/* ---------- 6. NUMERAL — huy hiệu số cho 6 tính năng ---------- */
export const Numeral: React.FC<P> = ({ card, ff, leaving }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const n = ls.length;
  const b = useMotion(frame, fps, card.start, leaving, T.EXIT, card.motion, card.exit);
  const spin = interpolate(b.s, [0, 1], [-14, 0]);
  return (
    <Frame card={card} align="flex-start">
      <div style={{
        width: 168, height: 168, background: pal.ink, borderRadius: 22, display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginBottom: 30, opacity: b.opacity, transform: `${b.transform} rotate(${spin}deg)`, filter: b.filter,
      }}>
        <span style={{ fontFamily: ff, fontWeight: '900', fontSize: 104, color: pal.dark ? '#0A0A0A' : '#FFFFFF', lineHeight: 1 }}>{card.num}</span>
      </div>
      {ls.map((l, i) => {
        const w = i === n - 1 ? '900' : '700';
        const size = fit(l.text, ff, w, i === n - 1 ? 100 : 68);
        const a = useMotion(frame, fps, Math.max(l.start, card.start), leaving, T.EXIT, card.motion, card.exit, 3);
        return (
          <span key={i} style={{
            fontFamily: ff, fontWeight: w, fontSize: size, lineHeight: 1.06, color: i === n - 1 ? pal.ink : pal.ink2,
            letterSpacing: a.letterSpacing ?? '-0.02em', margin: '7px 0', whiteSpace: 'pre', textShadow: pal.shadow,
            opacity: a.opacity, transform: a.transform, filter: a.filter, clipPath: a.clipPath,
          }}>{l.text}</span>
        );
      })}
    </Frame>
  );
};

/* ---------- 7. STRIKE — gạch ngang dòng phủ định ---------- */
export const Strike: React.FC<P> = ({ card, ff, leaving }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const n = ls.length;
  return (
    <Frame card={card} align="flex-start">
      {ls.map((l, i) => {
        const w = i === n - 1 ? '900' : '800';
        const size = fit(l.text, ff, w, i === n - 1 ? 106 : 82);
        const base = Math.max(l.start, card.start);
        const a = useMotion(frame, fps, base, leaving, T.EXIT, card.motion, card.exit);
        const cut = interpolate(frame - base * fps, [7, 18], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
        return (
          <div key={i} style={{
            position: 'relative', display: 'inline-block', margin: '9px 0', opacity: a.opacity,
            transform: a.transform, filter: a.filter, clipPath: a.clipPath, transformOrigin: 'left center',
          }}>
            <span style={{
              fontFamily: ff, fontWeight: w, fontSize: size, lineHeight: 1.05, color: i === n - 1 ? pal.ink : pal.gray,
              letterSpacing: a.letterSpacing ?? '-0.02em', display: 'block', whiteSpace: 'pre', textShadow: pal.shadow,
            }}>{l.text}</span>
            <div style={{ position: 'absolute', left: -6, right: -6, top: '52%', height: 9, background: pal.ink, transform: `scaleX(${cut})`, transformOrigin: 'left center' }} />
          </div>
        );
      })}
    </Frame>
  );
};
