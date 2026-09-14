import React from 'react';
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { brandsOf } from './BrandMark';
import type { Card } from './layouts';
import { usePal } from './palette';

/** Từ báo hiệu hai bên đang so kè nhau. */
const MARKS = new RegExp('[̀-ͯ]', 'g');
const bare = (s: string) =>
  s.toLowerCase().replace(/đ/g, 'd').normalize('NFD').replace(MARKS, '')
    .replace(/[^a-z0-9]/g, '');

const VS_WORDS = new Set(['dau', 'vs', 'versus', 'doidau', 'sovoi', 'hagục', 'haguc']);

/**
 * Thẻ "đấu": khi lời nói nêu hai hãng và một từ so kè ("đấu", "vs", "đối
 * đầu"), chỉ chữ thôi là hụt -- người xem cần THẤY hai bên đứng cạnh nhau.
 * Trả về đúng hai hãng đầu tiên, hoặc null nếu thẻ không phải cảnh so kè.
 */
export const versusOf = (card: Card) => {
  const hasVs = card.lines.some((l) =>
    (l.words ?? []).some((w) => VS_WORDS.has(bare(w.text))));
  if (!hasVs) return null;
  const brands = brandsOf(card);
  return brands.length >= 2 ? brands.slice(0, 2) : null;
};

const Tile: React.FC<{ file: string; label: string; at: number; ff: string; ink: string }> =
  ({ file, label, at, ff, ink }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const s = spring({ frame: frame - at, fps, config: { damping: 16, stiffness: 170, mass: 0.8 } });
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 22,
        opacity: interpolate(s, [0, 1], [0, 1]),
        transform: `scale(${interpolate(s, [0, 1], [0.7, 1])})`,
      }}>
        <div style={{
          width: 232, height: 232, borderRadius: 40, overflow: 'hidden',
          background: 'rgba(255,255,255,0.95)',
          boxShadow: '0 24px 60px rgba(0,0,0,0.55)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Img src={staticFile(file)} style={{ width: '72%', height: '72%', objectFit: 'contain' }} />
        </div>
        <span style={{
          fontFamily: ff, fontWeight: '800', fontSize: 34, color: ink,
          letterSpacing: '0.04em',
        }}>{label}</span>
      </div>
    );
  };

/** Hai ô logo đứng hai bên, chữ "ĐẤU" đỏ ở giữa. */
export const VersusMark: React.FC<{ card: Card; ff: string }> = ({ card, ff }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const pair = versusOf(card);
  if (!pair) return null;

  const base = card.start * fps;
  const mid = spring({ frame: frame - (base + 10), fps, config: { damping: 14, stiffness: 200, mass: 0.6 } });

  return (
    <div style={{
      position: 'absolute', top: 430, left: 0, right: 0,
      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 52,
    }}>
      <Tile file={pair[0].file} label={pair[0].label} at={base} ff={ff} ink={pal.ink} />
      <span style={{
        fontFamily: ff, fontWeight: '900', fontSize: 62, color: pal.accent,
        letterSpacing: '0.06em', marginBottom: 56,
        opacity: interpolate(mid, [0, 1], [0, 1]),
        transform: `scale(${interpolate(mid, [0, 1], [0.5, 1])})`,
      }}>ĐẤU</span>
      <Tile file={pair[1].file} label={pair[1].label} at={base + 6} ff={ff} ink={pal.ink} />
    </div>
  );
};
