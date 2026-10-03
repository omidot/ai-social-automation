/**
 * BẢNG MÀU + NHỊP CHUYỂN ĐỘNG cho video promo.
 *
 * Màu lấy đúng ba giá trị người dùng chỉ định, không tự thêm sắc nào khác:
 * nền giấy, cam nhấn, và mực/nền tối. Mọi thứ khác chỉ là các mức alpha của
 * ba màu này -- cấm gradient tím, glow, emoji.
 */

export const C = {
  paper: '#fbf6e8',
  orange: '#f47c30',
  ink: '#141a22',
} as const;

export type BgKind = 'paper' | 'orange' | 'dark';

/** Nền và màu mực tương ứng cho từng loại cảnh. */
export const bgOf = (k: BgKind) =>
  k === 'paper' ? { bg: C.paper, fg: C.ink, dim: 'rgba(20,26,34,0.55)' }
  : k === 'orange' ? { bg: C.orange, fg: C.ink, dim: 'rgba(20,26,34,0.62)' }
  : { bg: C.ink, fg: C.paper, dim: 'rgba(251,246,232,0.55)' };

/**
 * power3.out của GSAP: 1 - (1-t)^3.
 *
 * Người dùng chỉ đích danh easing này cho chữ blur-in, nên nó được viết lại
 * đúng công thức thay vì dùng một easing "gần giống" của Remotion.
 */
export const power3Out = (t: number) => 1 - Math.pow(1 - t, 3);

/** power4.inOut -- dùng cho whip chuyển cảnh, nhanh ở giữa, êm hai đầu. */
export const power4InOut = (t: number) =>
  t < 0.5 ? 8 * t * t * t * t : 1 - Math.pow(-2 * t + 2, 4) / 2;

/** Tiến độ 0..1 của một mốc, theo giây. Clamp hai đầu để seek tới đâu cũng đúng. */
export const prog = (t: number, at: number, dur: number) => {
  if (dur <= 0) return t >= at ? 1 : 0;
  const x = (t - at) / dur;
  return x <= 0 ? 0 : x >= 1 ? 1 : x;
};

/**
 * NHỊP CHỮ BLUR-IN -- đúng thông số người dùng đưa:
 * blur 16px -> 0, trượt lên 70px, stagger 0.07s mỗi đơn vị, power3.out.
 */
export const BLUR_IN = {
  blurPx: 16,
  riseY: 70,
  stagger: 0.07,
  dur: 0.62,
} as const;

/** Trạng thái một đơn vị chữ (từ) tại thời điểm t. */
export const blurInAt = (t: number, at: number, index: number) => {
  const p = power3Out(prog(t, at + index * BLUR_IN.stagger, BLUR_IN.dur));
  return {
    opacity: p,
    blur: BLUR_IN.blurPx * (1 - p),
    y: BLUR_IN.riseY * (1 - p),
  };
};

/**
 * Góc xoay cố định cho thẻ UI, trong khoảng ±2..8 độ.
 *
 * Phải suy ra từ chỉ số thẻ chứ KHÔNG dùng Math.random: bản dựng phải seek
 * tới frame nào cũng ra đúng một kết quả, và render lại lần sau không được
 * lệch so với bản snapshot người dùng đã duyệt.
 */
export const tiltOf = (i: number) => {
  const mag = 2 + ((i * 37) % 7); // 2..8
  return i % 2 === 0 ? -mag : mag;
};

/** Bóng mềm của thẻ UI trắng. */
export const CARD_SHADOW = '0 18px 48px rgba(20,26,34,0.22)';
export const CARD_RADIUS = 24;

/** Timecode 00:00:SS:FF từ giây và fps. */
export const timecode = (t: number, fps: number) => {
  const total = Math.max(0, Math.floor(t * fps));
  const ff = total % fps;
  const s = Math.floor(total / fps);
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(hh)}:${p(mm)}:${p(ss)}:${p(ff)}`;
};
