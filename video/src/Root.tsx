import { Composition } from 'remotion';
import { KineticShort } from './KineticShort';
import timeline from './timeline.json';

export const RemotionRoot: React.FC = () => (
  <Composition
    id="CodexShort"
    component={KineticShort}
    durationInFrames={timeline.durationInFrames}
    fps={timeline.fps}
    width={1080}
    height={1920}
  />
);
