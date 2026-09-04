import React from 'react';
import {
  AbsoluteFill, Audio, continueRender, delayRender, interpolate, spring,
  staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import { loadFont } from '@remotion/google-fonts/BeVietnamPro';
import { BgVideo, palAt } from './BgVideo';
import { PalCtx, usePal, LIGHT, DARK } from './palette';
import { Shots } from './Shots';
import { Cutouts } from './Cutouts';
import { Sfx } from './Sfx';
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

  const p = { card, ff: fontFamily, leaving, activeIdx };
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
    <div style={{ position: 'absolute', top: 128, left: 0, right: 0, display: 'flex', justifyContent: 'center' }}>
      <div
        style={{
          fontFamily, fontWeight: '800', fontSize: 27, letterSpacing: '0.22em', color: pal.ink,
          border: `2.5px solid ${pal.ink}`, borderRadius: 999, padding: '13px 30px 12px',
          background: pal.dark ? 'rgba(0,0,0,0.34)' : 'rgba(255,255,255,0.40)',
          textTransform: 'uppercase', textShadow: pal.shadow,
          opacity: interpolate(s, [0, 1], [0, 1]),
          transform: `translateY(${interpolate(s, [0, 1], [-16, 0])}px) scale(${interpolate(s, [0, 1], [0.9, 1])})`,
        }}
      >
        {label}
      </div>
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
        <Shots ff={fontFamily} />
        <Chip label={cur.section} key0={chipStart} />
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
      {/* Cutout B-roll nổi TRÊN cả card "invert" (tấm phủ trắng toàn khung),
          nếu không ảnh sẽ bị tấm phủ che mất ở 2 card cuối. */}
      <Cutouts />
      <Audio src={staticFile('voice.mp3')} />
      <Sfx />
    </AbsoluteFill>
  );
};
