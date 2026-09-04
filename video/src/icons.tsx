import React from 'react';

/**
 * Mỗi icon có 2 phần:
 *  - body : bóng khối đặc, dùng để ĐÙN ra chiều sâu (nhân bản nhiều lớp theo trục Z)
 *  - face : mặt trước có chi tiết, chỉ vẽ 1 lần trên cùng
 * Toàn bộ nằm trong lưới 24×24.
 */
export type Icon = {
  body: (fill: string) => React.ReactNode;
  face: (light: string, dark: string) => React.ReactNode;
};

const R = (p: React.SVGProps<SVGRectElement>) => <rect {...p} />;

export const ICONS: Record<string, Icon> = {
  // con trỏ chuột — motif chủ đạo của cả video
  cursor: {
    body: (f) => <path d="M5 2 L5 20.5 L9.4 16.2 L12.4 22.4 L15.4 21 L12.4 15 L18.8 14.8 Z" fill={f} />,
    face: (l, d) => (
      <>
        <path d="M5 2 L5 20.5 L9.4 16.2 L12.4 22.4 L15.4 21 L12.4 15 L18.8 14.8 Z" fill={l} stroke={d} strokeWidth={0.9} strokeLinejoin="round" />
      </>
    ),
  },

  // cửa sổ ứng dụng — Codex điều khiển máy
  window: {
    body: (f) => R({ x: 2, y: 4, width: 20, height: 16, rx: 2.4, fill: f }),
    face: (l, d) => (
      <>
        {R({ x: 2, y: 4, width: 20, height: 16, rx: 2.4, fill: l, stroke: d, strokeWidth: 0.9 })}
        <path d="M2 8.6 H22" stroke={d} strokeWidth={1.1} />
        <circle cx={4.9} cy={6.3} r={0.85} fill={d} />
        <circle cx={7.6} cy={6.3} r={0.85} fill={d} />
        <circle cx={10.3} cy={6.3} r={0.85} fill={d} />
        {R({ x: 5, y: 11.4, width: 9, height: 1.5, rx: 0.75, fill: d, opacity: 0.55 })}
        {R({ x: 5, y: 14.6, width: 13, height: 1.5, rx: 0.75, fill: d, opacity: 0.32 })}
      </>
    ),
  },

  // phím bấm — gõ một câu, dựng nguyên web app
  key: {
    body: (f) => R({ x: 3, y: 3, width: 18, height: 18, rx: 3.4, fill: f }),
    face: (l, d) => (
      <>
        {R({ x: 3, y: 3, width: 18, height: 18, rx: 3.4, fill: l, stroke: d, strokeWidth: 0.9 })}
        {R({ x: 6.2, y: 6.2, width: 11.6, height: 11.6, rx: 2.2, fill: 'none', stroke: d, strokeWidth: 1, opacity: 0.5 })}
        <path d="M9.6 13.6 L12 9.4 L14.4 13.6 Z" fill={d} />
      </>
    ),
  },

  // khung ảnh — GPT Image 1.5
  image: {
    body: (f) => R({ x: 2.5, y: 4.5, width: 19, height: 15, rx: 2.2, fill: f }),
    face: (l, d) => (
      <>
        {R({ x: 2.5, y: 4.5, width: 19, height: 15, rx: 2.2, fill: l, stroke: d, strokeWidth: 0.9 })}
        <circle cx={8} cy={9.4} r={1.9} fill={d} opacity={0.65} />
        <path d="M4 18.2 L10 11.6 L14.2 16 L16.8 13.2 L20 17.4 L20 19.5 L4 19.5 Z" fill={d} />
      </>
    ),
  },

  // chip nhớ — nó bắt đầu nhớ
  chip: {
    body: (f) => R({ x: 4, y: 4, width: 16, height: 16, rx: 2.2, fill: f }),
    face: (l, d) => (
      <>
        {[7.5, 12, 16.5].map((v) => (
          <g key={v}>
            <path d={`M${v} 1.6 V4`} stroke={d} strokeWidth={1.5} />
            <path d={`M${v} 20 V22.4`} stroke={d} strokeWidth={1.5} />
            <path d={`M1.6 ${v} H4`} stroke={d} strokeWidth={1.5} />
            <path d={`M20 ${v} H22.4`} stroke={d} strokeWidth={1.5} />
          </g>
        ))}
        {R({ x: 4, y: 4, width: 16, height: 16, rx: 2.2, fill: l, stroke: d, strokeWidth: 0.9 })}
        {R({ x: 8.4, y: 8.4, width: 7.2, height: 7.2, rx: 1.2, fill: d, opacity: 0.72 })}
      </>
    ),
  },

  // đồng hồ — task kéo dài nhiều tuần, tự thức dậy
  clock: {
    body: (f) => <circle cx={12} cy={12} r={9.4} fill={f} />,
    face: (l, d) => (
      <>
        <circle cx={12} cy={12} r={9.4} fill={l} stroke={d} strokeWidth={0.9} />
        <circle cx={12} cy={12} r={7.1} fill="none" stroke={d} strokeWidth={0.8} opacity={0.35} />
        <path d="M12 6.6 V12 L15.9 14.3" stroke={d} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <circle cx={12} cy={12} r={1.05} fill={d} />
      </>
    ),
  },

  // phích cắm — 111 plugin
  plug: {
    body: (f) => <path d="M6.4 8.6 H17.6 V13.2 A5.6 5.6 0 0 1 6.4 13.2 Z" fill={f} />,
    face: (l, d) => (
      <>
        <path d="M9.2 2.4 V8.6" stroke={d} strokeWidth={1.8} strokeLinecap="round" />
        <path d="M14.8 2.4 V8.6" stroke={d} strokeWidth={1.8} strokeLinecap="round" />
        <path d="M6.4 8.6 H17.6 V13.2 A5.6 5.6 0 0 1 6.4 13.2 Z" fill={l} stroke={d} strokeWidth={0.9} strokeLinejoin="round" />
        <path d="M12 18.8 V22" stroke={d} strokeWidth={1.8} strokeLinecap="round" />
      </>
    ),
  },

  // lưới 6 ô — "sáu thứ Codex vừa làm được"
  grid6: {
    body: (f) => R({ x: 2.6, y: 4.6, width: 18.8, height: 14.8, rx: 2.2, fill: f }),
    face: (l, d) => (
      <>
        {R({ x: 2.6, y: 4.6, width: 18.8, height: 14.8, rx: 2.2, fill: l, stroke: d, strokeWidth: 0.9 })}
        {[0, 1, 2].map((c) =>
          [0, 1].map((r) => (
            <rect key={`${c}${r}`} x={5.1 + c * 5.4} y={7.5 + r * 5.2} width={3.8} height={3.8} rx={1} fill={d} opacity={r ? 0.4 : 0.75} />
          )),
        )}
      </>
    ),
  },

  // khối lập phương — dùng làm vật thể nền
  cube: {
    body: (f) => R({ x: 3.5, y: 3.5, width: 17, height: 17, rx: 1.6, fill: f }),
    face: (l, d) => (
      <>
        {R({ x: 3.5, y: 3.5, width: 17, height: 17, rx: 1.6, fill: l, stroke: d, strokeWidth: 0.9 })}
      </>
    ),
  },
  // bong bóng thoại — dạy AI cãi lại
  bubble: {
    body: (f) => <path d="M3 5.6 H21 V17 H10.8 L6.2 21 V17 H3 Z" fill={f} />,
    face: (l, d) => (
      <>
        <path d="M3 5.6 H21 V17 H10.8 L6.2 21 V17 H3 Z" fill={l} stroke={d} strokeWidth={0.9} strokeLinejoin="round" />
        <circle cx={8.4} cy={11.3} r={1.15} fill={d} />
        <circle cx={12} cy={11.3} r={1.15} fill={d} />
        <circle cx={15.6} cy={11.3} r={1.15} fill={d} />
      </>
    ),
  },

  // sóng âm — báo cáo thành podcast
  wave: {
    body: (f) => R({ x: 2.6, y: 6.4, width: 18.8, height: 11.2, rx: 2.4, fill: f }),
    face: (l, d) => (
      <>
        {R({ x: 2.6, y: 6.4, width: 18.8, height: 11.2, rx: 2.4, fill: l, stroke: d, strokeWidth: 0.9 })}
        {[[6.4, 3.0], [9.0, 5.6], [11.6, 7.6], [14.2, 5.0], [16.8, 2.6]].map(([x, h]) => (
          <rect key={x} x={x - 0.75} y={12 - h / 2} width={1.5} height={h} rx={0.75} fill={d} />
        ))}
      </>
    ),
  },
};

/** map chương → icon */
export const SECTION_ICON: Record<string, string> = {
  'BẠN ĐANG TRẢ TIỀN CHO NÓ': 'cursor',
  '1 · DẠY NÓ CÃI LẠI': 'bubble',
  '2 · HỎI 5 TAB CÙNG LÚC': 'window',
  '3 · BÁO CÁO → PODCAST': 'wave',
  '4 · NÓ LÀM KHI BẠN NGỦ': 'clock',
  'SỰ THẬT': 'cube',
  'CÒN 6 MẸO NỮA': 'grid6',
};
