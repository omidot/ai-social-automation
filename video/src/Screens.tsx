import React from 'react';
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { fitText } from '@remotion/layout-utils';

/**
 * BỘ MÀN HÌNH dựng theo đúng video mẫu người dùng gửi (kênh ainius.net).
 *
 * Điểm mấu chốt mà bản trước làm sai: ở video mẫu, MỖI ĐOẠN là một màn
 * hình hoàn chỉnh chiếm khung -- không phải nền đen với chữ chạy ngang rồi
 * thỉnh thoảng mới chèn một biểu đồ. Chữ thoại chỉ là dòng nhỏ dưới đáy,
 * còn phần giữa khung LUÔN có một màn hình thuộc một trong các dạng dưới
 * đây. Vì vậy mỗi card bắt buộc phải mang một `screen`, không card nào
 * được để trống.
 *
 * Các dạng rút ra từ việc soi từng khung hình của bản mẫu:
 *   hook      -- mào đầu: nhãn nhỏ + tiêu đề lớn + phụ đề + các ô so kè
 *   panel     -- nhãn ngắn + các hộp số liệu / thanh so sánh / danh sách
 *   shot      -- ảnh chụp màn hình thật, tràn viền
 *   statement -- ảnh nền mờ + nhãn nhỏ + câu chốt có cụm bọc nền đỏ + đoạn nhỏ
 *
 * Màu lấy bằng cách đo pixel trên chính bản mẫu: nhấn #E03C3C (đỏ thẫm,
 * không phải cam), nền #080808.
 */

export const REF = {
  bg: '#080808',
  ink: '#FFFFFF',
  dim: 'rgba(255,255,255,0.42)',
  faint: 'rgba(255,255,255,0.22)',
  accent: '#E03C3C',
  box: 'rgba(255,255,255,0.045)',
  boxLine: 'rgba(255,255,255,0.09)',
  PAD: 96,
};

const W = 1080 - REF.PAD * 2;

const useIn = (at: number, delay = 0, fps = 30) => {
  const frame = useCurrentFrame();
  const s = spring({ frame: frame - at - delay, fps,
                     config: { damping: 21, stiffness: 155, mass: 0.8 } });
  return { o: interpolate(s, [0, 1], [0, 1]), y: interpolate(s, [0, 1], [24, 0]) };
};

/** Nhãn nhỏ viết hoa, giãn chữ -- bản mẫu dùng ở đầu mọi màn hình lớn. */
const Eyebrow: React.FC<{ text: string; ff: string; at: number; accentTail?: boolean }> =
({ text, ff, at, accentTail }) => {
  const { fps } = useVideoConfig();
  const a = useIn(at, 0, fps);
  if (!text) return null;
  const words = text.split(' ');
  const cut = accentTail ? Math.max(1, words.length - 2) : words.length;
  return (
    <div style={{
      textAlign: 'center', marginBottom: 22,
      fontFamily: ff, fontWeight: '700', fontSize: 27, letterSpacing: '0.2em',
      textTransform: 'uppercase',
      opacity: a.o, transform: `translateY(${a.y}px)`,
    }}>
      <span style={{ color: REF.dim }}>{words.slice(0, cut).join(' ')}</span>
      {cut < words.length ? (
        <span style={{ color: REF.accent }}> {words.slice(cut).join(' ')}</span>
      ) : null}
    </div>
  );
};

/* ================= 1. HOOK ================= */

export type Tile = { label: string; note?: string; file?: string; verdict?: 'win' | 'lose' };

/**
 * Màn mào đầu: nhãn nhỏ, tiêu đề TO, dòng phụ, rồi hàng ô so kè bên dưới.
 * Bản mẫu gạch chéo đỏ lên các ô thua và đội vương miện cho ô thắng.
 */
export const HookScreen: React.FC<{
  eyebrow: string; title: string; subtitle?: string; foot?: string;
  tiles?: Tile[]; ff: string; at: number;
}> = ({ eyebrow, title, subtitle, foot, tiles = [], ff, at }) => {
  const { fps } = useVideoConfig();
  const t1 = useIn(at, 5, fps);
  const t2 = useIn(at, 11, fps);
  const titleSize = Math.min(118, fitText({
    text: title.toUpperCase(), withinWidth: W, fontFamily: ff,
    fontWeight: '900', letterSpacing: '0.01em',
  }).fontSize);
  const subSize = subtitle ? Math.min(62, fitText({
    text: subtitle.toUpperCase(), withinWidth: W, fontFamily: ff,
    fontWeight: '800', letterSpacing: '0.01em',
  }).fontSize) : 0;

  return (
    <AbsoluteFill style={{
      alignItems: 'center', justifyContent: 'center',
      paddingLeft: REF.PAD, paddingRight: REF.PAD, paddingBottom: 430,
    }}>
      <Eyebrow text={eyebrow} ff={ff} at={at} />
      <div style={{
        fontFamily: ff, fontWeight: '900', fontSize: titleSize, lineHeight: 1.18,
        paddingBottom: '0.12em',
        color: REF.ink, textTransform: 'uppercase', letterSpacing: '0.01em',
        textAlign: 'center', whiteSpace: 'pre',
        opacity: t1.o, transform: `translateY(${t1.y}px)`,
      }}>{title.toUpperCase()}</div>
      {subtitle ? (
        <div style={{
          fontFamily: ff, fontWeight: '800', fontSize: subSize, lineHeight: 1.22,
          paddingBottom: '0.1em',
          color: REF.ink, textTransform: 'uppercase', letterSpacing: '0.01em',
          textAlign: 'center', marginTop: 12,
          opacity: t2.o, transform: `translateY(${t2.y}px)`,
        }}>{subtitle.toUpperCase()}</div>
      ) : null}
      {foot ? (
        <div style={{
          fontFamily: ff, fontWeight: '700', fontSize: 28, letterSpacing: '0.16em',
          color: REF.faint, textTransform: 'uppercase', marginTop: 18,
          opacity: t2.o,
        }}>{foot.toUpperCase()}</div>
      ) : null}

      {tiles.length ? (
        <div style={{ display: 'flex', gap: 30, marginTop: 26, alignItems: 'flex-start' }}>
          {tiles.slice(0, 3).map((tl, i) => (
            <TileView key={i} tile={tl} ff={ff} at={at + 16 + i * 6} />
          ))}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

const TileView: React.FC<{ tile: Tile; ff: string; at: number }> = ({ tile, ff, at }) => {
  const { fps } = useVideoConfig();
  const a = useIn(at, 0, fps);
  const win = tile.verdict === 'win';
  const lose = tile.verdict === 'lose';
  return (
    <div style={{
      width: 176, display: 'flex', flexDirection: 'column', alignItems: 'center',
      opacity: a.o, transform: `translateY(${a.y}px)`,
    }}>
      <div style={{
        position: 'relative', width: 152, height: 128, borderRadius: 18,
        background: win ? REF.accent : 'rgba(255,255,255,0.05)',
        border: `1px solid ${win ? REF.accent : REF.boxLine}`,
        boxShadow: win ? `0 16px 54px ${REF.accent}55` : 'none',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {tile.file ? (
          <Img src={staticFile(tile.file)}
               style={{ width: '58%', height: '58%', objectFit: 'contain',
                        filter: lose ? 'grayscale(1)' : 'none', opacity: lose ? 0.5 : 1 }} />
        ) : null}
        {lose ? (
          <svg width={152} height={128} style={{ position: 'absolute', inset: 0 }}>
            <line x1={26} y1={22} x2={126} y2={106} stroke={REF.accent} strokeWidth={9} strokeLinecap="round" />
            <line x1={126} y1={22} x2={26} y2={106} stroke={REF.accent} strokeWidth={9} strokeLinecap="round" />
          </svg>
        ) : null}
        {win ? (
          <span style={{ position: 'absolute', top: -44, fontSize: 50, lineHeight: 1 }}>👑</span>
        ) : null}
      </div>
      <span style={{
        marginTop: 14, fontFamily: ff, fontWeight: '800', fontSize: 25, lineHeight: 1.18,
        color: REF.ink, textAlign: 'center', textTransform: 'uppercase',
      }}>{tile.label}</span>
      {tile.note ? (
        <span style={{
          marginTop: 5, fontFamily: ff, fontWeight: '600', fontSize: 20,
          color: win ? REF.accent : REF.faint, textAlign: 'center',
        }}>{tile.note}</span>
      ) : null}
    </div>
  );
};

/* ================= 2. STATEMENT ================= */

/**
 * Câu chốt trên ảnh nền mờ: nhãn nhỏ, câu lớn, và MỘT cụm được bọc nền đỏ
 * -- đúng thủ pháp bản mẫu dùng để nhấn ý chính ("rẻ nhất mỗi token").
 */
export const StatementScreen: React.FC<{
  eyebrow?: string; lead: string; highlight: string; body?: string;
  bgFile?: string; ff: string; at: number;
}> = ({ eyebrow, lead, highlight, body, bgFile, ff, at }) => {
  const { fps } = useVideoConfig();
  const a = useIn(at, 6, fps);
  const b = useIn(at, 13, fps);
  const c = useIn(at, 20, fps);
  const size = Math.min(72, fitText({
    text: lead.length > highlight.length ? lead : highlight,
    withinWidth: W - 40, fontFamily: ff, fontWeight: '800', letterSpacing: '-0.01em',
  }).fontSize);
  return (
    <AbsoluteFill>
      {bgFile ? (
        <>
          <Img src={staticFile(bgFile)}
               style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          <AbsoluteFill style={{ background: 'rgba(6,6,6,0.82)' }} />
        </>
      ) : null}
      <AbsoluteFill style={{
        alignItems: 'center', justifyContent: 'center',
        paddingLeft: REF.PAD, paddingRight: REF.PAD, paddingBottom: 380,
      }}>
        {eyebrow ? <Eyebrow text={eyebrow} ff={ff} at={at} accentTail /> : null}
        <div style={{
          fontFamily: ff, fontWeight: '800', fontSize: size, lineHeight: 1.22,
          color: REF.ink, textAlign: 'center', letterSpacing: '-0.01em',
          opacity: a.o, transform: `translateY(${a.y}px)`,
        }}>{lead}</div>
        <div style={{
          marginTop: 12, padding: '8px 22px 12px', borderRadius: 10,
          background: REF.accent,
          opacity: b.o, transform: `translateY(${b.y}px)`,
        }}>
          <span style={{
            fontFamily: ff, fontWeight: '800', fontSize: size, lineHeight: 1.22,
            color: REF.ink, letterSpacing: '-0.01em',
          }}>{highlight}</span>
        </div>
        {body ? (
          <div style={{
            marginTop: 30, maxWidth: W - 60,
            fontFamily: ff, fontWeight: '600', fontSize: 34, lineHeight: 1.5,
            color: REF.dim, textAlign: 'center',
            opacity: c.o, transform: `translateY(${c.y}px)`,
          }}>{body}</div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/* ================= 3. SHOT ================= */

/** Ảnh chụp thật, tràn viền, làm tối hai mép cho chữ đọc được. */
export const ShotScreen: React.FC<{
  file: string; at: number; title?: string; sourceUrl?: string; ff?: string;
}> = ({ file, at, title, sourceUrl, ff }) => {
  const { fps } = useVideoConfig();
  const frame = useCurrentFrame();
  const a = useIn(at, 0, fps);
  const t = useIn(at, 8, fps);
  // Trôi rất chậm để hình không chết cứng, nhưng KHÔNG phóng to lấp khung:
  // ảnh trang web là khổ ngang, ép vào khung dọc kiểu "cover" thì cắt mất
  // hai bên -- đo thật: tiêu đề "Cognition helps Devin test..." bị xén còn
  // "tion helps Devin t". Bản mẫu luôn để ảnh vừa CHIỀU NGANG, chừa đen
  // trên dưới, nhờ vậy đọc được nguyên tiêu đề bài báo.
  const drift = Math.max(0, (frame - at) / fps) * 5;

  // Tên miền nguồn, để người xem biết ảnh này lấy từ đâu -- vừa đúng kiểu
  // bản mẫu (luôn có một dòng nhỏ ghi nguồn), vừa là ghi công tử tế.
  let host = '';
  try { host = sourceUrl ? new URL(sourceUrl).hostname.replace(/^www\./, '') : ''; } catch { host = ''; }

  return (
    <AbsoluteFill style={{
      opacity: a.o, alignItems: 'center', justifyContent: 'center',
    }}>
      {/* Ảnh thu nhỏ lại, chừa lề hai bên -- đỡ nặng khung, và có chỗ cho
          tiêu đề phía trên thở. */}
      <Img src={staticFile(file)} style={{
        width: '82%', height: 'auto', display: 'block', borderRadius: 14,
        transform: `translateY(${-drift}px)`,
        boxShadow: '0 30px 90px rgba(0,0,0,0.75)',
      }} />
      <AbsoluteFill style={{
        // Trang web thường nền TRẮNG -> caption trắng ở đáy biến mất. Phủ
        // tối hẳn từ 58% trở xuống, đúng vùng caption ngồi (70%).
        background: 'linear-gradient(to bottom, rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.0) 22%,'
          + ' rgba(0,0,0,0.0) 50%, rgba(0,0,0,0.88) 62%, rgba(0,0,0,0.97) 72%,'
          + ' rgba(0,0,0,0.99) 100%)',
      }} />
      {title ? (
        <div style={{
          position: 'absolute', top: 210, left: REF.PAD, right: REF.PAD,
          textAlign: 'center',
          opacity: t.o, transform: `translateY(${t.y}px)`,
        }}>
          <div style={{
            fontFamily: ff, fontWeight: '800', fontSize: 46, lineHeight: 1.24,
            color: REF.ink, letterSpacing: '-0.01em',
            textShadow: '0 4px 26px rgba(0,0,0,0.9)',
          }}>{title}</div>
          {host ? (
            <div style={{
              marginTop: 14, display: 'inline-block',
              padding: '8px 18px', borderRadius: 999,
              background: 'rgba(0,0,0,0.55)', border: `1px solid ${REF.accent}66`,
              fontFamily: ff, fontWeight: '700', fontSize: 23, letterSpacing: '0.14em',
              color: REF.accent, textTransform: 'uppercase',
            }}>nguồn · {host}</div>
          ) : null}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/* ================= 4. CARDS — bộ thẻ nhỏ ================= */

/**
 * Nhãn ngắn + 2-4 hộp bo góc, mỗi hộp một mục. Dạng này chiếm phần lớn bản
 * mẫu ("Có gì cho bạn", "Năng lực nổi bật"). Mục lấy nguyên văn từ câu liệt
 * kê trong lời nói, có đánh số như bản mẫu.
 */
export const CardsScreen: React.FC<{
  title: string; items: { label: string; note?: string }[]; ff: string; at: number;
}> = ({ title, items, ff, at }) => {
  const { fps } = useVideoConfig();
  const t = useIn(at, 0, fps);
  return (
    <AbsoluteFill style={{
      alignItems: 'center', justifyContent: 'center',
      paddingLeft: REF.PAD, paddingRight: REF.PAD, paddingBottom: 430,
    }}>
      <div style={{ width: W }}>
        {title ? (
          <div style={{
            textAlign: 'center', marginBottom: 30,
            fontFamily: ff, fontWeight: '800', fontSize: 46, color: REF.ink,
            opacity: t.o, transform: `translateY(${t.y}px)`,
          }}>{title}</div>
        ) : null}
        {items.slice(0, 4).map((it, i) => (
          <CardRow key={i} n={i + 1} item={it} ff={ff} at={at + 7 + i * 8} />
        ))}
      </div>
    </AbsoluteFill>
  );
};

const CardRow: React.FC<{
  n: number; item: { label: string; note?: string }; ff: string; at: number;
}> = ({ n, item, ff, at }) => {
  const { fps } = useVideoConfig();
  const a = useIn(at, 0, fps);
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 22,
      padding: '26px 30px', marginBottom: 18, borderRadius: 20,
      background: REF.box, border: `1px solid ${REF.boxLine}`,
      opacity: a.o, transform: `translateY(${a.y}px)`,
    }}>
      <span style={{
        width: 50, height: 50, flex: '0 0 50px', borderRadius: 13,
        background: 'rgba(255,255,255,0.07)', border: `1px solid ${REF.boxLine}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: ff, fontWeight: '800', fontSize: 26, color: REF.ink, opacity: 0.8,
      }}>{n}</span>
      <span style={{ flex: 1 }}>
        <span style={{
          display: 'block', fontFamily: ff, fontWeight: '800', fontSize: 34,
          color: REF.ink, lineHeight: 1.25,
        }}>{item.label}</span>
        {item.note ? (
          <span style={{
            display: 'block', marginTop: 5, fontFamily: ff, fontWeight: '500',
            fontSize: 25, color: REF.dim,
          }}>{item.note}</span>
        ) : null}
      </span>
    </div>
  );
};

/* ================= 5. PERSON — nhân vật phát biểu ================= */

/**
 * Nhân vật đã tách nền (viền trắng nướng sẵn trong file PNG) trượt vào theo
 * đường CHÉO TỪ GÓC PHẢI DƯỚI, kèm khối trích dẫn bên trái như thể người đó
 * đang nói. Dòng ghi nguồn ảnh nằm dưới cùng.
 *
 * Ảnh là ảnh người thật, lấy từ nguồn có giấy phép rõ ràng (Wikimedia) và
 * luôn kèm ghi công -- không đi vơ ảnh ở nguồn không rõ bản quyền.
 */
export const PersonScreen: React.FC<{
  file: string; name: string; role?: string; quote: string; credit?: string;
  ff: string; at: number;
}> = ({ file, name, role, quote, credit, ff, at }) => {
  const { fps } = useVideoConfig();
  const frame = useCurrentFrame();
  const p = spring({ frame: frame - at, fps,
                     config: { damping: 24, stiffness: 120, mass: 1.1 } });
  const q = useIn(at, 14, fps);
  const c = useIn(at, 22, fps);

  // vào chéo: từ ngoài mép phải dưới tiến về chỗ đứng
  const dx = interpolate(p, [0, 1], [520, 0]);
  const dy = interpolate(p, [0, 1], [420, 0]);

  return (
    <AbsoluteFill>
      <div style={{
        position: 'absolute', right: -40, bottom: 210,
        transform: `translate(${dx}px, ${dy}px)`,
        opacity: interpolate(p, [0, 0.25], [0, 1], { extrapolateRight: 'clamp' }),
        filter: 'drop-shadow(0 26px 60px rgba(0,0,0,0.75))',
      }}>
        <Img src={staticFile(file)} style={{ height: 980, width: 'auto', display: 'block' }} />
      </div>

      {/* khối trích dẫn: dấu nháy lớn + câu nói + tên và chức danh */}
      <div style={{
        position: 'absolute', left: REF.PAD, top: 300, width: 560,
        opacity: q.o, transform: `translateY(${q.y}px)`,
      }}>
        <div style={{
          fontFamily: ff, fontWeight: '900', fontSize: 92, color: REF.accent,
          lineHeight: 0.7, marginBottom: 10,
        }}>&ldquo;</div>
        <div style={{
          fontFamily: ff, fontWeight: '800', fontSize: 44, lineHeight: 1.3,
          color: REF.ink, letterSpacing: '-0.01em',
          textShadow: '0 4px 26px rgba(0,0,0,0.9)',
        }}>{quote}</div>
        <div style={{
          marginTop: 22, paddingTop: 18, borderTop: `2px solid ${REF.accent}`,
          display: 'inline-block',
        }}>
          <div style={{
            fontFamily: ff, fontWeight: '800', fontSize: 34, color: REF.ink,
          }}>{name}</div>
          {role ? (
            <div style={{
              marginTop: 4, fontFamily: ff, fontWeight: '600', fontSize: 25,
              color: REF.dim,
            }}>{role}</div>
          ) : null}
        </div>
      </div>

      {credit ? (
        <div style={{
          position: 'absolute', left: REF.PAD, bottom: 56,
          fontFamily: ff, fontWeight: '600', fontSize: 20, letterSpacing: '0.1em',
          color: REF.faint, textTransform: 'uppercase',
          opacity: c.o,
        }}>ảnh: {credit}</div>
      ) : null}
    </AbsoluteFill>
  );
};

/* ================= 6. BRAND — logo hãng giữa khung ================= */

/**
 * Nói tới hãng nào thì hiện LOGO HÃNG ĐÓ GIỮA KHUNG, to và có tên.
 *
 * Trước đây logo chỉ là một ô nhỏ nép góc phải trên, gần như không ai thấy.
 * Người dùng chỉ rõ: nhắc "GPT-6 Astra" hay "Claude Fable 5" thì phải hiện
 * đúng logo hai bên ở GIỮA kèm chú thích, không phải một chấm bé ở góc.
 *
 * Một hãng -> một ô. Hai hãng nhắc sát nhau -> hai ô đối nhau, có dấu "&"
 * ở giữa.
 */
export const BrandScreen: React.FC<{
  tiles: { label: string; file?: string }[]; eyebrow?: string;
  ff: string; at: number;
}> = ({ tiles, eyebrow, ff, at }) => {
  const { fps } = useVideoConfig();
  const pair = tiles.length >= 2;
  const mid = useIn(at, 10, fps);
  return (
    <AbsoluteFill style={{
      alignItems: 'center', justifyContent: 'center', paddingBottom: 420,
    }}>
      {eyebrow ? <Eyebrow text={eyebrow} ff={ff} at={at} /> : null}
      <div style={{ display: 'flex', alignItems: 'center', gap: pair ? 54 : 0 }}>
        {tiles.slice(0, 2).map((t, i) => (
          <BrandTile key={i} tile={t} ff={ff} at={at + i * 7} big={!pair} />
        ))}
        {pair ? (
          <span style={{
            position: 'absolute', left: 0, right: 0, textAlign: 'center',
            fontFamily: ff, fontWeight: '900', fontSize: 54, color: REF.accent,
            marginBottom: 78, pointerEvents: 'none',
            opacity: mid.o, transform: `scale(${0.6 + mid.o * 0.4})`,
          }}>&amp;</span>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

const BrandTile: React.FC<{
  tile: { label: string; file?: string }; ff: string; at: number; big: boolean;
}> = ({ tile, ff, at, big }) => {
  const { fps } = useVideoConfig();
  const a = useIn(at, 0, fps);
  const size = big ? 300 : 230;
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24,
      opacity: a.o, transform: `translateY(${a.y}px) scale(${0.82 + a.o * 0.18})`,
    }}>
      <div style={{
        width: size, height: size, borderRadius: 42,
        background: '#FFFFFF', border: `2px solid ${REF.boxLine}`,
        boxShadow: '0 28px 70px rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {tile.file ? (
          <Img src={staticFile(tile.file)}
               style={{ width: '62%', height: '62%', objectFit: 'contain' }} />
        ) : null}
      </div>
      <span style={{
        fontFamily: ff, fontWeight: '800', fontSize: big ? 44 : 36,
        color: REF.ink, letterSpacing: '0.02em', textAlign: 'center',
      }}>{tile.label}</span>
    </div>
  );
};
