import React from 'react';
import {
  AbsoluteFill, Audio, continueRender, delayRender, interpolate, spring,
  staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import { loadFont } from '@remotion/google-fonts/BeVietnamPro';
import { BgVideo, palAt } from './BgVideo';
import { ChartCard } from './Chart';
import { ScreenshotCard } from './Screenshot';
import { HookScreen, StatementScreen, ShotScreen, CardsScreen, BrandScreen,
         BrandCardsScreen } from './Screens';
import { ElementView } from './Elements';
import { EditorialPerson } from './Editorial';
import { loadFont as loadSerif } from '@remotion/google-fonts/PlayfairDisplay';
import { PalCtx, usePal, LIGHT, DARK } from './palette';
import { shown, type Card } from './layouts';
import { T } from './theme';
import timeline from './timeline.json';

const { fontFamily, waitUntilDone } = loadFont('normal', {
  weights: ['500', '700', '800', '900'],
  subsets: ['latin', 'vietnamese'],
});
const serif = loadSerif('normal', { weights: ['700', '900'], subsets: ['latin', 'vietnamese'] });
const serifHandle = delayRender('playfair');
serif.waitUntilDone().then(() => continueRender(serifHandle));

const fontHandle = delayRender('be-vietnam-pro');
waitUntilDone().then(() => continueRender(fontHandle));

type Screen = NonNullable<Card['screen']> & { until?: number };

/**
 * Vẽ ĐÚNG MỘT màn hình tại mỗi thời điểm, kèm vào/ra mờ dần.
 *
 * Trước đây màn hình gắn vào từng thẻ caption và mỗi thẻ tự vẽ lại nó. Vì
 * nhiều thẻ cùng hiện một lúc, cùng một màn bị dựng chồng nhiều lần với mốc
 * giờ khác nhau -> hiệu ứng chạy lại liên tục, nhìn ra đúng cái "nhấp nháy
 * miết" người dùng chỉ ra. Giờ màn hình là một dòng thời gian riêng và chỗ
 * này chọn ra một cái duy nhất.
 */
const ScreenView: React.FC<{ sc: Screen }> = ({ sc }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = (sc.at ?? 0) * fps;

  // Vào mờ dần, ra mờ dần -- người dùng yêu cầu rõ: hình xuất hiện và biến
  // mất phải có chuyển, không bật/tắt phựt.
  const IN = 9, OUT = 11;
  const endF = (sc.until ?? 1e9) * fps;
  const fade = Math.min(
    interpolate(frame - at, [0, IN], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }),
    interpolate(endF - frame, [0, OUT], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }),
  );
  if (fade <= 0) return null;

  let inner: React.ReactNode = null;
  switch (sc.kind) {
    case 'shot':
      inner = <ShotScreen file={sc.file!} at={at} title={sc.eyebrow}
                          sourceUrl={sc.sourceUrl} ff={fontFamily} />; break;
    case 'hook':
      inner = <HookScreen eyebrow={sc.eyebrow ?? ''} title={sc.title ?? ''}
                          subtitle={sc.subtitle} tiles={sc.tiles ?? []}
                          ff={fontFamily} at={at} />; break;
    case 'statement':
      inner = <StatementScreen eyebrow={sc.eyebrow} lead={sc.lead ?? ''}
                               highlight={sc.highlight ?? ''}
                               ff={fontFamily} at={at} />; break;
    case 'person':
      inner = <EditorialPerson
                variant={sc.variant as never}
                date={sc.date} headline={sc.headline ?? sc.name ?? ''}
                standfirst={sc.standfirst} masthead={sc.masthead}
                name={sc.name} role={sc.role}
                cutFile={sc.file!} credit={sc.credit}
                serif={serif.fontFamily} sans={fontFamily} at={at} />; break;
    case 'brandcards':
      inner = <BrandCardsScreen tile={(sc.tiles ?? [])[0] ?? { label: '' }}
                                items={sc.items ?? []} ff={fontFamily} at={at} />; break;
    case 'brand':
    case 'brandpair':
      inner = <BrandScreen tiles={sc.tiles ?? []} eyebrow={sc.eyebrow}
                           ff={fontFamily} at={at} />; break;
    case 'cards':
      inner = <CardsScreen title={sc.eyebrow ?? ''} items={sc.items ?? []}
                           ff={fontFamily} at={at} />; break;
    case 'element':
      inner = <ElementView at={at} ff={fontFamily}
                          pick={{ kind: sc.element!,
                                  nodes: (sc.items ?? []).map((i) => i.label) }} />; break;
    case 'panel':
      inner = <ChartCard ff={fontFamily} leaving={0} activeIdx={0}
                card={{ chart: sc.chart, visualAt: sc.at, anchor: 'mid',
                        start: sc.at ?? 0, out: sc.until ?? 0,
                        lines: [], index: 0, end: 0, section: '',
                        variant: 'stack', motion: 'rise', exit: 'up' } as Card} />; break;
    default:
      return null;
  }
  return <AbsoluteFill style={{ opacity: fade }}>{inner}</AbsoluteFill>;
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
const Caption: React.FC<{ card: Card; activeIdx: number; asideOf?: boolean }> =
({ card, activeIdx, asideOf }) => {
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
      position: 'absolute',
      // Màn nhân vật: người chiếm nửa phải khung, nên caption dạt hẳn sang
      // TRÁI và hẹp lại. Để giữa như cũ là chữ nằm đè lên mặt người.
      // right lớn hơn = khung chữ HẸP hơn (chừa nhiều đất cho người bên
      // phải). Lần trước để 42% tức khung RỘNG hơn 48% -- ngược ý định,
      // nên chữ vẫn chạm tóc. 56% mới thực sự siết khung về còn 44% khung.
      left: 0, right: asideOf ? '56%' : 0, top: asideOf ? '50%' : '70%',
      display: 'flex', justifyContent: asideOf ? 'flex-start' : 'center',
      padding: asideOf ? '0 20px 0 70px' : '0 76px',
      pointerEvents: 'none',
    }}>
      <span style={{
        // Bên trong flex item, chiều rộng mặc định co theo NỘI DUNG KHÔNG
        // XUỐNG DÒNG (min-width: auto của flexbox) chứ không co theo khung
        // cha -- đo thật: câu dài tràn hẳn qua nửa phải, đè lên mặt người
        // dù container đã bị chặn ở right:48%. minWidth:0 tắt hành vi đó
        // để chữ xuống dòng đúng bên trong khung.
        minWidth: 0, maxWidth: '100%',
        fontFamily, fontWeight: '800', fontSize: asideOf ? 38 : 62, lineHeight: 1.24,
        textAlign: asideOf ? 'left' : 'center', letterSpacing: '-0.015em',
        textShadow: asideOf ? 'none' : '0 4px 30px rgba(0,0,0,0.92)',
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

  const cur = cards.filter((c) => frame >= c.start * fps).slice(-1)[0] ?? cards[0];
  // Đếm theo chính DÒNG THỜI GIAN MÀN HÌNH -- trước đây đếm theo section
  // kịch bản (cố định 6), nên chip góc trên vẫn ghi "0X / 06" suốt video dù
  // bên dưới đã đổi màn 14 lần. Bộ đếm dựng ra để nói "còn bao nhiêu nữa",
  // đếm sai số thì đúng là còn cái cảm giác "6 slide" mà người dùng thấy.
  const screensAll0 = ((timeline as { screens?: Screen[] }).screens ?? []);
  const t0 = frame / fps;
  const chapIdx = Math.max(0, screensAll0.filter((x) => t0 >= (x.at ?? 0)).length - 1);
  const chapTotal = screensAll0.length || 1;

  const prog = interpolate(frame, [0, timeline.duration * fps], [0, 1], { extrapolateRight: 'clamp' });

  // Màn báo giấy có nền SÁNG -> caption trắng và khung viền phải đảo sang
  // mực đen, nếu không chữ trắng nằm trên giấy trắng là mất hút.
  const screensAll = ((timeline as { screens?: Screen[] }).screens ?? []);
  const curScreen = screensAll.filter((x) => frame / fps >= (x.at ?? 0)).slice(-1)[0];
  const onPaper = curScreen?.kind === 'person';
  const over = onPaper ? LIGHT : pal;


  let capIdx = 0;
  shown(cur).forEach((l, i) => { if (frame / fps >= l.start - 0.02) capIdx = i; });


  return (
    <>
      {(() => {
        const screens = ((timeline as { screens?: Screen[] }).screens ?? []);
        const t = frame / fps;
        const sc = screens.filter((x) => t >= (x.at ?? 0)).slice(-1)[0];
        return sc ? <ScreenView sc={sc} /> : null;
      })()}
      <PalCtx.Provider value={over}>
        <Caption card={cur} activeIdx={capIdx} asideOf={onPaper} />
        <Counter index={chapIdx} total={chapTotal} />
        <ChapterRail index={chapIdx} total={chapTotal} />
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
