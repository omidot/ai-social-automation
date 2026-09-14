import React from 'react';
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { Card } from './layouts';
import logos from './logos.json';

type Brand = { label: string; file: string };
const REGISTRY = logos as Record<string, Brand>;

/** bỏ dấu câu + dấu tiếng Việt để "GPT-6", "gpt." cùng khớp khoá "gpt" */
const MARKS = new RegExp('[̀-ͯ]', 'g');
const norm = (s: string) =>
  s.toLowerCase().replace(/đ/g, 'd').normalize('NFD').replace(MARKS, '')
    .replace(/[^a-z0-9]/g, '');

/**
 * Hãng đang được nói tới trong thẻ này. Khoá lấy thẳng từ logos.json (do
 * phía Python sinh ra) nên không phải chép lại danh sách hãng ở hai nơi.
 */
export const brandOf = (card: Card): Brand | null => {
  const words = card.lines.flatMap((l) => (l.words ?? []).map((w) => norm(w.text)));
  for (const w of words) {
    if (REGISTRY[w]) return REGISTRY[w];
  }
  return null;
};

/** Mọi hãng được nhắc trong thẻ, theo thứ tự nói, không lặp. */
export const brandsOf = (card: Card): Brand[] => {
  const out: Brand[] = [];
  for (const l of card.lines) {
    for (const w of l.words ?? []) {
      const b = REGISTRY[norm(w.text)];
      if (b && !out.some((x) => x.label === b.label)) out.push(b);
    }
  }
  return out;
};

/** Logo hãng ở góc phải trên, đổi theo hãng đang được nhắc. */
export const BrandMark: React.FC<{ card: Card }> = ({ card }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const brand = brandOf(card);
  if (!brand) return null;
  const s = spring({ frame: frame - card.start * fps, fps, config: { damping: 18, stiffness: 200, mass: 0.7 } });
  return (
    // To và đứng một mình trên nền, không nhét trong ô trắng bé xíu -- bản
    // tham chiếu để logo hãng ở cỡ đọc được từ xa. Vẫn giữ một nền sáng rất
    // nhạt vì nhiều favicon là hình đen, đặt thẳng lên nền tối sẽ mất hút.
    <div style={{
      position: 'absolute', top: 124, right: 52,
      width: 92, height: 92, borderRadius: 22, overflow: 'hidden',
      background: 'rgba(255,255,255,0.94)',
      boxShadow: '0 10px 30px rgba(0,0,0,0.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      opacity: interpolate(s, [0, 1], [0, 1]),
      transform: `scale(${interpolate(s, [0, 1], [0.6, 1])})`,
    }}>
      <Img src={staticFile(brand.file)}
           style={{ width: '76%', height: '76%', objectFit: 'contain' }} />
    </div>
  );
};
