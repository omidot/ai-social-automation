export const Cursor: React.FC<{ size?: number; light?: boolean }> = ({ size = 52, light }) => (
  <svg width={size} height={size * 1.32} viewBox="0 0 25 33" style={{ display: 'block' }}>
    <path
      d="M2 1.5 L2 27.5 L8.6 21.2 L12.9 30.9 L17.4 28.8 L13.2 19.4 L22.2 19.1 Z"
      fill={light ? '#FFFFFF' : '#0B0B0B'}
      stroke={light ? '#0B0B0B' : '#FFFFFF'}
      strokeWidth={1.6}
      strokeLinejoin="round"
    />
  </svg>
);
