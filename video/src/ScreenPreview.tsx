import React from 'react';
import { AbsoluteFill, continueRender, delayRender, interpolate, useCurrentFrame } from 'remotion';
import { loadFont } from '@remotion/google-fonts/BeVietnamPro';
import { HookScreen, StatementScreen, PersonScreen, REF } from './Screens';
import { PanelTitle, StatBox, StepBox, BarRow } from './Panel';
import { PalCtx, DARK } from './palette';

const { fontFamily, waitUntilDone } = loadFont('normal', {
  weights: ['500', '600', '700', '800', '900'],
  subsets: ['latin', 'vietnamese'],
});
const h = delayRender('preview-font');
waitUntilDone().then(() => continueRender(h));

/**
 * Bản dựng thử để đối chiếu từng dạng màn hình với video mẫu, không phải
 * thành phần của video thật. Mỗi dạng chiếm một đoạn frame riêng để chụp
 * ảnh tĩnh ra xem nhanh, khỏi phải render cả video mới biết sai chỗ nào.
 */

/* Nền giống bản mẫu: gần như đen, có vân chéo mờ và quầng đỏ tối góc trên. */
const Bg: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: REF.bg }}>
    <AbsoluteFill style={{
      backgroundImage:
        'repeating-linear-gradient(45deg, rgba(255,255,255,0.028) 0 1px, transparent 1px 34px),'
        + 'repeating-linear-gradient(-45deg, rgba(255,255,255,0.028) 0 1px, transparent 1px 34px)',
    }} />
    <AbsoluteFill style={{
      background: 'radial-gradient(60% 34% at 74% 12%, rgba(224,60,60,0.16) 0%, transparent 70%)',
    }} />
  </AbsoluteFill>
);

/* Khung viền: đếm chương trái trên, vạch chương mép trái, gạch tiến độ đáy. */
const Chrome: React.FC<{ chapter: number; total: number }> = ({ chapter, total }) => (
  <>
    <div style={{
      position: 'absolute', top: 96, left: 60,
      fontFamily, fontWeight: '700', fontSize: 25, letterSpacing: '0.22em',
      color: REF.ink, opacity: 0.38,
    }}>{String(chapter).padStart(2, '0')} / {String(total).padStart(2, '0')}</div>
    <div style={{
      position: 'absolute', left: 0, top: '14%', bottom: '14%', width: 6,
      display: 'flex', flexDirection: 'column', gap: 12,
    }}>
      {Array.from({ length: total }, (_, i) => (
        <div key={i} style={{
          flex: 1, borderRadius: 3,
          background: i === chapter - 1 ? REF.accent : 'rgba(255,255,255,0.09)',
        }} />
      ))}
    </div>
    <div style={{
      position: 'absolute', left: '22%', right: '22%', bottom: 34, height: 2,
      background: 'linear-gradient(90deg, transparent, rgba(224,60,60,0.5), transparent)',
    }} />
  </>
);

/** Dòng thoại dưới đáy: ngắn, từ đang nói tô đỏ. */
const Caption: React.FC<{ words: string[]; hot: number }> = ({ words, hot }) => (
  <div style={{
    position: 'absolute', left: 0, right: 0, top: '70%',
    display: 'flex', justifyContent: 'center', padding: '0 76px',
  }}>
    <span style={{
      fontFamily, fontWeight: '800', fontSize: 62, letterSpacing: '-0.015em',
      textAlign: 'center', textShadow: '0 4px 30px rgba(0,0,0,0.92)',
    }}>
      {words.map((w, i) => (
        <span key={i} style={{ color: i === hot ? REF.accent : REF.ink }}>
          {w}{i < words.length - 1 ? ' ' : ''}
        </span>
      ))}
    </span>
  </div>
);

const W = 1080 - REF.PAD * 2;

export const ScreenPreview: React.FC = () => {
  const frame = useCurrentFrame();
  const seg = Math.floor(frame / 60);          // mỗi dạng 2 giây
  const at = seg * 60;

  return (
    <AbsoluteFill>
      <Bg />
      <PalCtx.Provider value={DARK}>
        {seg === 0 ? (
          <>
            <HookScreen
              eyebrow="Model nhỏ nhất của DeepSeek"
              title="Hạ gục"
              subtitle="GPT-5.6 & Claude Opus 5"
              foot="trên nhiều bài test agent thật"
              tiles={[
                { label: 'GPT-5.6 Sol', note: 'OpenAI', verdict: 'lose' },
                { label: 'DeepSeek Flash', note: 'nhỏ nhất', verdict: 'win' },
                { label: 'Claude Opus 5', note: 'Anthropic', verdict: 'lose' },
              ]}
              ff={fontFamily} at={at} />
            <Caption words={['mà', 'nó', 'đang', 'hạ', 'cả']} hot={2} />
            <Chrome chapter={1} total={9} />
          </>
        ) : seg === 1 ? (
          <>
            <AbsoluteFill style={{
              alignItems: 'center', justifyContent: 'center',
              paddingLeft: REF.PAD, paddingRight: REF.PAD, paddingBottom: 430,
            }}>
              <div style={{ width: W }}>
                <PanelTitle text="Giá đầu ra mỗi 1 triệu token" ff={fontFamily} at={at} />
                <BarRow label="Claude Opus 5" value={25} max={25} unit="$" ff={fontFamily}
                        at={at} delay={4} hot={false} />
                <BarRow label="GPT-5.6 Sol" value={20} max={25} unit="$" ff={fontFamily}
                        at={at} delay={12} hot={false} />
                <BarRow label="DeepSeek Flash" value={0.6} max={25} unit="$" ff={fontFamily}
                        at={at} delay={20} hot />
              </div>
            </AbsoluteFill>
            <Caption words={['đô.', 'Rẻ', 'hơn', 'bốn', 'chục', 'lần']} hot={1} />
            <Chrome chapter={6} total={9} />
          </>
        ) : seg === 2 ? (
          <>
            <AbsoluteFill style={{
              alignItems: 'center', justifyContent: 'center',
              paddingLeft: REF.PAD, paddingRight: REF.PAD, paddingBottom: 430,
            }}>
              <div style={{ width: W }}>
                <PanelTitle text="Có gì cho bạn" ff={fontFamily} at={at} />
                <StepBox n={1} title="Mã nguồn mở" note="Giấy phép MIT, tải trọng số tự do"
                         ff={fontFamily} at={at} delay={5} />
                <StepBox n={2} title="Có ngay trên API" note="Tên gọi: deepseek-flash"
                         ff={fontFamily} at={at} delay={13} />
              </div>
            </AbsoluteFill>
            <Caption words={['ngày', '14', 'tháng', '9,']} hot={0} />
            <Chrome chapter={7} total={9} />
          </>
        ) : seg === 3 ? (
          <>
            <AbsoluteFill style={{
              alignItems: 'center', justifyContent: 'center',
              paddingLeft: REF.PAD, paddingRight: REF.PAD, paddingBottom: 430,
            }}>
              <div style={{ width: W }}>
                <PanelTitle text="Kiến trúc Causal Encoder-Decoder" ff={fontFamily} at={at} />
                <StatBox label="Tổng tham số" value={552} unit="B" ff={fontFamily}
                         at={at} delay={6} />
                <StatBox label="Kích hoạt mỗi token" value={31} unit="B" ff={fontFamily}
                         at={at} delay={14} />
              </div>
            </AbsoluteFill>
            <Caption words={['tham', 'số,', 'nhưng']} hot={0} />
            <Chrome chapter={2} total={9} />
          </>
        ) : seg === 4 ? (
          <>
            <PersonScreen
              file="portraits/altman.png"
              name="Sam Altman"
              role="CEO OpenAI"
              quote="Họ kiểm tra AI ít hơn hẳn so với các thế hệ trước."
              credit="Wikipedia · Sam Altman"
              ff={fontFamily} at={at} />
            <Caption words={['ít', 'hơn', 'hẳn']} hot={0} />
            <Chrome chapter={3} total={9} />
          </>
        ) : (
          <>
            <StatementScreen
              eyebrow="Cuộc đua đã đổi trục"
              lead="Không phải ai lớn nhất, mà ai"
              highlight="rẻ nhất mỗi token"
              body="DeepSeek tự thay flagship trả phí V4-Pro bằng chính con model nhỏ và rẻ hơn, vẫn ngang cơ các flagship hàng đầu."
              ff={fontFamily} at={at} />
            <Caption words={['từ', 'ai', 'lớn', 'nhất']} hot={3} />
            <Chrome chapter={8} total={9} />
          </>
        )}
      </PalCtx.Provider>
    </AbsoluteFill>
  );
};
