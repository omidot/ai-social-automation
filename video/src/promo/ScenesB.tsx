import React from 'react';
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { BlurIn, Eyebrow, UICard } from './Type';
import { Mascot } from './Mascot';
import { prog, power3Out, C, bgOf, tiltOf, CARD_RADIUS, CARD_SHADOW } from './theme';
import type { Fonts } from './ScenesA';

const PAD = 86;

/* ================= 04 — NỘI DUNG: bento các bước ================= */

/**
 * Lưới bento 6 ô: 4 ô thật lấp đầy lần lượt đúng lúc bước đó được nói tới,
 * 2 ô còn lại giữ viền đứt làm chỗ thở cho bố cục (đúng mô tả "ô viền đứt
 * lấp đầy lần lượt").
 */
export const StepsScene: React.FC<{ s: any; f: Fonts; mascot?: string | null }> =
({ s, f, mascot }) => {
  const c = bgOf('paper');
  return (
    <AbsoluteFill style={{ padding: `${PAD + 80}px ${PAD}px ${PAD}px` }}>
      <Eyebrow text={s.eyebrow} at={s.at + 0.2} mono={f.mono} color={c.dim} />
      <div style={{ height: 40 }} />
      <BlurIn text={s.title} accents={s.accent} at={s.titleAt}
              sans={f.sans} serif={f.serif} color={c.fg}
              accentColor={C.orange} size={92} lineHeight={1.03} />

      <div style={{
        marginTop: 64, display: 'grid',
        gridTemplateColumns: '1fr 1fr', gap: 26,
      }}>
        {s.steps.map((st: any, i: number) => (
          <StepBox key={i} st={st} i={i} f={f} />
        ))}
        <GhostBox />
        <GhostBox />
      </div>

      <Mascot file={mascot} pose="travel" at={s.at + 1.2} size={210}
              style={{ right: PAD - 30, bottom: 48 }} />
    </AbsoluteFill>
  );
};

/**
 * Một ô bento. TRƯỚC mốc của nó là một ô VIỀN ĐỨT rỗng, tới mốc thì thẻ
 * trắng lấp vào -- đúng mô tả "ô viền đứt lấp đầy lần lượt".
 *
 * Quan trọng là ô rỗng vẫn chiếm sẵn đúng chỗ: nếu để ô chưa tới lúc tàng
 * hình hoàn toàn thì giữa khung hiện ra một mảng trống lớn, và lưới bento
 * nhảy giật mỗi lần một bước xuất hiện.
 */
const StepBox: React.FC<{ st: any; i: number; f: Fonts }> = ({ st, i, f }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = power3Out(prog(frame / fps, st.at, 0.52));
  const file = st.logo ? `promo/dith/${st.logo.split('/').pop()}` : null;
  return (
    <div style={{ position: 'relative', minHeight: 268 }}>
      {/* ô viền đứt, mờ dần đi khi thẻ thật lấp vào */}
      <div style={{
        position: 'absolute', inset: 0, borderRadius: CARD_RADIUS,
        border: '2px dashed rgba(20,26,34,0.24)',
        opacity: 1 - p,
      }} />
      <div style={{
        position: 'absolute', inset: 0,
        background: '#FFFFFF', borderRadius: CARD_RADIUS, boxShadow: CARD_SHADOW,
        padding: '30px 28px 34px',
        display: 'flex', flexDirection: 'column', gap: 12,
        opacity: p,
        filter: p < 0.99 ? `blur(${(9 * (1 - p)).toFixed(2)}px)` : 'none',
        transform: `translateY(${(30 * (1 - p)).toFixed(2)}px)`
          + ` rotate(${(tiltOf(i) * 0.22 * p).toFixed(2)}deg)`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{
            fontFamily: f.mono, fontSize: 26, fontWeight: 700,
            color: C.orange, letterSpacing: '0.1em',
          }}>{st.k}</span>
          {file ? (
            <Img src={staticFile(file)}
                 style={{ width: 52, height: 52, objectFit: 'contain' }} />
          ) : null}
        </div>
        <span style={{
          fontFamily: f.sans, fontWeight: '800', fontSize: 38,
          color: C.ink, letterSpacing: '-0.02em', lineHeight: 1.14,
        }}>{st.label}</span>
        <span style={{
          fontFamily: f.sans, fontWeight: '400', fontSize: 26,
          color: 'rgba(20,26,34,0.6)', lineHeight: 1.34,
        }}>{st.note}</span>
      </div>
    </div>
  );
};

/** Hai ô nhỏ luôn để trống, giữ nhịp lưới bento 6 ô. */
const GhostBox: React.FC = () => (
  <div style={{
    borderRadius: CARD_RADIUS, minHeight: 104,
    border: '2px dashed rgba(20,26,34,0.18)',
  }} />
);

/* ============ 05 — BẰNG CHỨNG: tương phản + số đếm lên ============ */

export const ProofScene: React.FC<{ s: any; f: Fonts }> = ({ s, f }) => {
  const c = bgOf('dark');
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const cnt = s.counter;
  const cp = power3Out(prog(t, cnt.at, Math.max(0.3, cnt.landAt - cnt.at)));
  const shown = Math.round(cnt.from + (cnt.to - cnt.from) * cp);
  const sp = power3Out(prog(t, s.stampAt, 0.44));

  return (
    <AbsoluteFill style={{
      padding: `${PAD + 80}px ${PAD}px ${PAD}px`, justifyContent: 'center',
    }}>
      <Eyebrow text={s.eyebrow} at={s.at + 0.2} mono={f.mono} color={c.dim} />
      <div style={{ height: 44 }} />
      <BlurIn text={s.lead} accents={s.leadAccent} at={s.leadAt}
              sans={f.sans} serif={f.serif} color={c.fg}
              accentColor={C.orange} size={88} lineHeight={1.04} />

      <div style={{ marginTop: 50, display: 'flex', flexDirection: 'column', gap: 18 }}>
        <SideCard text={s.contrast.lose.text} at={s.contrast.lose.at} i={0} lose f={f} />
        <SideCard text={s.contrast.win.text} at={s.contrast.win.at} i={1} f={f} />
      </div>

      {/* Con số thật đếm lên, dừng đúng lúc nói xong.
          Lời đọc là "30–50 người" chứ không phải "50 người", nên cận dưới
          phải đứng sẵn bên trái và chỉ cận trên mới chạy số -- hiện mỗi 50
          là nói một đằng, chữ một nẻo. */}
      {/* Cả khối số chỉ xuất hiện TỪ mốc của nó. Để hiện sẵn thì suốt hơn
          ba chục giây trước đó khung đứng im ở "30–30", vừa sai nghĩa vừa
          làm hỏng cú đếm lên khi tới lúc. */}
      <div style={{
        marginTop: 62,
        opacity: cp > 0 ? 1 : 0,
        transform: `translateY(${(24 * (1 - Math.min(1, cp * 4))).toFixed(2)}px)`,
      }}>
        <span style={{
          fontFamily: f.sans, fontWeight: '500', fontSize: 38,
          color: c.dim, display: 'block', marginBottom: 6,
        }}>{cnt.label}</span>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 20 }}>
          <span style={{
            fontFamily: f.sans, fontWeight: '800', fontSize: 210,
            color: C.orange, letterSpacing: '-0.05em', lineHeight: 1,
            fontVariantNumeric: 'tabular-nums',
          }}>{cnt.from}–{shown}</span>
          <span style={{
            fontFamily: f.sans, fontWeight: '800', fontSize: 62, color: c.fg,
          }}>{cnt.unit}</span>
        </div>
      </div>

      {/* tem cam đóng nghiêng */}
      <div style={{
        position: 'absolute', right: PAD, top: 300,
        background: C.orange, padding: '14px 26px 18px',
        borderRadius: 8,
        opacity: sp,
        transform: `rotate(-7deg) scale(${(0.7 + 0.3 * sp).toFixed(3)})`,
      }}>
        <span style={{
          fontFamily: f.mono, fontWeight: 700, fontSize: 28,
          color: C.ink, letterSpacing: '0.06em', textTransform: 'uppercase',
        }}>{s.stamp}</span>
      </div>
    </AbsoluteFill>
  );
};

const SideCard: React.FC<{
  text: string; at: number; i: number; lose?: boolean; f: Fonts;
}> = ({ text, at, i, lose, f }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = power3Out(prog(frame / fps, at, 0.5));
  return (
    <div style={{
      background: lose ? 'rgba(251,246,232,0.07)' : '#FFFFFF',
      border: lose ? '1px solid rgba(251,246,232,0.2)' : 'none',
      borderRadius: CARD_RADIUS, padding: '26px 32px',
      opacity: p,
      filter: p < 0.99 ? `blur(${(8 * (1 - p)).toFixed(2)}px)` : 'none',
      transform: `translateX(${((lose ? -56 : 56) * (1 - p)).toFixed(2)}px)`
        + ` rotate(${(tiltOf(i) * 0.3 * p).toFixed(2)}deg)`,
    }}>
      <span style={{
        fontFamily: f.sans, fontWeight: lose ? '500' : '800', fontSize: 38,
        color: lose ? 'rgba(251,246,232,0.62)' : C.ink,
        textDecoration: lose ? 'line-through' : 'none',
        lineHeight: 1.2, letterSpacing: '-0.01em',
      }}>{text}</span>
    </div>
  );
};

/* ===================== 06 — CTA (nền giấy) ===================== */

export const CtaScene: React.FC<{ s: any; f: Fonts; mascot?: string | null }> =
({ s, f, mascot }) => {
  const c = bgOf('paper');
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const bp = power3Out(prog(t, s.ctaAt, 0.42));
  const fp = power3Out(prog(t, s.ctaAt + 0.3, 0.4));
  return (
    <AbsoluteFill style={{
      padding: `${PAD + 80}px ${PAD}px ${PAD}px`, justifyContent: 'center',
    }}>
      <Eyebrow text={s.eyebrow} at={s.at + 0.15} mono={f.mono} color={c.dim} />
      <div style={{ height: 44 }} />
      <BlurIn text={s.title} accents={s.accent} at={s.titleAt}
              sans={f.sans} serif={f.serif} color={c.fg}
              accentColor={C.orange} size={104} lineHeight={1.03} />

      <div style={{
        marginTop: 64, display: 'inline-flex', alignSelf: 'flex-start',
        alignItems: 'center', gap: 18,
        background: C.ink, borderRadius: 999, padding: '26px 46px',
        opacity: bp,
        transform: `translateY(${(30 * (1 - bp)).toFixed(2)}px) scale(${(0.9 + 0.1 * bp).toFixed(3)})`,
      }}>
        <span style={{
          fontFamily: f.sans, fontWeight: '800', fontSize: 52, color: C.paper,
          letterSpacing: '-0.01em',
        }}>{s.cta}</span>
        <span style={{ fontFamily: f.sans, fontWeight: '800', fontSize: 52, color: C.orange }}>→</span>
      </div>

      <div style={{ marginTop: 30, opacity: fp }}>
        <span style={{ fontFamily: f.mono, fontSize: 32, color: c.dim, letterSpacing: '0.06em' }}>
          {s.foot}
        </span>
      </div>

      <Mascot file={mascot} pose="wink" at={s.at + 0.5} winkAt={s.winkAt} size={330}
              style={{ right: PAD - 40, bottom: 56 }} />
    </AbsoluteFill>
  );
};
