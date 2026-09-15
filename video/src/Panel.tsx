import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fitText } from '@remotion/layout-utils';
import { usePal } from './palette';

/**
 * Bộ "tấm thông tin" dựng theo đúng bản tham chiếu người dùng gửi.
 *
 * Quan sát từng khung hình của bản mẫu: mọi đoạn đều là MỘT tiêu đề ngắn
 * hai sắc độ (cụm đầu đậm trắng, phần còn lại nhạt hơn) đặt trên một hoặc
 * vài HỘP BO TRÒN nền mờ. Trong hộp là: nhãn nhỏ bên trái + con số to bên
 * phải, hoặc số thứ tự + tiêu đề + mô tả nhỏ, hoặc nhãn/giá trị nằm trên
 * một thanh chạy hết chiều ngang.
 *
 * Đây KHÔNG phải tiêu đề của card (người dùng nói rõ không muốn tiêu đề
 * lặp lại lời thoại) -- nó là nhãn ngắn cho biết HỘP SỐ LIỆU bên dưới đang
 * đo cái gì, đúng vai trò nó đảm nhiệm trong bản mẫu.
 */

const W = 1080 - 88 * 2;

/** Tiêu đề hai sắc độ: cụm từ đầu đậm, phần sau nhạt -- như bản mẫu. */
export const PanelTitle: React.FC<{ text: string; ff: string; at: number }> = ({ text, ff, at }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const s = spring({ frame: frame - at, fps, config: { damping: 20, stiffness: 160, mass: 0.7 } });
  const words = text.split(' ');
  const cut = Math.max(1, Math.min(2, words.length - 1));
  const head = words.slice(0, cut).join(' ');
  const tail = words.slice(cut).join(' ');
  const size = Math.min(52, fitText({
    text, withinWidth: W, fontFamily: ff, fontWeight: '800', letterSpacing: '-0.01em',
  }).fontSize);
  return (
    <div style={{
      textAlign: 'center', marginBottom: 30,
      opacity: interpolate(s, [0, 1], [0, 1]),
      transform: `translateY(${interpolate(s, [0, 1], [-12, 0])}px)`,
    }}>
      <span style={{ fontFamily: ff, fontWeight: '800', fontSize: size, color: pal.ink }}>{head}</span>
      {tail ? (
        <span style={{ fontFamily: ff, fontWeight: '600', fontSize: size, color: pal.ink, opacity: 0.62 }}> {tail}</span>
      ) : null}
    </div>
  );
};

/** Hộp bo tròn nền mờ -- khối dựng cơ bản của mọi tấm trong bản mẫu. */
export const Box: React.FC<{
  at: number; delay?: number; children: React.ReactNode; pad?: string;
}> = ({ at, delay = 0, children, pad = '30px 34px' }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - at - delay, fps, config: { damping: 21, stiffness: 150, mass: 0.8 } });
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 22,
      padding: pad, marginBottom: 20, borderRadius: 22,
      background: 'rgba(255,255,255,0.045)',
      border: '1px solid rgba(255,255,255,0.09)',
      opacity: interpolate(s, [0, 1], [0, 1]),
      transform: `translateY(${interpolate(s, [0, 1], [20, 0])}px)`,
    }}>{children}</div>
  );
};

/**
 * SỐ ĐANG CHẠY rồi dừng đúng con số thật.
 *
 * Yêu cầu trực tiếp: khi giọng đọc nói tới một con số thì con số trên màn
 * phải chạy lên rồi dừng lại đúng nó. Điểm mấu chốt là DỪNG ĐÚNG LÚC NÓI
 * XONG, nên thời lượng chạy không đặt cứng mà nhận từ ngoài vào (`runFor`)
 * theo đúng độ dài lời nói của con số đó.
 *
 * Số thập phân giữ nguyên số chữ số sau dấu phẩy trong suốt lúc chạy, nếu
 * không thì "0.60" nhảy loạn giữa "0" và "0.6" trông như lỗi.
 */
const Rolling: React.FC<{ value: number; unit: string; at: number; runFor: number }> =
({ value, unit, at, runFor }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = interpolate(frame - at, [0, Math.max(1, runFor)], [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  // chậm dần về cuối -> cảm giác "hãm lại rồi đứng yên"
  const eased = 1 - Math.pow(1 - p, 3);
  const dec = String(value).includes('.') ? String(value).split('.')[1].length : 0;
  const shown = p >= 1 ? value : Number((value * eased).toFixed(dec));
  return <>{fmtVal(shown, unit)}</>;
};

const fmtVal = (v: number, unit: string) => {
  const n = Number.isInteger(v) ? v.toLocaleString('en-US') : String(v);
  if (!unit) return n;
  if (unit === '$') return `$${n}`;
  if (unit === '%' || unit === 'x') return `${n}${unit}`;
  return `${n} ${unit}`;
};

/** Hàng SỐ LIỆU: nhãn nhỏ trái, con số to phải. Bản mẫu dùng cho giá/thông số. */
export const StatBox: React.FC<{
  label: string; value: number; unit: string; ff: string; at: number; delay: number;
  runFor?: number;
}> = ({ label, value, unit, ff, at, delay, runFor }) => {
  const pal = usePal();
  return (
    <Box at={at} delay={delay}>
      <span style={{
        flex: 1, fontFamily: ff, fontWeight: '600', fontSize: 30,
        color: pal.ink, opacity: 0.62,
      }}>{label}</span>
      <span style={{
        fontFamily: ff, fontWeight: '800', fontSize: 62, lineHeight: 1, color: pal.ink,
        letterSpacing: '-0.02em',
      }}><Rolling value={value} unit={unit} at={at + delay} runFor={runFor ?? 18} /></span>
    </Box>
  );
};

/** Hàng ĐÁNH SỐ: huy hiệu số vuông + tiêu đề đậm + mô tả nhỏ mờ. */
export const StepBox: React.FC<{
  n: number; title: string; note?: string; ff: string; at: number; delay: number;
}> = ({ n, title, note, ff, at, delay }) => {
  const pal = usePal();
  return (
    <Box at={at} delay={delay} pad="26px 30px">
      <span style={{
        width: 52, height: 52, flex: '0 0 52px', borderRadius: 13,
        background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: ff, fontWeight: '800', fontSize: 27, color: pal.ink, opacity: 0.85,
      }}>{n}</span>
      <span style={{ flex: 1 }}>
        <span style={{
          display: 'block', fontFamily: ff, fontWeight: '800', fontSize: 33, color: pal.ink,
        }}>{title}</span>
        {note ? (
          <span style={{
            display: 'block', marginTop: 5, fontFamily: ff, fontWeight: '500', fontSize: 25,
            color: pal.ink, opacity: 0.45,
          }}>{note}</span>
        ) : null}
      </span>
    </Box>
  );
};

/**
 * Hàng SO KÈ: nhãn trái + giá trị phải nằm TRÊN, thanh chạy hết ngang nằm
 * NGAY DƯỚI. Bản mẫu vẽ đúng kiểu này chứ không phải đồ thị có trục.
 */
export const BarRow: React.FC<{
  label: string; value: number; max: number; unit: string; ff: string;
  at: number; delay: number; hot: boolean; runFor?: number;
}> = ({ label, value, max, unit, ff, at, delay, hot, runFor }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const s = spring({ frame: frame - at - delay, fps, config: { damping: 22, stiffness: 140, mass: 0.9 } });
  const pct = max > 0 ? Math.max(0.025, value / max) : 0;
  return (
    <div style={{
      marginBottom: 26,
      opacity: interpolate(s, [0, 1], [0, 1]),
      transform: `translateY(${interpolate(s, [0, 1], [16, 0])}px)`,
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 11,
      }}>
        <span style={{
          fontFamily: ff, fontWeight: hot ? '800' : '600', fontSize: 30,
          color: pal.ink, opacity: hot ? 1 : 0.5,
        }}>{label}</span>
        <span style={{
          fontFamily: ff, fontWeight: '800', fontSize: 34,
          color: hot ? pal.ink : pal.ink, opacity: hot ? 1 : 0.5,
        }}><Rolling value={value} unit={unit} at={at + delay} runFor={runFor ?? 16} /></span>
      </div>
      <div style={{
        height: 42, borderRadius: 21, background: 'rgba(255,255,255,0.05)',
        border: '1px solid rgba(255,255,255,0.07)', overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', borderRadius: 21,
          width: `${pct * interpolate(s, [0, 1], [0, 1]) * 100}%`,
          background: hot
            ? `linear-gradient(90deg, ${pal.accent} 0%, #FF8A6B 100%)`
            : 'linear-gradient(90deg, #6F6F6D 0%, #979794 100%)',
        }} />
      </div>
    </div>
  );
};
