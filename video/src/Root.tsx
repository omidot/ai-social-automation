import { Composition } from 'remotion';
import { KineticShort } from './KineticShort';
import { ScreenPreview } from './ScreenPreview';
import { Promo, promoConfig } from './promo/Promo';
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
    {/* Video promo 9:16 dựng từ ba file thu: linh vật dither, thẻ UI trắng,
        chữ blur-in. Mốc giờ mọi cảnh bám đúng lời đọc thật. */}
    <Composition
      id={promoConfig.id}
      component={Promo}
      durationInFrames={promoConfig.durationInFrames}
      fps={promoConfig.fps}
      width={promoConfig.width}
      height={promoConfig.height}
    />
  </>
);
