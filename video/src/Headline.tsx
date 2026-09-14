import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fitText } from '@remotion/layout-utils';
import { usePal } from './palette';
import type { Card } from './layouts';

const W = 1080 - 96 * 2;

/**
 * Tiêu đề TO phía trên khung -- chữ của KỊCH BẢN, đứng yên suốt cả đoạn
 * thay vì chạy theo từng từ. Bản tham chiếu luôn có lớp này: tiêu đề nói
 * CHỦ ĐỀ đang bàn, còn caption nhỏ ở đáy mới chạy theo lời nói. Dòng cuối
 * được nhấn bằng ô nền màu -- đúng kiểu "HẠ GỤC / GPT-5.6 & CLAUDE OPUS 5".
 */
export const Headline: React.FC<{ card: Card; ff: string; at: number }> = ({ card, ff, at }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const lines = card.headline ?? [];
  if (lines.length === 0) return null;

  const n = lines.length;
  return (
    <div style={{
      position: 'absolute', top: 232, left: 96, right: 96,
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
      pointerEvents: 'none',
    }}>
      {lines.map((text, i) => {
        const last = i === n - 1;
        const shout = last && n > 1;
        const draw = shout ? text.toUpperCase() : text;
        const weight = shout ? '900' : '800';
        const cap = shout ? 92 : 64;
        const size = Math.min(cap, fitText({
          text: draw, withinWidth: W - (shout ? 68 : 0), fontFamily: ff,
          fontWeight: weight, letterSpacing: '-0.01em',
        }).fontSize);
        const s = spring({
          frame: frame - at - i * 4, fps,
          config: { damping: 18, stiffness: 170, mass: 0.7 },
        });
        return (
          <div key={i} style={{
            padding: shout ? '10px 30px 12px' : 0,
            borderRadius: shout ? 12 : 0,
            background: shout ? pal.accent : 'transparent',
            opacity: interpolate(s, [0, 1], [0, 1]),
            transform: `translateY(${interpolate(s, [0, 1], [-18, 0])}px)`,
          }}>
            <span style={{
              fontFamily: ff, fontWeight: weight, fontSize: size, lineHeight: 1.1,
              color: shout ? '#FFFFFF' : pal.ink,
              letterSpacing: '-0.01em', display: 'block', textAlign: 'center',
              whiteSpace: 'pre', textShadow: shout ? 'none' : pal.shadow,
            }}>{draw}</span>
          </div>
        );
      })}
    </div>
  );
};
