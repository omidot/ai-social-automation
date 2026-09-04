import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
const FF = 'node_modules/ffmpeg-static/ffmpeg.exe';

const run = (args) => {
  const r = spawnSync(FF, args, { encoding: 'utf8', maxBuffer: 1 << 24 });
  return (r.stderr || '') + (r.stdout || '');
};
const peakOf = (file) => {
  const out = run(['-hide_banner', '-nostats', '-i', file, '-af', 'volumedetect', '-f', 'null', '-']);
  const m = out.match(/max_volume:\s*(-?[\d.]+)/);
  return m ? Number(m[1]) : 0;
};

// [tên, nguồn, bắt đầu, dài, fadeIn, fadeOut]
const CUTS = [
  ['u-riser',   'src1.mp3', 0.233, 3.460, 0.05, 0.10],
  ['u-click',   'src1.mp3', 4.142, 0.640, 0.01, 0.06],
  ['u-whoosh',  'src1.mp3', 5.102, 1.450, 0.02, 0.25],
  ['u-drone',   'src2.mp3', 0.157, 6.060, 0.30, 0.60],
  ['u-impact',  'src2.mp3', 6.338, 2.550, 0.01, 0.45],
  ['u-impact2', 'src2.mp3', 9.147, 2.070, 0.01, 0.40],
];

fs.mkdirSync('public/sfx', { recursive: true });
const TARGET = -3.0; // đỉnh mục tiêu, dB

for (const [name, src, ss, dur, fi, fo] of CUTS) {
  const tmp = `ref/sfx/_${name}.wav`;
  const out = `public/sfx/${name}.mp3`;
  // cắt + fade hai đầu để không bị "cạch" ở điểm cắt
  run(['-hide_banner', '-v', 'error', '-y', '-ss', String(ss), '-t', String(dur), '-i', `ref/sfx/${src}`,
    '-af', `afade=t=in:st=0:d=${fi},afade=t=out:st=${(dur - fo).toFixed(3)}:d=${fo}`, tmp]);
  // chuẩn hóa đỉnh về cùng một mức để trộn cho đều tay
  const gain = (TARGET - peakOf(tmp)).toFixed(2);
  run(['-hide_banner', '-v', 'error', '-y', '-i', tmp, '-af', `volume=${gain}dB`, '-c:a', 'libmp3lame', '-b:a', '192k', out]);
  fs.unlinkSync(tmp);
  const kb = (fs.statSync(out).size / 1024).toFixed(0);
  console.log(`✓ ${name.padEnd(10)} ${dur.toFixed(2)}s  bù ${gain.padStart(6)} dB  ${kb.padStart(4)} KB`);
}
