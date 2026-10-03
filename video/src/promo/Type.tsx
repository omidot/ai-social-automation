import React from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import { blurInAt, prog, power3Out, tiltOf, CARD_RADIUS, CARD_SHADOW, C } from './theme';

/**
 * CHỮ BLUR-IN theo đúng thông số người dùng: blur 16px -> 0, trượt lên 70px,
 * stagger 0.07s mỗi TỪ, power3.out.
 *
 * Từ nào nằm trong `accent` được in bằng serif nghiêng (Newsreader Italic)
 * thay vì sans đậm -- đây là thủ pháp nhấn của phong cách, không phải đổi
 * màu. Tách theo CỤM chứ không theo từng từ, để cụm nhấn nhiều từ không bị
 * vỡ nhịp giữa chừng.
 */

type Seg = { text: string; accent: boolean };

/** Cắt câu thành các đoạn thường / đoạn nhấn, giữ nguyên thứ tự. */
export const segment = (text: string, accents: string[] = []): Seg[] => {
  if (!accents.length) return [{ text, accent: false }];
  let segs: Seg[] = [{ text, accent: false }];
  for (const a of accents) {
    if (!a) continue;
    const next: Seg[] = [];
    for (const s of segs) {
      if (s.accent || !s.text.includes(a)) { next.push(s); continue; }
      const i = s.text.indexOf(a);
      if (i > 0) next.push({ text: s.text.slice(0, i), accent: false });
      next.push({ text: a, accent: true });
      const rest = s.text.slice(i + a.length);
      if (rest) next.push({ text: rest, accent: false });
    }
    segs = next;
  }
  return segs;
};

export const BlurIn: React.FC<{
  text: string; accents?: string[]; at: number;
  sans: string; serif: string; color: string; accentColor?: string;
  size: number; lineHeight?: number; align?: 'left' | 'center';
  weight?: string; style?: React.CSSProperties;
}> = ({ text, accents = [], at, sans, serif, color, accentColor,
        size, lineHeight = 1.08, align = 'left', weight = '800', style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  // Đánh số TỪ chạy liên tục qua mọi đoạn, để stagger không nhảy cóc ở ranh
  // giới giữa đoạn thường và đoạn nhấn.
  let wi = -1;
  const segs = segment(text, accents);

  return (
    <div style={{
      display: 'flex', flexWrap: 'wrap',
      // Khoảng cách giữa các từ phải tính theo CỠ CHỮ của chính khối này.
      // Dùng đơn vị em ở đây thì nó quy chiếu về font-size của container
      // (mặc định 16px) chứ không phải `size`, nên các từ dính liền nhau.
      columnGap: Math.round(size * 0.24),
      rowGap: 0,
      justifyContent: align === 'center' ? 'center' : 'flex-start',
      lineHeight, ...style,
    }}>
      {segs.map((s, si) =>
        s.text.split(/\s+/).filter(Boolean).map((w, k) => {
          wi += 1;
          const a = blurInAt(t, at, wi);
          return (
            <span
              key={`${si}-${k}`}
              style={{
                fontFamily: s.accent ? serif : sans,
                fontStyle: s.accent ? 'italic' : 'normal',
                fontWeight: s.accent ? '500' : weight,
                fontSize: size,
                color: s.accent ? (accentColor ?? color) : color,
                letterSpacing: s.accent ? '0' : '-0.02em',
                opacity: a.opacity,
                filter: a.blur > 0.15 ? `blur(${a.blur.toFixed(2)}px)` : 'none',
                transform: `translateY(${a.y.toFixed(2)}px)`,
                display: 'inline-block',
              }}
            >{w}</span>
          );
        })
      )}
    </div>
  );
};

/** Nhãn mono nhỏ, viết hoa, giãn chữ -- dùng mở đầu mỗi cảnh. */
export const Eyebrow: React.FC<{
  text: string; at: number; mono: string; color: string; size?: number;
}> = ({ text, at, mono, color, size = 24 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = power3Out(prog(frame / fps, at, 0.45));
  return (
    <div style={{
      fontFamily: mono, fontSize: size, letterSpacing: '0.2em', color,
      fontWeight: 600, opacity: p,
      transform: `translateY(${(14 * (1 - p)).toFixed(2)}px)`,
    }}>{text}</div>
  );
};

/**
 * THẺ UI TRẮNG: bo 24px, bóng mềm, xoay nhẹ ±2–8°.
 * Bay vào kèm blur và xoay -- không fade chậm.
 */
export const UICard: React.FC<{
  at: number; i: number; children: React.ReactNode;
  style?: React.CSSProperties; dur?: number;
  /**
   * Hệ số thu nhỏ góc xoay. Thẻ CÀNG RỘNG thì cùng một góc lại đẩy hai mép
   * lệch càng xa: thẻ rộng ~900px nghiêng 6° đã đội mép lên gần 95px, đủ để
   * các thẻ xếp dọc chồng lên nhau. Thẻ rộng truyền hệ số nhỏ lại.
   */
  tiltScale?: number;
}> = ({ at, i, children, style, dur = 0.5, tiltScale = 1 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = power3Out(prog(frame / fps, at, dur));
  const tilt = tiltOf(i) * tiltScale;
  return (
    <div style={{
      background: '#FFFFFF',
      borderRadius: CARD_RADIUS,
      boxShadow: CARD_SHADOW,
      opacity: p,
      filter: p < 0.99 ? `blur(${(10 * (1 - p)).toFixed(2)}px)` : 'none',
      transform: `translateY(${(54 * (1 - p)).toFixed(2)}px)`
        + ` rotate(${(tilt * p).toFixed(2)}deg)`
        + ` scale(${(0.9 + 0.1 * p).toFixed(3)})`,
      ...style,
    }}>{children}</div>
  );
};

/**
 * GẠCH CHÉO NÉT BÚT MARKER chạy ngang qua một thẻ.
 * Nét vẽ hơi nghiêng và dày như đầu bút dạ, quét từ trái sang.
 */
export const MarkerStrike: React.FC<{ at: number; color?: string; dur?: number }> =
({ at, color = C.ink, dur = 0.28 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = power3Out(prog(frame / fps, at, dur));
  if (p <= 0) return null;
  return (
    // Nét bút phải nằm GỌN trong thẻ: đã xoay thì hai đầu vươn ra thêm, nên
    // chừa lề rộng hơn góc xoay cần, không để nét chạy lòi khỏi mép thẻ.
    <div style={{
      position: 'absolute', left: '6%', right: '6%', top: '50%',
      height: 10, background: color, borderRadius: 5,
      transform: `translateY(-50%) rotate(-1.1deg) scaleX(${p.toFixed(3)})`,
      transformOrigin: 'left center',
      opacity: 0.92,
    }} />
  );
};
