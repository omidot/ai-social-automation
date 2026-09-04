import React from 'react';
import { Audio, Sequence, staticFile } from 'remotion';
import timeline from './timeline.json';
import { SHOTS } from './Shots';
import { CUTOUTS } from './Cutouts';
import { shown, type Card } from './layouts';

const FPS = timeline.fps;
const cards = timeline.cards as Card[];

type Cue = { at: number; file: string; vol: number; rate?: number };
const cues: Cue[] = [];
const add = (at: number, file: string, vol: number, rate?: number) => cues.push({ at: Math.max(0, at), file, vol, rate });

/* 1. NHẠC MỞ ĐẦU — chỉ còn intro. Nền cinematic (bed) ĐÃ BỎ theo yêu cầu. */
add(0, 'sfx/intro.mp3', 0.32);                                    // trước 0.22

/* 2. TIẾNG CHỮ — CHỈ khi con SỐ hiện ra (6 card có huy hiệu số).
      Mọi dòng chữ khác không còn tiếng nữa. Cao độ vẫn dao động ±5%. */
let k = 0;
cards.filter((c) => c.variant === 'numeral').forEach((c) => {
  const rate = 0.95 + ((k * 7) % 11) / 100;
  add(c.start - 0.02, 'sfx/text.mp3', 0.30, rate);
  k++;
});

/* 3. TIẾNG HIGHLIGHT — giữ nguyên cho card có thanh đen quét ngang chữ (bôi đậm). */
cards.filter((c) => c.variant === 'mark').forEach((c) => {
  const ls = shown(c);
  if (ls.length) add(ls[ls.length - 1].start + 0.05, 'sfx/hl.mp3', 0.26);
});

/* 4. WHOOSH — mỗi lần ảnh chụp màn hình trượt vào. */
SHOTS.forEach((s) => add(s.at - 0.08, 'sfx/wosh.mp3', 0.28));

/* 5. ẢNH CUTOUT (B-roll giấy dán) — mỗi ảnh một tiếng riêng, không lặp lại. */
const CUTOUT_SFX: Record<string, string> = {
  'cutouts/bulb.png': 'pop', 'cutouts/robothand.png': 'click', 'cutouts/moon.png': 'swipe',
  'cutouts/robotA.png': 'thud', 'cutouts/robotB.png': 'boing', 'cutouts/robotC.png': 'drop',
  'cutouts/phone.png': 'whoosh', 'cutouts/user1.png': 'paper', 'cutouts/skyscraper.png': 'riser',
};
CUTOUTS.forEach((c) => {
  const name = CUTOUT_SFX[c.file];
  if (name) add(c.at - 0.03, `sfx-vox/${name}.wav`, 0.4);
});

cues.sort((a, b) => a.at - b.at);

export const Sfx: React.FC = () => (
  <>
    {cues.map((c, i) => (
      <Sequence key={i} from={Math.round(c.at * FPS)} name={`sfx-${c.file.split('/')[1]}`}>
        <Audio src={staticFile(c.file)} volume={c.vol} playbackRate={c.rate ?? 1} />
      </Sequence>
    ))}
  </>
);

export const CUES = cues;
