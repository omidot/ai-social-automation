import React from 'react';
import {
  AbsoluteFill, Audio, continueRender, delayRender, interpolate, spring,
  staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import { loadFont } from '@remotion/google-fonts/BeVietnamPro';
import { BgVideo, palAt } from './BgVideo';
import { BrandMark } from './BrandMark';
import { ChartCard } from './Chart';
import { Headline } from './Headline';
import { ScreenshotCard } from './Screenshot';
import { VersusMark, versusOf } from './Versus';
import { PalCtx, usePal, LIGHT, DARK } from './palette';
import { Stack, Hero, Invert, Mark, Stair, Numeral, Strike, shown, WordFade, type Card } from './layouts';
import { T } from './theme';
import timeline from './timeline.json';

const { fontFamily, waitUntilDone } = loadFont('normal', {
  weights: ['500', '700', '800', '900'],
  subsets: ['latin', 'vietnamese'],
});
const fontHandle = delayRender('be-vietnam-pro');
waitUntilDone().then(() => continueRender(fontHandle));

const CardView: React.FC<{ card: Card }> = ({ card }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const leaving = frame - (card.out * fps - T.EXIT);

  let activeIdx = 0;
  shown(card).forEach((l, i) => { if (t >= l.start - 0.02) activeIdx = i; });

  // Cảnh "đấu" chiếm nửa trên khung cho hai ô logo -- chữ phải tụt xuống,
  // không thì đè lên nhau.
  // num bị bỏ: con số đó chỉ là mảnh của tên model ("GPT-6" -> 6), dán
  // nó lên huy hiệu cạnh hai ô logo là vô nghĩa.
  // Thẻ kể chuyện thường (không phải hero/invert -- hai biến thể dành riêng
  // cho khoảnh khắc mở/chốt) luôn neo xuống đáy khung như phụ đề thật của
  // bản tham chiếu, bất kể variants.py gán anchor gì -- không còn trôi nổi
  // giữa khung.
  // Thẻ có HÌNH (biểu đồ/ảnh chụp) giữ nguyên vị trí giữa khung cho hình;
  // caption lời nói được vẽ riêng ở đáy bởi <Caption>.
  if (card.chart) return <ChartCard card={{ ...card, anchor: 'mid' }} ff={fontFamily} leaving={leaving} activeIdx={activeIdx} />;
  if (card.screenshotFile) return <ScreenshotCard card={card} ff={fontFamily} leaving={leaving} activeIdx={activeIdx} />;

  const isEmphasis = card.variant === 'hero' || card.variant === 'invert';
  const shifted = versusOf(card)
    ? { ...card, anchor: 'low' as const, num: undefined }
    : isEmphasis ? card : { ...card, anchor: 'low' as const };
  const p = { card: shifted, ff: fontFamily, leaving, activeIdx };
  switch (card.variant) {
    case 'hero': return <Hero {...p} />;
    case 'invert': return <Invert {...p} />;
    case 'mark': return <Mark {...p} />;
    case 'stair': return <Stair {...p} />;
    case 'numeral': return <Numeral {...p} />;
    case 'strike': return <Strike {...p} />;
    case 'right': return <Stack {...p} mirror />;
    default: return <Stack {...p} />;
  }
};

const Chip: React.FC<{ label: string; key0: number }> = ({ label, key0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const s = spring({ frame: frame - key0, fps, config: { damping: 15, stiffness: 220, mass: 0.6 } });
  return (
    <div style={{ position: 'absolute', top: 132, left: 0, right: 0, display: 'flex', justifyContent: 'center', padding: '0 96px' }}>
      <div
        style={{
          fontFamily, fontWeight: '800', fontSize: 30, letterSpacing: '0.04em', color: pal.ink,
          textAlign: 'center', textTransform: 'uppercase', textShadow: pal.shadow,
          opacity: interpolate(s, [0, 1], [0, 0.92]),
          transform: `translateY(${interpolate(s, [0, 1], [-12, 0])}px)`,
        }}
      >
        {label}
      </div>
    </div>
  );
};

/**
 * Caption lời nói ở ĐÁY khung, dành cho thẻ mà phần giữa đã bị HÌNH chiếm
 * (biểu đồ, ảnh chụp). Các biến thể chữ tự vẽ caption của mình, nên lớp
 * này chỉ bù cho thẻ có hình -- trước đây thẻ có hình không hiện lời nói
 * nào, người xem mất mạch giữa chừng.
 */
const Caption: React.FC<{ card: Card; activeIdx: number }> = ({ card, activeIdx }) => {
  const pal = usePal();
  const ls = shown(card);
  const line = ls[activeIdx];
  if (!line) return null;
  return (
    <div style={{
      position: 'absolute', left: 0, right: 0, bottom: 236,
      display: 'flex', justifyContent: 'center', padding: '0 84px',
      pointerEvents: 'none',
    }}>
      <span style={{
        fontFamily, fontWeight: '800', fontSize: 56, lineHeight: 1.16,
        color: pal.ink, textAlign: 'center', letterSpacing: '-0.01em',
        textShadow: '0 4px 28px rgba(0,0,0,0.9)',
      }}><WordFade line={line} /></span>
    </div>
  );
};

/**
 * Chấm sáng "hiện diện": khi thẻ KHÔNG có biểu đồ/ảnh/đấu, giữa khung
 * trống đen -- đúng cái người dùng chụp màn hình phàn nàn. Bản tham chiếu
 * luôn có một điểm sáng nhỏ đập nhịp ở đó. Không dựng được minh hoạ riêng
 * theo từng chủ đề (không có dữ liệu để vẽ), nhưng một chấm sáng thở đều
 * vẫn hơn khung đen trơn.
 */
const Presence: React.FC = () => {
  const frame = useCurrentFrame();
  const pal = usePal();
  const beat = 0.5 + 0.5 * Math.sin(frame / 26);
  return (
    <div style={{
      position: 'absolute', left: 0, right: 0, top: '52%',
      display: 'flex', justifyContent: 'center', pointerEvents: 'none',
    }}>
      <div style={{
        width: 96, height: 96, borderRadius: '50%',
        background: pal.dark ? '#F4F3F1' : '#0B0B0B',
        boxShadow: `0 0 ${46 + beat * 34}px ${14 + beat * 8}px ${pal.accent}45`,
        opacity: 0.88, transform: `scale(${1 + beat * 0.07})`,
      }} />
    </div>
  );
};

/** Số thẻ ở góc trái trên -- cho người xem biết đang ở đâu trong mạch bài. */
const Counter: React.FC<{ index: number; total: number }> = ({ index, total }) => {
  const pal = usePal();
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    <div style={{
      position: 'absolute', top: 138, left: 56,
      fontFamily, fontWeight: '700', fontSize: 24, letterSpacing: '0.22em',
      color: pal.ink, opacity: 0.45,
    }}>
      {pad(index + 1)} / {pad(total)}
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
  const chipStart = cards.find((c) => c.section === cur.section)!.start * fps;
  const prog = interpolate(frame, [0, timeline.duration * fps], [0, 1], { extrapolateRight: 'clamp' });

  // Khi card "invert" phủ tấm lên toàn khung, nền hiệu dụng bị ĐẢO —
  // chip, ảnh chụp, icon và thanh tiến độ phải đảo màu theo, nếu không sẽ trắng trên trắng.
  const inverted = cur.variant === 'invert' && frame >= cur.start * fps + 7;
  const over = inverted ? (pal.dark ? LIGHT : DARK) : pal;

  // Tiêu đề chỉ đổi khi sang card KỊCH BẢN khác, không đổi theo từng thẻ
  // caption -- nên nó đứng yên nhiều giây như bản tham chiếu.
  const headStart = (cards.find((c) => c.headlineAt === cur.headlineAt) ?? cur).start * fps;
  // Ảnh chụp/versus chiếm hết khung; tiêu đề in đè lên sẽ rối. Thẻ 'invert'
  // thì VẪN cần tiêu đề -- bỏ nó ra làm thẻ chốt thành khung trắng trơn chỉ
  // có một cụm chữ xám (đo thật trên bản render), đúng kiểu "đen/trắng thui"
  // mà người dùng phàn nàn. Màu đã tự đảo theo PalCtx bên dưới.
  const showHead = !cur.screenshotFile && !versusOf(cur);

  // Thẻ có HÌNH không tự vẽ lời nói -> cần lớp caption riêng ở đáy.
  const hasVisual = Boolean(cur.chart) || Boolean(cur.screenshotFile);
  let capIdx = 0;
  shown(cur).forEach((l, i) => { if (frame / fps >= l.start - 0.02) capIdx = i; });

  // Giữa khung trống đen khi thẻ chẳng có hình gì -- chấm sáng lấp chỗ đó.
  const bare = !hasVisual && !versusOf(cur)
    && cur.variant !== 'hero' && cur.variant !== 'invert';

  return (
    <>
      {visible.map((c) => <CardView key={c.index} card={c} />)}
      <PalCtx.Provider value={over}>
        {bare ? <Presence /> : null}
        {hasVisual ? <Caption card={cur} activeIdx={capIdx} /> : null}
        {showHead ? <Headline card={cur} ff={fontFamily} at={headStart} /> : null}
        <Chip label={cur.section} key0={chipStart} />
        <Counter index={cur.index} total={cards.length} />
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
