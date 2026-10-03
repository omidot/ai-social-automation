import React from 'react';
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { BlurIn, Eyebrow, UICard, MarkerStrike } from './Type';
import { Mascot, Bubble } from './Mascot';
import { prog, power3Out, C, bgOf } from './theme';

export type Fonts = { sans: string; serif: string; mono: string; hand: string };

const PAD = 86;

/* ===================== 01 — CÂU HỎI (nền giấy) ===================== */

export const HookScene: React.FC<{ s: any; f: Fonts; mascot?: string | null }> =
({ s, f, mascot }) => {
  const c = bgOf('paper');
  return (
    <AbsoluteFill style={{ padding: `${PAD + 80}px ${PAD}px ${PAD}px` }}>
      <Eyebrow text={s.eyebrow} at={s.at + 0.2} mono={f.mono} color={c.dim} />
      <div style={{ height: 46 }} />
      <BlurIn
        text={s.title} accents={s.accent} at={s.titleAt}
        sans={f.sans} serif={f.serif} color={c.fg} size={118}
        lineHeight={1.02}
      />
      {/* chữ viết tay KHÔNG dấu -- Caveat không có bộ dấu tiếng Việt */}
      <HandNote text={s.hand} at={s.handAt} hand={f.hand} />

      <Mascot file={mascot} pose="peek" at={s.at + 0.35} size={360}
              style={{ left: PAD - 20, bottom: 70 }} />
      <Bubble text={s.bubble} at={s.at + 1.0} hand={f.hand}
              style={{ left: PAD + 290, bottom: 350 }} />
    </AbsoluteFill>
  );
};

const HandNote: React.FC<{ text: string; at: number; hand: string }> =
({ text, at, hand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = power3Out(prog(frame / fps, at, 0.5));
  return (
    <div style={{
      marginTop: 34, opacity: p,
      transform: `translateY(${(22 * (1 - p)).toFixed(2)}px) rotate(-3deg)`,
      display: 'flex', alignItems: 'center', gap: 16,
    }}>
      <svg width={64} height={30} viewBox="0 0 64 30">
        <path d="M2 24 C18 4, 44 4, 60 18" fill="none"
              stroke={C.orange} strokeWidth={6} strokeLinecap="round"
              strokeDasharray={90} strokeDashoffset={90 * (1 - p)} />
      </svg>
      <span style={{ fontFamily: hand, fontSize: 64, color: C.orange }}>{text}</span>
    </div>
  );
};

/* ================= 02 — NIỀM TIN SAI (nền cam) ================= */

export const BeliefsScene: React.FC<{ s: any; f: Fonts }> = ({ s, f }) => {
  const c = bgOf('orange');
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const vp = power3Out(prog(frame / fps, s.verdictAt, 0.46));
  return (
    <AbsoluteFill style={{
      padding: `${PAD + 80}px ${PAD}px ${PAD}px`,
      justifyContent: 'center',
    }}>
      <Eyebrow text={s.eyebrow} at={s.at + 0.2} mono={f.mono} color={c.dim} />
      <div style={{ height: 54 }} />
      {s.cards.map((cd: any, i: number) => (
        <UICard key={i} at={cd.at} i={i} tiltScale={0.32}
                style={{ padding: '38px 44px', marginBottom: 38, position: 'relative' }}>
          <span style={{
            fontFamily: f.sans, fontWeight: '800', fontSize: 52,
            color: C.ink, letterSpacing: '-0.02em', lineHeight: 1.16,
          }}>{cd.text}</span>
          <MarkerStrike at={cd.strikeAt} />
        </UICard>
      ))}
      <div style={{
        marginTop: 26, opacity: vp,
        transform: `translateY(${(26 * (1 - vp)).toFixed(2)}px)`,
      }}>
        <span style={{
          fontFamily: f.sans, fontWeight: '800', fontSize: 86,
          color: C.ink, letterSpacing: '-0.03em',
        }}>{s.verdict}</span>
      </div>
    </AbsoluteFill>
  );
};

/* ================ 03 — ĐIỀU QUYẾT ĐỊNH (nền tối) ================ */

export const DecisiveScene: React.FC<{ s: any; f: Fonts }> = ({ s, f }) => {
  const c = bgOf('dark');
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const fp = power3Out(prog(t, s.footAt, 0.5));
  return (
    <AbsoluteFill style={{
      padding: `${PAD + 80}px ${PAD}px ${PAD}px`, justifyContent: 'center',
    }}>
      <Eyebrow text={s.eyebrow} at={s.at + 0.2} mono={f.mono} color={c.dim} />
      <div style={{ height: 50 }} />

      <BlurIn text={s.notLine} at={s.notAt} sans={f.sans} serif={f.serif}
              color={c.dim} size={74} lineHeight={1.08} />
      <div style={{ height: 26 }} />
      <BlurIn text={s.isLine} accents={s.isAccent} at={s.isAt}
              sans={f.sans} serif={f.serif} color={c.fg}
              accentColor={C.orange} size={94} lineHeight={1.04} />

      {/* hai chip hãng được nhắc tên -- logo đã dither 2 màu */}
      <div style={{ display: 'flex', gap: 22, marginTop: 52 }}>
        {s.chips.map((ch: any, i: number) => (
          <Chip key={i} chip={ch} f={f} />
        ))}
      </div>

      <div style={{
        marginTop: 58, opacity: fp,
        transform: `translateY(${(20 * (1 - fp)).toFixed(2)}px)`,
      }}>
        <span style={{
          fontFamily: f.serif, fontStyle: 'italic', fontSize: 46,
          color: c.dim, lineHeight: 1.3,
        }}>{s.foot}</span>
      </div>
    </AbsoluteFill>
  );
};

const Chip: React.FC<{ chip: any; f: Fonts }> = ({ chip, f }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = power3Out(prog(frame / fps, chip.at, 0.42));
  const file = chip.logo ? `promo/dith/${chip.logo.split('/').pop()}` : null;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 16,
      background: 'rgba(251,246,232,0.07)',
      border: '1px solid rgba(251,246,232,0.18)',
      borderRadius: 999, padding: '14px 30px 14px 16px',
      opacity: p,
      transform: `translateY(${(26 * (1 - p)).toFixed(2)}px) scale(${(0.9 + 0.1 * p).toFixed(3)})`,
    }}>
      {file ? (
        <Img src={staticFile(file)}
             style={{ width: 54, height: 54, objectFit: 'contain', borderRadius: 10 }} />
      ) : null}
      <span style={{
        fontFamily: f.mono, fontSize: 36, fontWeight: 600,
        color: C.paper, letterSpacing: '0.02em',
      }}>{chip.text}</span>
    </div>
  );
};
