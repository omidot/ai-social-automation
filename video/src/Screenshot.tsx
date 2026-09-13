import React from 'react';
import { Img, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { usePal } from './palette';
import { useMotion } from './anim';
import { Frame, shown, type P } from './layouts';
import { T } from './theme';

const FRAME_W = 1080 - T.PAD * 2;

export const ScreenshotCard: React.FC<P> = ({ card, ff, leaving }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const a = useMotion(frame, fps, card.start, leaving, T.EXIT, card.motion, card.exit);
  return (
    <Frame card={card} align="center">
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center',
                    opacity: a.opacity, transform: a.transform, filter: a.filter }}>
        <div style={{ width: FRAME_W, borderRadius: 14, overflow: 'hidden',
                      boxShadow: '0 20px 60px rgba(0,0,0,0.5)', background: '#fff' }}>
          <div style={{ background: '#e8e8e8', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#ff5f57' }} />
            <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#febc2e' }} />
            <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#28c840' }} />
            {card.screenshotUrl ? (
              <div style={{ flex: 1, background: '#fff', borderRadius: 6, fontSize: 20, color: '#555',
                            padding: '4px 12px', marginLeft: 8, overflow: 'hidden', textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap', fontFamily: 'monospace' }}>
                {card.screenshotUrl.replace(/^https?:\/\//, '')}
              </div>
            ) : null}
          </div>
          <Img src={staticFile(card.screenshotFile!)}
               style={{ width: '100%', display: 'block' }} />
        </div>
        {ls.map((l, i) => (
          <span key={i} style={{
            fontFamily: ff, fontWeight: '800', fontSize: 52, lineHeight: 1.2, color: pal.ink,
            textShadow: pal.shadow, marginTop: 24, textAlign: 'center', whiteSpace: 'pre-wrap',
            textTransform: 'uppercase',
          }}>{l.text}</span>
        ))}
      </div>
    </Frame>
  );
};
