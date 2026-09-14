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
import { VersusMark, versusOf } from './Versus';
import { PalCtx, usePal, LIGHT, DARK } from './palette';
import { Stack, Hero, Invert, Mark, Stair, Numeral, Strike, shown, type Card } from './layouts';
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
  const isEmphasis = card.variant === 'hero' || card.variant === 'invert';
  const shifted = versusOf(card)
    ? { ...card, anchor: 'low' as const, num: undefined }
    : isEmphasis ? card : { ...card, anchor: 'low' as const };
  const p = { card: shifted, ff: fontFamily, leaving, activeIdx };
  if (card.chart) return <ChartCard {...p} />;
  if (card.screenshotFile) return <ScreenshotCard {...p} />;
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

  return (
    <>
      {visible.map((c) => <CardView key={c.index} card={c} />)}
      <PalCtx.Provider value={over}>
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
