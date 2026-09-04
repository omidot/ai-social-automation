export const T = {
  bg: '#EDECEA',
  bgHi: '#FCFCFB',
  bgLo: '#C9C7C4',
  ink: '#0B0B0B',
  ink2: '#333230',
  gray: '#8C8A87',
  wedge: '#1B1B1B',
  grid: '#B5B3AF',
  PAD: 104,          // lề trái/phải của khối chữ
  EXIT: 8,           // số frame cho hiệu ứng mờ dần khi card thoát
  SIZE: { small: 64, big: 112, accent: 104 },
  WEIGHT: { small: '700', big: '900', accent: '900' },
};
export const roleOf = (i: number, n: number) =>
  (i === n - 1 ? 'accent' : n === 3 && i === 0 ? 'small' : 'big') as 'small' | 'big' | 'accent';
