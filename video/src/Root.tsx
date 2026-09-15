import { Composition } from 'remotion';
import { KineticShort } from './KineticShort';
import { ScreenPreview } from './ScreenPreview';
import timeline from './timeline.json';

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="CodexShort"
      component={KineticShort}
      durationInFrames={timeline.durationInFrames}
      fps={timeline.fps}
      width={1080}
      height={1920}
    />
    {/* Bản dựng thử từng DẠNG MÀN HÌNH để đối chiếu với video mẫu bằng ảnh
        tĩnh -- không phải video thật, chỉ để soi bố cục cho nhanh thay vì
        phải render cả phút mới biết sai chỗ nào. */}
    <Composition
      id="ScreenPreview"
      component={ScreenPreview}
      durationInFrames={600}
      fps={30}
      width={1080}
      height={1920}
    />
  </>
);
