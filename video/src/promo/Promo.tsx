import React from 'react';
import { AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { loadFont as loadSans } from '@remotion/google-fonts/BeVietnamPro';
import { loadFont as loadSerif } from '@remotion/google-fonts/Newsreader';
import { loadFont as loadMono } from '@remotion/google-fonts/JetBrainsMono';
import { loadFont as loadHand } from '@remotion/google-fonts/Caveat';

import scenesJson from './scenes.json';
import { Chrome } from './Chrome';
import { HookScene, BeliefsScene, DecisiveScene } from './ScenesA';
import { StepsScene, ProofScene, CtaScene } from './ScenesB';
import { bgOf, power4InOut, prog, type BgKind } from './theme';

/**
 * VIDEO PROMO 9:16 -- sáu cảnh, bám đúng mốc giờ lời đọc thật.
 *
 * Toàn bộ chuyển động suy ra từ `frame` nên bản dựng TẤT ĐỊNH: seek tới đâu
 * cũng ra đúng khung đó, và render lại không lệch so với snapshot đã duyệt.
 * Không có Math.random hay Date ở bất kỳ đâu trong cây này.
 *
 * Tiếng Việt chỉ hiện ở sans/serif/mono -- cả ba font đều có bộ dấu đầy đủ.
 * Caveat KHÔNG có bộ dấu nên chỉ dùng cho chữ viết tay đã bỏ dấu sẵn trong
 * scenes.json.
 */

const sans = loadSans('normal', { weights: ['400', '500', '800'], subsets: ['vietnamese', 'latin'] });
const serif = loadSerif('italic', { weights: ['500'], subsets: ['vietnamese', 'latin'] });
const mono = loadMono('normal', { weights: ['500', '600', '700'], subsets: ['vietnamese', 'latin'] });
const hand = loadHand('normal', { weights: ['600'], subsets: ['latin'] });

export const promoFonts = {
  sans: sans.fontFamily,
  serif: serif.fontFamily,
  mono: mono.fontFamily,
  hand: hand.fontFamily,
};

export const waitForPromoFonts = () => Promise.all([
  sans.waitUntilDone(), serif.waitUntilDone(),
  mono.waitUntilDone(), hand.waitUntilDone(),
]);

type Scene = (typeof scenesJson.scenes)[number];

/** Độ dài cú whip giữa hai cảnh. */
const WHIP = 0.34;

export const Promo: React.FC<{ mascot?: string | null }> = ({ mascot = null }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const scenes = scenesJson.scenes as Scene[];
  // Cảnh đang chạy = cảnh cuối cùng đã tới mốc. Duyệt tay thay vì
  // findLastIndex để không phụ thuộc lib ES2023 của bản tsconfig này.
  let idx = 0;
  for (let i = 0; i < scenes.length; i += 1) {
    if (t >= scenes[i].at) idx = i;
  }
  const cur = scenes[idx];
  const c = bgOf(cur.bg as BgKind);

  // Whip ngang kèm blur ngay sau mỗi mốc đổi cảnh: cảnh mới lao vào từ phải.
  const wp = power4InOut(prog(t, cur.at, WHIP));
  const whipX = (1 - wp) * 150;
  const whipBlur = (1 - wp) * 22;

  return (
    <AbsoluteFill style={{ backgroundColor: c.bg }}>
      <Audio src={staticFile(scenesJson.audio)} />

      <AbsoluteFill style={{
        transform: `translateX(${whipX.toFixed(2)}px)`,
        filter: whipBlur > 0.2 ? `blur(${whipBlur.toFixed(2)}px)` : 'none',
      }}>
        <SceneBody s={cur} mascot={mascot} />
      </AbsoluteFill>

      <Chrome n={cur.n} name={cur.name} sceneAt={cur.at}
              brand={scenesJson.brand} fg={c.fg} dim={c.dim} mono={promoFonts.mono} />
    </AbsoluteFill>
  );
};

const SceneBody: React.FC<{ s: Scene; mascot?: string | null }> = ({ s, mascot }) => {
  const f = promoFonts;
  switch (s.kind) {
    case 'hook':     return <HookScene s={s} f={f} mascot={mascot} />;
    case 'beliefs':  return <BeliefsScene s={s} f={f} />;
    case 'decisive': return <DecisiveScene s={s} f={f} />;
    case 'steps':    return <StepsScene s={s} f={f} mascot={mascot} />;
    case 'proof':    return <ProofScene s={s} f={f} />;
    case 'cta':      return <CtaScene s={s} f={f} mascot={mascot} />;
    default:         return null;
  }
};

export const promoConfig = {
  id: 'Promo',
  width: scenesJson.width,
  height: scenesJson.height,
  fps: scenesJson.fps,
  durationInFrames: Math.round(scenesJson.duration * scenesJson.fps),
};
