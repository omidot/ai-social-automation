import React from 'react';
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { useMotion } from './anim';
import { type P } from './layouts';
import { T } from './theme';

/**
 * Ảnh chụp TRÀN VIỀN, không bo góc, không nổi giữa khung như một tấm thẻ --
 * bản tham chiếu luôn cho ảnh chiếm trọn khung dọc, chỉ làm tối dần hai mép
 * trên/dưới (vignette) để chữ header/phụ đề còn đọc được đè lên trên. Không
 * khung trình duyệt giả, không thanh địa chỉ, không dòng ghi nguồn.
 */
export const ScreenshotCard: React.FC<P> = ({ card, leaving }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // Ảnh đứng nguyên cả đoạn -> hiệu ứng vào tính từ mốc card đầu của nhóm.
  const a = useMotion(frame, fps, card.visualAt ?? card.start, leaving, T.EXIT, card.motion, card.exit);
  return (
    <AbsoluteFill style={{ opacity: a.opacity, transform: a.transform, filter: a.filter }}>
      <Img src={staticFile(card.screenshotFile!)}
           style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
      <AbsoluteFill style={{
        background: 'linear-gradient(to bottom, rgba(0,0,0,0.62) 0%, rgba(0,0,0,0.05) 22%, rgba(0,0,0,0.05) 66%, rgba(0,0,0,0.78) 100%)',
      }} />
    </AbsoluteFill>
  );
};
