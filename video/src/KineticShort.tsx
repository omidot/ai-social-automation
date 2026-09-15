import React from 'react';
import {
  AbsoluteFill, Audio, continueRender, delayRender, interpolate, spring,
  staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import { loadFont } from '@remotion/google-fonts/BeVietnamPro';
import { BgVideo, palAt } from './BgVideo';
import { BrandMark } from './BrandMark';
import { ChartCard } from './Chart';
import { ScreenshotCard } from './Screenshot';
import { HookScreen, StatementScreen, ShotScreen, CardsScreen } from './Screens';
import { ElementView } from './Elements';
import { VersusMark, versusOf } from './Versus';
import { PalCtx, usePal, LIGHT, DARK } from './palette';
import { shown, type Card } from './layouts';
import { T } from './theme';
import timeline from './timeline.json';

const { fontFamily, waitUntilDone } = loadFont('normal', {
  weights: ['500', '700', '800', '900'],
  subsets: ['latin', 'vietnamese'],
});
const fontHandle = delayRender('be-vietnam-pro');
waitUntilDone().then(() => continueRender(fontHandle));

const CardView: React.FC<{ card: Card }> = ({ card }) => {
  const { fps } = useVideoConfig();
  const sc = card.screen;
  if (!sc) return null;
  const at = (sc.at ?? card.start) * fps;

  // Mỗi chương một màn hình chiếm khung, đứng yên suốt chương -- đúng như
  // video mẫu. Lời thoại do <Caption> vẽ riêng ở đáy khung.
  switch (sc.kind) {
    case 'shot':
      return <ShotScreen file={sc.file!} at={at} title={sc.eyebrow}
                         sourceUrl={sc.sourceUrl} ff={fontFamily} />;
    case 'hook':
      return <HookScreen eyebrow={sc.eyebrow ?? ''} title={sc.title ?? ''}
                         subtitle={sc.subtitle} tiles={sc.tiles ?? []}
                         ff={fontFamily} at={at} />;
    case 'statement':
      return <StatementScreen eyebrow={sc.eyebrow} lead={sc.lead ?? ''}
                              highlight={sc.highlight ?? ''}
                              ff={fontFamily} at={at} />;
    case 'cards':
      return <CardsScreen title={sc.eyebrow ?? ''} items={sc.items ?? []}
                          ff={fontFamily} at={at} />;
    case 'element':
      return <ElementView at={at} ff={fontFamily}
                          pick={{ kind: sc.element!,
                                  nodes: (sc.items ?? []).map((i) => i.label) }} />;
    case 'panel':
      return <ChartCard card={{ ...card, chart: sc.chart, visualAt: sc.at, anchor: 'mid' }}
                        ff={fontFamily} leaving={0} activeIdx={0} />;
    default:
      return null;
  }
};


/**
 * CAPTION -- lớp chữ DUY NHẤT của video, dựng theo đúng bản tham chiếu.
 *
 * Bản mẫu chỉ có một dòng ngắn (2-4 từ) căn giữa ở khoảng 72% chiều cao,
 * cả dòng hiện cùng lúc, và TỪ ĐANG ĐƯỢC NÓI được tô màu nhấn. Người dùng
 * nói rõ: không tiêu đề, chữ khớp từng tiếng, không quá nhanh không quá
 * chậm. Dòng chỉ bật lên khi từ đầu tiên của nó thật sự được nói, nên chữ
 * không bao giờ chạy trước tiếng.
 *
 * Chữ lấy từ KỊCH BẢN (đúng chính tả), mốc giờ lấy từ giọng đọc thật --
 * xem phần căn chỉnh trong tools/align.mjs.
 */
const Caption: React.FC<{ card: Card; activeIdx: number }> = ({ card, activeIdx }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const line = ls[activeIdx];
  if (!line) return null;
  const t = frame / fps;
  const words = line.words && line.words.length > 0
    ? line.words : [{ text: line.text, start: line.start, end: line.end }];
  const appear = interpolate(t - line.start, [0, 0.14], [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <div style={{
      position: 'absolute', left: 0, right: 0, top: '70%',
      display: 'flex', justifyContent: 'center', padding: '0 76px',
      pointerEvents: 'none',
    }}>
      <span style={{
        fontFamily, fontWeight: '800', fontSize: 62, lineHeight: 1.18,
        textAlign: 'center', letterSpacing: '-0.015em',
        textShadow: '0 4px 30px rgba(0,0,0,0.92)',
        opacity: appear,
        transform: `translateY(${interpolate(appear, [0, 1], [10, 0])}px)`,
      }}>
        {words.map((w, i) => {
          const on = t >= w.start - 0.02 && t < w.end + 0.06;
          return (
            <span key={i} style={{ color: on ? pal.accent : pal.ink }}>
              {w.text}{i < words.length - 1 ? ' ' : ''}
            </span>
          );
        })}
      </span>
    </div>
  );
};

/**
 * Hình minh hoạ cho thẻ KHÔNG có biểu đồ/ảnh chụp. Chọn theo chính câu
 * đang được nói (xem Elements.tsx). Trước đây chỗ này là một chấm sáng --
 * nó chẳng minh hoạ gì, chỉ lấp cho đỡ trống, và đó đúng là chỗ làm ẩu.
 * Không câu từ nào khớp thì KHÔNG vẽ gì: thà trống còn hơn hình sai nội dung.
 */

/**
 * Đếm CHƯƠNG ở góc trái trên. Bản tham chiếu ghi "01 / 09" -- chín chương
 * của bài, không phải số dòng phụ đề. Đếm theo dòng caption thì ra
 * "76 / 132", một con số chạy loạn chẳng nói lên điều gì.
 */
const Counter: React.FC<{ index: number; total: number }> = ({ index, total }) => {
  const pal = usePal();
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    <div style={{
      position: 'absolute', top: 128, left: 60,
      fontFamily, fontWeight: '700', fontSize: 23, letterSpacing: '0.22em',
      color: pal.ink, opacity: 0.4,
    }}>
      {pad(index + 1)} / {pad(total)}
    </div>
  );
};

/**
 * Vạch CHƯƠNG dọc mép trái: mỗi chương một đoạn, chương đang chạy sáng màu
 * nhấn, các chương khác mờ. Bản tham chiếu có đúng dải vạch này chạy suốt
 * mép trái khung -- nó cho biết bài dài bao nhiêu và đang ở đâu mà không
 * tốn một chữ nào.
 */
const ChapterRail: React.FC<{ index: number; total: number }> = ({ index, total }) => {
  const pal = usePal();
  if (total <= 1) return null;
  return (
    <div style={{
      position: 'absolute', left: 0, top: '16%', bottom: '16%', width: 5,
      display: 'flex', flexDirection: 'column', gap: 10, pointerEvents: 'none',
    }}>
      {Array.from({ length: total }, (_, i) => (
        <div key={i} style={{
          flex: 1, borderRadius: 3,
          background: i === index ? pal.accent : 'rgba(255,255,255,0.10)',
          opacity: i === index ? 0.95 : 1,
        }} />
      ))}
    </div>
  );
};

const Stage: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const cards = timeline.cards as Card[];

  const visible = cards.filter((c) => frame >= c.start * fps - 2 && frame < c.out * fps + 1);
  const cur = cards.filter((c) => frame >= c.start * fps).slice(-1)[0] ?? cards[0];
  // Danh sách chương theo đúng thứ tự xuất hiện -> "03 / 09" như bản mẫu.
  const chapters: string[] = [];
  for (const c of cards) if (chapters[chapters.length - 1] !== c.section) chapters.push(c.section);
  const chapIdx = Math.max(0, chapters.lastIndexOf(cur.section));

  const prog = interpolate(frame, [0, timeline.duration * fps], [0, 1], { extrapolateRight: 'clamp' });

  // Khi card "invert" phủ tấm lên toàn khung, nền hiệu dụng bị ĐẢO —
  // chip, ảnh chụp, icon và thanh tiến độ phải đảo màu theo, nếu không sẽ trắng trên trắng.
  const inverted = cur.variant === 'invert' && frame >= cur.start * fps + 7;
  const over = inverted ? (pal.dark ? LIGHT : DARK) : pal;


  let capIdx = 0;
  shown(cur).forEach((l, i) => { if (frame / fps >= l.start - 0.02) capIdx = i; });


  return (
    <>
      {visible.map((c) => <CardView key={c.index} card={c} />)}
      <PalCtx.Provider value={over}>
        <Caption card={cur} activeIdx={capIdx} />
        <Counter index={chapIdx} total={chapters.length} />
        <ChapterRail index={chapIdx} total={chapters.length} />
        {versusOf(cur)
          ? <VersusMark card={cur} ff={fontFamily} />
          : <BrandMark card={cur} />}
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 6, background: over.dark ? 'rgba(255,255,255,0.18)' : 'rgba(11,11,11,0.14)' }}>
          <div style={{ height: '100%', width: `${prog * 100}%`, background: over.ink }} />
        </div>
      </PalCtx.Provider>
    </>
  );
};

export const KineticShort: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = palAt(frame / fps);

  return (
    <AbsoluteFill style={{ backgroundColor: pal.dark ? '#080808' : '#EDECEA' }}>
      <BgVideo />
      <PalCtx.Provider value={pal}>
        <Stage />
      </PalCtx.Provider>
      <Audio src={staticFile('voice.mp3')} />
    </AbsoluteFill>
  );
};
