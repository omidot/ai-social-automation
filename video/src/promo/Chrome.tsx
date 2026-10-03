import React from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import { timecode, prog } from './theme';

/**
 * KHUNG CỐ ĐỊNH nằm trên mọi cảnh.
 *
 *   góc trái  -- nhãn mono "// 0X — tên cảnh", đổi chữ bằng hiệu ứng scramble
 *   góc phải  -- tên thương hiệu + timecode chạy 00:00:SS:FF
 *
 * Chữ scramble được suy ra TẤT ĐỊNH từ vị trí ký tự và số frame, không dùng
 * Math.random -- nếu không, mỗi lần seek lại ra một chuỗi rác khác nhau và
 * bản render sẽ lệch so với snapshot đã duyệt.
 */

const GLYPHS = '#%&@$*+=<>/\\|[]{}0123456789ABCDEFGHJKLMNPQRSTUVWXYZ';

/** Ký tự rác tất định cho ô thứ `i` tại frame `f`. */
const scrambleChar = (i: number, f: number) => {
  const k = (i * 71 + f * 31) % GLYPHS.length;
  return GLYPHS[k];
};

/**
 * Chữ hiện dần theo kiểu scramble: mỗi ký tự "chốt" lần lượt từ trái sang,
 * các ký tự chưa chốt vẫn đang quay số.
 */
const Scramble: React.FC<{ text: string; at: number; ff: string; style?: React.CSSProperties }> =
({ text, at, ff, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const DUR = 0.5;                     // thời gian khoá hết chuỗi
  const p = prog(t, at, DUR);
  const locked = Math.floor(p * text.length);

  const shown = text
    .split('')
    .map((ch, i) => {
      if (i < locked || ch === ' ') return ch;
      if (p >= 1) return ch;
      return scrambleChar(i, frame);
    })
    .join('');

  return (
    <span style={{ fontFamily: ff, whiteSpace: 'pre', ...style }}>{shown}</span>
  );
};

export const Chrome: React.FC<{
  n: string; name: string; sceneAt: number; brand: string;
  fg: string; dim: string; mono: string;
}> = ({ n, name, sceneAt, brand, fg, dim, mono }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const label = `// ${n} — ${name}`;
  const PAD = 54;
  const base: React.CSSProperties = {
    position: 'absolute', fontSize: 25, letterSpacing: '0.08em',
    fontWeight: 500,
  };

  return (
    <>
      <div style={{ ...base, left: PAD, top: PAD, color: dim }}>
        <Scramble text={label} at={sceneAt} ff={mono} />
      </div>
      <div style={{
        ...base, right: PAD, top: PAD, color: dim,
        textAlign: 'right', display: 'flex', flexDirection: 'column', gap: 6,
        alignItems: 'flex-end',
      }}>
        <span style={{ fontFamily: mono, color: fg, letterSpacing: '0.14em' }}>{brand}</span>
        <span style={{ fontFamily: mono, fontVariantNumeric: 'tabular-nums' }}>
          {timecode(t, fps)}
        </span>
      </div>
    </>
  );
};
