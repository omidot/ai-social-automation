import React from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import { usePal } from './palette';
import timeline from './timeline.json';

export type SubWord = { text: string; start: number; end: number };

const WORDS = ((timeline as { subtitle?: SubWord[] }).subtitle ?? []) as SubWord[];

/** Bao nhiêu từ hiện cùng lúc -- bản tham chiếu để 2-4 từ mỗi lần. */
const WINDOW = 4;
/** Phụ đề nán lại sau từ cuối, để câu chốt không biến mất ngay. */
const LINGER = 0.6;

/**
 * Phụ đề chạy theo giọng nói ở đáy khung: mỗi lần một nhúm từ, từ ĐANG
 * được đọc tô màu nhấn. Đây là tầng bám sát tiếng nói -- slide phía trên
 * là chữ kịch bản đã thiết kế, cố tình không chạy theo từng từ.
 */
export const Subtitle: React.FC<{ ff: string }> = ({ ff }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const t = frame / fps;

  if (WORDS.length === 0) return null;

  // từ đang được đọc = từ cuối cùng đã bắt đầu
  let cur = -1;
  for (let i = 0; i < WORDS.length; i++) if (t >= WORDS[i].start) cur = i;
  if (cur < 0) return null;
  if (t > WORDS[WORDS.length - 1].end + LINGER) return null;

  // Cửa sổ trượt theo nhúm cố định: chữ đứng yên rồi nhảy cả nhúm, không
  // trôi từng từ một -- đọc dễ hơn hẳn trên video dọc.
  const from = Math.floor(cur / WINDOW) * WINDOW;
  const group = WORDS.slice(from, from + WINDOW);

  return (
    <div style={{
      position: 'absolute', left: 0, right: 0, bottom: 250,
      display: 'flex', justifyContent: 'center', padding: '0 60px',
    }}>
      <div style={{
        fontFamily: ff, fontWeight: '800', fontSize: 58, lineHeight: 1.25,
        textAlign: 'center', textShadow: '0 3px 18px rgba(0,0,0,0.85)',
        letterSpacing: '-0.01em',
      }}>
        {group.map((w, i) => (
          <span key={from + i} style={{ color: from + i === cur ? pal.accent : '#FFFFFF' }}>
            {w.text}{i < group.length - 1 ? ' ' : ''}
          </span>
        ))}
      </div>
    </div>
  );
};
