import React from 'react';
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { fitText } from '@remotion/layout-utils';

/**
 * MÀN NHÂN VẬT KIỂU BÁO GIẤY (theo đúng ba ảnh mẫu người dùng gửi).
 *
 * Khác hẳn tông tối của phần còn lại: nền giấy sáng có vân nhăn và lưới
 * chấm, tiêu đề chữ serif đen, vài cụm được bôi BÚT DẠ VÀNG, dòng ghi tên
 * tờ báo kèm gạch ngang, và ảnh nhân vật ĐEN TRẮNG cắt rời có viền màu
 * chạy quanh, đặt lệch góc phải dưới, kèm nét vẽ tay đỏ.
 *
 * Viền quanh người được dựng bằng drop-shadow chồng nhiều lớp thay vì nướng
 * sẵn vào file PNG -- nhờ vậy đổi màu viền (đỏ/vàng) mà không phải tạo lại
 * ảnh, và cùng một file ảnh dùng được cho cả tông tối lẫn tông giấy.
 */

export const PAPER = {
  bg: '#EFEDE6',
  ink: '#121212',
  rule: '#1A1A1A',
  red: '#C8322B',
  marker: '#F5E14B',
  muted: '#4A4845',
};

/** Nền giấy: màu kem, lưới chấm mờ, vệt nhăn nhẹ. */
export const PaperBg: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: PAPER.bg }}>
    <AbsoluteFill style={{
      backgroundImage: 'radial-gradient(rgba(0,0,0,0.16) 1.4px, transparent 1.4px)',
      backgroundSize: '46px 46px', opacity: 0.55,
    }} />
    <AbsoluteFill style={{
      background:
        'radial-gradient(80% 50% at 18% 8%, rgba(0,0,0,0.05), transparent 60%),'
        + 'radial-gradient(70% 45% at 88% 70%, rgba(0,0,0,0.06), transparent 62%)',
    }} />
  </AbsoluteFill>
);

/** Cụm chữ được bôi bút dạ -- vệt màu nằm dưới chữ, hai đầu hơi lệch. */
const Mark: React.FC<{ children: React.ReactNode; on: boolean; grow: number }> =
({ children, on, grow }) => (
  <span style={{ position: 'relative', display: 'inline' }}>
    {on ? (
      <span style={{
        position: 'absolute', left: -8, right: -8, top: '14%', bottom: '4%',
        background: PAPER.marker, transformOrigin: 'left center',
        transform: `scaleX(${grow}) rotate(-0.6deg)`,
        borderRadius: 3, zIndex: 0,
      }} />
    ) : null}
    <span style={{ position: 'relative', zIndex: 1 }}>{children}</span>
  </span>
);

/** Mũi tên cong vẽ tay, chỉ vào nhân vật. */
const Arrow: React.FC<{ at: number }> = ({ at }) => {
  const frame = useCurrentFrame();
  const draw = interpolate(frame - at, [0, 22], [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <svg width={260} height={230} viewBox="0 0 260 230"
         style={{ position: 'absolute', left: 104, top: 880 }}>
      <path d="M20 40 C60 170, 150 210, 238 168"
            fill="none" stroke={PAPER.red} strokeWidth={9} strokeLinecap="round"
            strokeDasharray={330} strokeDashoffset={330 * (1 - draw)} />
      <path d="M196 132 L242 166 L198 196"
            fill="none" stroke={PAPER.red} strokeWidth={9}
            strokeLinecap="round" strokeLinejoin="round"
            opacity={draw > 0.9 ? 1 : 0} />
    </svg>
  );
};

/**
 * Bốn KIỂU CHỮ cho màn nhân vật. Ba ảnh mẫu người dùng gửi mỗi cái một
 * kiểu -- một cái đủ khối báo (ngày, tít, sapo, tên báo), một cái chỉ có
 * chân dung với nét vẽ tay, một cái tít khổng lồ tràn cả ra ngoài mép. Dùng
 * chung một khuôn cho mọi màn thì tới màn thứ ba người xem đã thấy lặp.
 *
 *   masthead  khối báo đầy đủ: chip ngày + tít + sapo + tên báo có gạch
 *   bleed     tít khổng lồ tràn hai mép, không sapo -- dùng cho câu đắt
 *   stamp     tít chữ in trong khối đỏ đặc, như con dấu đóng lên trang
 *   quote     dấu nháy lớn + câu nói + tên người, dùng khi trích lời
 */
export type EdVariant = 'masthead' | 'bleed' | 'stamp' | 'quote';

/**
 * @param headline   tiêu đề, cụm nào cần bôi vàng thì bọc trong **hai sao**
 * @param cutFile    ảnh nhân vật đã tách nền (KHÔNG cần viền sẵn)
 * @param ringColor  màu viền quanh người -- mẫu dùng đỏ hoặc vàng
 */
export const EditorialPerson: React.FC<{
  date?: string; headline: string; standfirst?: string; masthead?: string;
  cutFile: string; credit?: string; variant?: EdVariant;
  name?: string; role?: string;
  serif: string; sans: string; at: number;
}> = ({ date, headline, standfirst, masthead, cutFile, credit,
        variant = 'masthead', name, role, serif, sans, at }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const chip = spring({ frame: frame - at, fps, config: { damping: 22, stiffness: 170, mass: 0.7 } });
  const head = spring({ frame: frame - at - 6, fps, config: { damping: 24, stiffness: 140, mass: 0.9 } });
  const stand = spring({ frame: frame - at - 16, fps, config: { damping: 24, stiffness: 140, mass: 0.9 } });
  // người trượt vào từ mép phải dưới, hơi nghiêng rồi đứng thẳng
  const man = spring({ frame: frame - at - 10, fps, config: { damping: 26, stiffness: 105, mass: 1.2 } });
  const markGrow = interpolate(frame - at - 20, [0, 14], [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  const W = 1080 - 96 * 2;
  const parts = headline.split('**');
  const plain = parts.join('');
  const size = Math.min(96, fitText({
    text: plain.length > 40 ? plain.slice(0, 40) : plain,
    withinWidth: W, fontFamily: serif, fontWeight: '900', letterSpacing: '-0.01em',
  }).fontSize);

  return (
    <AbsoluteFill>
      <PaperBg />

      {/* nhân vật: đen trắng, viền màu, trượt chéo vào từ góc phải dưới */}
      <div style={{
        position: 'absolute', right: -70, bottom: -90,
        transform: `translate(${interpolate(man, [0, 1], [380, 0])}px,`
          + ` ${interpolate(man, [0, 1], [300, 0])}px)`
          + ` rotate(${interpolate(man, [0, 1], [4, 0])}deg)`,
        opacity: interpolate(man, [0, 0.3], [0, 1], { extrapolateRight: 'clamp' }),
      }}>
        <Img src={staticFile(cutFile)} style={{
          height: 1180, width: 'auto', display: 'block',
          // KHÔNG phủ bộ lọc nào: ảnh đã đen trắng và đã viền sẵn trong
          // file PNG. Phủ grayscale ở đây ăn luôn cả viền, biến viền đỏ
          // thành xám -- đo thật trên khung dựng thử.
        }} />
      </div>

      {variant === 'bleed' ? (
        /* Tít khổng lồ tràn ra ngoài hai mép -- đúng kiểu ảnh mẫu thứ ba,
           chữ bị xén ở rìa khung làm khung hình như một trang báo phóng to. */
        <div style={{
          position: 'absolute', left: -46, right: -46, top: 190,
          opacity: interpolate(head, [0, 1], [0, 1]),
          transform: `translateY(${interpolate(head, [0, 1], [22, 0])}px)`,
        }}>
          <div style={{
            fontFamily: serif, fontWeight: '900', fontSize: 132, lineHeight: 1.02,
            color: PAPER.ink, letterSpacing: '-0.03em', whiteSpace: 'nowrap',
          }}>
            {parts.map((seg, i) => (
              <Mark key={i} on={i % 2 === 1} grow={markGrow}>{seg}</Mark>
            ))}
          </div>
        </div>
      ) : variant === 'stamp' ? (
        /* Tít chữ in trắng trong khối đỏ đặc, như con dấu đóng lên trang. */
        <div style={{ position: 'absolute', left: 96, right: 96, top: 230 }}>
          <div style={{
            display: 'inline-block', background: PAPER.red, padding: '20px 30px 24px',
            transform: `rotate(-1.2deg) translateY(${interpolate(head, [0, 1], [20, 0])}px)`,
            opacity: interpolate(head, [0, 1], [0, 1]),
          }}>
            <span style={{
              fontFamily: sans, fontWeight: '900', fontSize: 62, lineHeight: 1.12,
              color: '#FFF', letterSpacing: '-0.01em', textTransform: 'uppercase',
            }}>{plain}</span>
          </div>
          {standfirst ? (
            <div style={{
              marginTop: 26, maxWidth: 780,
              fontFamily: serif, fontWeight: '500', fontSize: 34, lineHeight: 1.45,
              color: PAPER.muted,
              opacity: interpolate(stand, [0, 1], [0, 1]),
            }}>{standfirst}</div>
          ) : null}
        </div>
      ) : variant === 'quote' ? (
        /* Dấu nháy lớn + câu nói + tên người, dùng khi trích lời nhân vật. */
        <div style={{ position: 'absolute', left: 96, right: 300, top: 250 }}>
          <div style={{
            fontFamily: serif, fontWeight: '900', fontSize: 130, lineHeight: 0.6,
            color: PAPER.red, marginBottom: 18,
            opacity: interpolate(chip, [0, 1], [0, 1]),
          }}>&ldquo;</div>
          <div style={{
            fontFamily: serif, fontWeight: '700', fontSize: 58, lineHeight: 1.25,
            color: PAPER.ink, fontStyle: 'italic',
            opacity: interpolate(head, [0, 1], [0, 1]),
            transform: `translateY(${interpolate(head, [0, 1], [16, 0])}px)`,
          }}>{plain}</div>
          {name ? (
            <div style={{
              marginTop: 28, paddingTop: 18, borderTop: `3px solid ${PAPER.red}`,
              display: 'inline-block',
              opacity: interpolate(stand, [0, 1], [0, 1]),
            }}>
              <div style={{ fontFamily: sans, fontWeight: '800', fontSize: 34, color: PAPER.ink }}>{name}</div>
              {role ? (
                <div style={{ marginTop: 4, fontFamily: sans, fontWeight: '600', fontSize: 25, color: PAPER.muted }}>{role}</div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : (
        <div style={{ position: 'absolute', left: 96, right: 96, top: 210 }}>
        {date ? (
          <div style={{
            display: 'inline-block', padding: '10px 22px 12px',
            background: PAPER.red, color: '#FFF',
            fontFamily: sans, fontWeight: '700', fontSize: 28, letterSpacing: '0.02em',
            opacity: interpolate(chip, [0, 1], [0, 1]),
            transform: `translateY(${interpolate(chip, [0, 1], [-14, 0])}px)`,
          }}>{date}</div>
        ) : null}

        <div style={{
          marginTop: 26,
          fontFamily: serif, fontWeight: '900', fontSize: size, lineHeight: 1.12,
          color: PAPER.ink, letterSpacing: '-0.01em',
          opacity: interpolate(head, [0, 1], [0, 1]),
          transform: `translateY(${interpolate(head, [0, 1], [18, 0])}px)`,
        }}>
          {parts.map((seg, i) => (
            <Mark key={i} on={i % 2 === 1} grow={markGrow}>{seg}</Mark>
          ))}
        </div>

        {standfirst ? (
          <div style={{
            marginTop: 22, maxWidth: 860,
            fontFamily: serif, fontWeight: '500', fontSize: 34, lineHeight: 1.45,
            color: PAPER.muted,
            opacity: interpolate(stand, [0, 1], [0, 1]),
            transform: `translateY(${interpolate(stand, [0, 1], [14, 0])}px)`,
          }}>{standfirst}</div>
        ) : null}

        {masthead ? (
          <div style={{
            marginTop: 30, display: 'flex', alignItems: 'center', gap: 24,
            opacity: interpolate(stand, [0, 1], [0, 1]),
          }}>
            <span style={{
              fontFamily: serif, fontWeight: '700', fontSize: 34, color: PAPER.ink,
              whiteSpace: 'nowrap',
            }}>{masthead}</span>
            <span style={{ flex: 1, height: 2, background: PAPER.rule, opacity: 0.85 }} />
          </div>
        ) : null}
      </div>

      )}

      <Arrow at={at + 26} />

      {credit ? (
        <div style={{
          position: 'absolute', left: 96, bottom: 54,
          fontFamily: sans, fontWeight: '600', fontSize: 20, letterSpacing: '0.1em',
          color: PAPER.muted, opacity: 0.75, textTransform: 'uppercase',
        }}>ảnh: {credit}</div>
      ) : null}
    </AbsoluteFill>
  );
};
