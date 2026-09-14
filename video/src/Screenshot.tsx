import React from 'react';
import { Img, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { useMotion } from './anim';
import { Frame, type P } from './layouts';
import { T } from './theme';

const FRAME_W = 1080 - T.PAD * 2;

/**
 * Ảnh chụp đặt trần: bo góc nhẹ, không khung trình duyệt giả, không thanh
 * địa chỉ, không dòng ghi nguồn -- bản tham chiếu để ảnh nói chuyện một
 * mình, mấy thứ trang trí đó chỉ làm khung hình rẻ tiền đi. Chữ của thẻ
 * chạy ở phụ đề dưới cùng như mọi thẻ khác, không in đè lên ảnh.
 */
export const ScreenshotCard: React.FC<P> = ({ card, leaving }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = useMotion(frame, fps, card.start, leaving, T.EXIT, card.motion, card.exit);
  return (
    <Frame card={card} align="center">
      <div style={{
        width: FRAME_W, borderRadius: 16, overflow: 'hidden',
        boxShadow: '0 30px 80px rgba(0,0,0,0.6)',
        opacity: a.opacity, transform: a.transform, filter: a.filter,
      }}>
        <Img src={staticFile(card.screenshotFile!)} style={{ width: '100%', display: 'block' }} />
      </div>
    </Frame>
  );
};
