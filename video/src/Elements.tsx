import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { usePal } from './palette';

/**
 * BỘ HÌNH MINH HOẠ THEO NỘI DUNG ĐANG NÓI.
 *
 * Trước đây thẻ nào không có biểu đồ thì giữa khung chỉ có một chấm sáng --
 * nó không minh hoạ gì hết, chỉ là chỗ lấp cho đỡ trống, và người dùng đã
 * chỉ thẳng vào đó. Bản tham chiếu thì mỗi đoạn đều có một hình NÓI ĐÚNG
 * điều đang được kể: cái hộp chạy code, bức tường chặn, cửa sổ dòng lệnh,
 * đồng hồ tốc độ, thẻ giá...
 *
 * Ở đây mỗi hình được vẽ bằng CSS/SVG (không cần tải ảnh, không cần mạng),
 * và `pickElement` chọn hình dựa trên CHÍNH TỪ NGỮ đang được nói ra. Không
 * có từ khoá nào khớp thì KHÔNG vẽ gì -- thà để trống còn hơn dán một hình
 * sai nội dung.
 */

const MARKS = new RegExp('[̀-ͯ]', 'g');
const bare = (s: string) =>
  s.toLowerCase().replace(/đ/g, 'd').normalize('NFD').replace(MARKS, '')
    .replace(/[^a-z0-9 ]/g, ' ');

/* ---------------- khối dựng chung ---------------- */

const useRise = (at: number, delay = 0) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - at - delay, fps,
                     config: { damping: 21, stiffness: 150, mass: 0.85 } });
  return {
    opacity: interpolate(s, [0, 1], [0, 1]),
    transform: `translateY(${interpolate(s, [0, 1], [26, 0])}px)`,
  };
};

const Shell: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{
    position: 'absolute', left: 0, right: 0, top: '30%',
    display: 'flex', justifyContent: 'center', pointerEvents: 'none',
  }}>{children}</div>
);

/* ---------------- 1. CỬA SỔ DÒNG LỆNH ---------------- */
/** Dùng khi lời nói nhắc tới code, lệnh, terminal, CLI. */
const Terminal: React.FC<{ at: number; ff: string; text: string }> = ({ at, ff, text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const r = useRise(at);
  const chars = Math.floor(Math.max(0, (frame - at) / fps) * 13);
  return (
    <Shell>
      <div style={{
        width: 720, borderRadius: 18, overflow: 'hidden',
        background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.11)',
        ...r,
      }}>
        <div style={{
          height: 44, display: 'flex', alignItems: 'center', gap: 9, paddingLeft: 20,
          background: 'rgba(255,255,255,0.05)',
        }}>
          {[0, 1, 2].map((i) => (
            <span key={i} style={{
              width: 12, height: 12, borderRadius: '50%',
              background: 'rgba(255,255,255,0.22)',
            }} />
          ))}
        </div>
        <div style={{
          padding: '34px 30px 44px', fontFamily: 'monospace', fontSize: 34,
          color: pal.ink, letterSpacing: '0.01em',
        }}>
          <span style={{ color: pal.accent }}>$ </span>
          {text.slice(0, chars)}
          <span style={{
            display: 'inline-block', width: 16, height: 34, marginLeft: 3,
            background: pal.accent, verticalAlign: 'text-bottom',
            opacity: Math.floor(frame / 15) % 2 ? 0.25 : 1,
          }} />
        </div>
      </div>
    </Shell>
  );
};

/* ---------------- 2. VÒNG TỰ VẬN HÀNH ---------------- */
/**
 * Lõi ở giữa, các đường kẻ nối ra từng chấm, mỗi chấm có CHÚ THÍCH nói nó
 * làm gì. Một xung sáng chạy dọc đường kẻ để thấy vòng lặp đang tự quay.
 *
 * Trước đây chỗ này chỉ là cái hộp với mấy chấm trôi lơ lửng, không nối vào
 * đâu và không chú thích -- nhìn thì có hình nhưng không hiểu đang nói gì.
 * Chú thích lấy từ chính câu liệt kê trong lời nói ("tự sửa phần mềm, tự
 * viết báo cáo, tự giám sát production"), nên không phải bịa.
 */
const AutoLoop: React.FC<{ at: number; ff: string; label: string; nodes: string[] }> =
({ at, ff, label, nodes }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const r = useRise(at);
  const t = Math.max(0, (frame - at) / fps);

  const CX = 380, CY = 330, R = 210;
  const list = (nodes && nodes.length ? nodes : ['tự chạy', 'tự kiểm', 'tự sửa']).slice(0, 4);
  const pts = list.map((text, i) => {
    const a = (-90 + (360 / list.length) * i) * (Math.PI / 180);
    return { text, x: CX + Math.cos(a) * R, y: CY + Math.sin(a) * R, a };
  });

  return (
    <Shell>
      <div style={{ ...r }}>
        <svg width={760} height={660} viewBox="0 0 760 660">
          {pts.map((p, i) => {
            // đường kẻ nối lõi ra từng chấm
            const grow = interpolate(frame - at - i * 6, [0, 16], [0, 1],
              { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
            const ex = CX + (p.x - CX) * grow;
            const ey = CY + (p.y - CY) * grow;
            // xung sáng chạy dọc đường, lệch pha từng nhánh
            const k = ((t * 0.55 + i / list.length) % 1);
            const px = CX + (p.x - CX) * k;
            const py = CY + (p.y - CY) * k;
            return (
              <g key={i}>
                <line x1={CX} y1={CY} x2={ex} y2={ey}
                      stroke={pal.accent} strokeWidth={3} opacity={0.42} />
                {grow > 0.98 ? (
                  <circle cx={px} cy={py} r={7} fill={pal.accent} opacity={0.95} />
                ) : null}
                <circle cx={ex} cy={ey} r={17} fill="#0C0C0C"
                        stroke={pal.accent} strokeWidth={3} opacity={grow} />
              </g>
            );
          })}
          {/* lõi */}
          <circle cx={CX} cy={CY} r={62} fill={pal.accent} />
          <circle cx={CX} cy={CY} r={62 + 16 * (0.5 + 0.5 * Math.sin(t * 2.2))}
                  fill="none" stroke={pal.accent} strokeWidth={2} opacity={0.35} />
          <text x={CX} y={CY + 9} textAnchor="middle"
                style={{ fontFamily: ff, fontWeight: 800, fontSize: 25, fill: '#fff' }}>
            {label.slice(0, 8)}
          </text>

          {/* chú thích cho từng chấm */}
          {pts.map((p, i) => {
            const show = interpolate(frame - at - 14 - i * 6, [0, 12], [0, 1],
              { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
            const right = Math.cos(p.a) > 0.1;
            const below = Math.sin(p.a) > 0.5;
            const anchor = Math.abs(Math.cos(p.a)) < 0.2 ? 'middle' : (right ? 'start' : 'end');
            const dx = anchor === 'middle' ? 0 : (right ? 30 : -30);
            const dy = below ? 44 : (Math.sin(p.a) < -0.5 ? -32 : 8);
            return (
              <text key={i} x={p.x + dx} y={p.y + dy} textAnchor={anchor} opacity={show}
                    style={{ fontFamily: ff, fontWeight: 700, fontSize: 27, fill: '#FFFFFF' }}>
                {p.text}
              </text>
            );
          })}
        </svg>
      </div>
    </Shell>
  );
};

/* ---------------- 3. TƯỜNG CHẶN ---------------- */
/** Khi nói về giới hạn, chặn, rào cản, không cho phép. */
const Barrier: React.FC<{ at: number; ff: string; label: string }> = ({ at, ff, label }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const r = useRise(at);
  // mũi tên lao tới rồi bật ngược lại khi chạm tường
  const t = Math.max(0, (frame - at) / fps);
  const cyc = (t % 2.2) / 2.2;
  const x = cyc < 0.55 ? interpolate(cyc, [0, 0.55], [0, 230])
                       : interpolate(cyc, [0.55, 1], [230, 150]);
  const hit = cyc >= 0.5 && cyc < 0.75;
  return (
    <Shell>
      <div style={{ width: 700, height: 300, position: 'relative', ...r }}>
        <div style={{
          position: 'absolute', top: '50%', left: 40, width: 26, height: 26,
          marginTop: -13, borderRadius: '50%', background: pal.ink,
          transform: `translateX(${x}px)`,
        }} />
        {/* bức tường */}
        <div style={{
          position: 'absolute', top: 20, bottom: 20, left: 330, width: 16,
          borderRadius: 8, background: pal.accent,
          boxShadow: hit ? `0 0 60px 16px ${pal.accent}66` : 'none',
        }} />
        <span style={{
          position: 'absolute', top: '50%', left: 392, marginTop: -30,
          fontSize: 60, color: pal.accent, fontWeight: 900, lineHeight: 1,
          opacity: hit ? 1 : 0.35,
        }}>×</span>
        {label ? (
          <span style={{
            position: 'absolute', bottom: -14, left: 0, right: 0, textAlign: 'center',
            fontFamily: ff, fontWeight: '700', fontSize: 25, color: pal.ink, opacity: 0.55,
            letterSpacing: '0.1em', textTransform: 'uppercase',
          }}>{label}</span>
        ) : null}
      </div>
    </Shell>
  );
};

/* ---------------- 4. THẺ GIÁ ---------------- */
/** Khi nói về tiền, chi phí, giá, gói cước. */
const PriceTag: React.FC<{ at: number; ff: string; label: string }> = ({ at, ff, label }) => {
  const pal = usePal();
  const r = useRise(at);
  return (
    <Shell>
      <div style={{
        position: 'relative', padding: '46px 76px', borderRadius: 26,
        background: 'rgba(255,255,255,0.05)', border: `2px solid ${pal.accent}55`,
        display: 'flex', alignItems: 'center', gap: 26, ...r,
      }}>
        <span style={{ fontSize: 76, lineHeight: 1 }}>💰</span>
        <span style={{
          fontFamily: ff, fontWeight: '800', fontSize: 46, color: pal.ink,
          letterSpacing: '-0.01em', maxWidth: 420,
        }}>{label}</span>
      </div>
    </Shell>
  );
};

/* ---------------- 5. DANH SÁCH TÍCH ---------------- */
/** Khi nói về kiểm thử, kiểm tra, quy trình, các bước. */
const CheckList: React.FC<{ at: number; ff: string; items: string[] }> = ({ at, ff, items }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  return (
    <Shell>
      <div style={{ width: 640, display: 'flex', flexDirection: 'column', gap: 20 }}>
        {items.map((it, i) => {
          const s = spring({ frame: frame - at - i * 9, fps,
                             config: { damping: 20, stiffness: 160, mass: 0.8 } });
          const done = frame - at - i * 9 > 12;
          return (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 22,
              padding: '24px 30px', borderRadius: 18,
              background: 'rgba(255,255,255,0.045)',
              border: '1px solid rgba(255,255,255,0.09)',
              opacity: interpolate(s, [0, 1], [0, 1]),
              transform: `translateX(${interpolate(s, [0, 1], [-22, 0])}px)`,
            }}>
              <span style={{
                width: 40, height: 40, borderRadius: 11, flex: '0 0 40px',
                border: `2px solid ${done ? pal.accent : 'rgba(255,255,255,0.22)'}`,
                background: done ? pal.accent : 'transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontSize: 25, fontWeight: 900,
              }}>{done ? '✓' : ''}</span>
              <span style={{
                fontFamily: ff, fontWeight: '700', fontSize: 32, color: pal.ink,
                opacity: done ? 1 : 0.6,
              }}>{it}</span>
            </div>
          );
        })}
      </div>
    </Shell>
  );
};

/* ---------------- 6. CẢNH BÁO ---------------- */
/** Khi nói về rủi ro, nguy hiểm, sự cố, mất mát. */
const Warning: React.FC<{ at: number; ff: string; label: string }> = ({ at, ff, label }) => {
  const frame = useCurrentFrame();
  const pal = usePal();
  const r = useRise(at);
  const pulse = 0.55 + 0.45 * Math.sin((frame - at) / 11);
  return (
    <Shell>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 28, ...r }}>
        <svg width={230} height={205} viewBox="0 0 230 205">
          <path d="M115 12 L222 196 L8 196 Z" fill="none"
                stroke={pal.accent} strokeWidth={11} strokeLinejoin="round"
                opacity={pulse} />
          <rect x={105} y={78} width={20} height={62} rx={10} fill={pal.accent} />
          <circle cx={115} cy={166} r={12} fill={pal.accent} />
        </svg>
        {label ? (
          <span style={{
            fontFamily: ff, fontWeight: '800', fontSize: 34, color: pal.ink,
            letterSpacing: '0.04em', textTransform: 'uppercase', opacity: 0.75,
          }}>{label}</span>
        ) : null}
      </div>
    </Shell>
  );
};

/* ---------------- 7. MŨI TÊN TĂNG VỌT ---------------- */
/** Khi nói về tăng trưởng, bứt phá, vượt lên. */
const Surge: React.FC<{ at: number; ff: string; up: boolean }> = ({ at, ff, up }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const r = useRise(at);
  const draw = interpolate(frame - at, [0, 26], [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const pts = up ? '20,250 130,205 240,150 350,55' : '20,55 130,110 240,180 350,250';
  return (
    <Shell>
      <div style={{ ...r }}>
        <svg width={420} height={300} viewBox="0 0 380 290">
          {[0, 1, 2, 3].map((i) => (
            <line key={i} x1={10} y1={40 + i * 70} x2={370} y2={40 + i * 70}
                  stroke="rgba(255,255,255,0.07)" strokeWidth={2} />
          ))}
          <polyline points={pts} fill="none" stroke={pal.accent} strokeWidth={12}
                    strokeLinecap="round" strokeLinejoin="round"
                    strokeDasharray={520} strokeDashoffset={520 * (1 - draw)} />
          <circle cx={up ? 350 : 350} cy={up ? 55 : 250} r={15} fill={pal.accent}
                  opacity={draw > 0.95 ? 1 : 0} />
        </svg>
      </div>
    </Shell>
  );
};

/* ---------------- 8. NGƯỜI vs MÁY ---------------- */
/** Khi nói về con người so với AI / tự động thay thế thủ công. */
const HumanVsBot: React.FC<{ at: number; ff: string; leftLabel: string; rightLabel: string }> =
({ at, ff, leftLabel, rightLabel }) => {
  const pal = usePal();
  const a = useRise(at);
  const b = useRise(at, 8);
  const Tile = (emoji: string, label: string, st: React.CSSProperties, hot: boolean) => (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18, ...st,
    }}>
      <div style={{
        width: 190, height: 190, borderRadius: 30,
        background: hot ? `${pal.accent}1F` : 'rgba(255,255,255,0.045)',
        border: `2px solid ${hot ? pal.accent : 'rgba(255,255,255,0.12)'}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 92,
      }}>{emoji}</div>
      <span style={{
        fontFamily: ff, fontWeight: '800', fontSize: 28,
        color: hot ? pal.accent : pal.ink, opacity: hot ? 1 : 0.6,
        letterSpacing: '0.04em', textTransform: 'uppercase',
      }}>{label}</span>
    </div>
  );
  return (
    <Shell>
      <div style={{ display: 'flex', alignItems: 'center', gap: 46 }}>
        {Tile('🧑‍💻', leftLabel, a, false)}
        <span style={{
          fontFamily: ff, fontWeight: '900', fontSize: 44, color: pal.ink, opacity: 0.35,
          marginBottom: 46,
        }}>VS</span>
        {Tile('🤖', rightLabel, b, true)}
      </div>
    </Shell>
  );
};

/* ---------------- CHỌN HÌNH THEO LỜI NÓI ---------------- */

type Pick = { kind: string; label?: string; items?: string[]; up?: boolean; text?: string;
              nodes?: string[] };

/** Nhóm từ khoá -> hình. Thứ tự quan trọng: khớp cái cụ thể trước. */
const RULES: { kind: string; words: string[] }[] = [
  { kind: 'terminal', words: ['dong lenh', 'terminal', 'cli', 'cau lenh', 'go code', 'viet code', 'dong code'] },
  { kind: 'barrier',  words: ['chan', 'gioi han', 'han che', 'rao can', 'khong cho', 'cam', 'siet', 'tuong'] },
  { kind: 'price',    words: ['gia', 'chi phi', 'do la', 'usd', 'tien', 'dat do', 're hon', 'goi cuoc', 'tra phi'] },
  { kind: 'checks',   words: ['kiem thu', 'kiem tra', 'test', 'quy trinh', 'tung buoc', 'giam sat'] },
  { kind: 'warning',  words: ['rui ro', 'nguy hiem', 'su co', 'canh bao', 'that bai', 'sai lam', 'mat'] },
  { kind: 'human',    words: ['thu cong', 'con nguoi', 'nghiep du', 'thay the', 'tu dong thay'] },
  { kind: 'surgeUp',  words: ['tang', 'bung no', 'vot len', 'but pha', 'nhanh hon', 'vuot'] },
  { kind: 'surgeDn',  words: ['giam', 'tut', 'cham hon', 'roi xuong', 'sut'] },
  { kind: 'sandbox',  words: ['tu van hanh', 'tu dong', 'tu sua', 'tu viet', 'he thong', 'production', 'moi truong', 'tu chay'] },
];

/**
 * Chọn hình cho một thẻ dựa trên chính câu đang được nói. Trả về null khi
 * không từ khoá nào khớp -- thà để trống còn hơn dán một hình sai nội dung.
 */
export const pickElement = (text: string): Pick | null => {
  const t = ' ' + bare(text) + ' ';
  for (const r of RULES) {
    for (const w of r.words) {
      if (t.includes(' ' + w) || t.includes(w + ' ')) {
        if (r.kind === 'surgeUp') return { kind: 'surge', up: true };
        if (r.kind === 'surgeDn') return { kind: 'surge', up: false };
        return { kind: r.kind };
      }
    }
  }
  return null;
};

export const ElementView: React.FC<{ pick: Pick; at: number; ff: string }> = ({ pick, at, ff }) => {
  switch (pick.kind) {
    case 'terminal': return <Terminal at={at} ff={ff} text={pick.text ?? 'run agent.py'} />;
    case 'barrier':  return <Barrier at={at} ff={ff} label={pick.label ?? 'giới hạn'} />;
    case 'price':    return <PriceTag at={at} ff={ff} label={pick.label ?? 'chi phí'} />;
    case 'checks':   return <CheckList at={at} ff={ff}
                              items={pick.items ?? ['tự viết kiểm thử', 'tự chạy', 'tự giám sát']} />;
    case 'warning':  return <Warning at={at} ff={ff} label={pick.label ?? 'rủi ro'} />;
    case 'human':    return <HumanVsBot at={at} ff={ff}
                              leftLabel={pick.label ?? 'thủ công'} rightLabel="tự động" />;
    case 'surge':    return <Surge at={at} ff={ff} up={pick.up ?? true} />;
    case 'sandbox':  return <AutoLoop at={at} ff={ff} label={pick.label ?? 'ASTRA'}
                                      nodes={pick.nodes ?? []} />;
    default:         return null;
  }
};
