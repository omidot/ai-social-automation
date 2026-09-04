import { spawnSync } from 'node:child_process';
const FF = 'node_modules/ffmpeg-static/ffmpeg.exe';
const mean = (file, ss, t, af) => {
  const args = ['-hide_banner', '-nostats', '-ss', String(ss), '-t', String(t), '-i', file];
  args.push('-af', af ? `${af},volumedetect` : 'volumedetect', '-f', 'null', '-');
  const r = spawnSync(FF, args, { encoding: 'utf8', maxBuffer: 1 << 24 });
  const out = (r.stderr || '') + (r.stdout || '');
  const m = out.match(/mean_volume:\s*(-?[\d.]+)/);
  return m ? Number(m[1]) : -99;
};
const EV = [
  ['1-A', 'ref/sfx/src1.mp3', 0.233, 3.467],
  ['1-B', 'ref/sfx/src1.mp3', 4.142, 0.649],
  ['1-C', 'ref/sfx/src1.mp3', 5.102, 2.688],
  ['2-A', 'ref/sfx/src2.mp3', 0.157, 6.071],
  ['2-B', 'ref/sfx/src2.mp3', 6.338, 2.566],
  ['2-C', 'ref/sfx/src2.mp3', 9.147, 2.086],
];
console.log('nhãn   dài   sub     mid     cao     đầu→cuối   => đoán');
for (const [id, f, ss, d] of EV) {
  const sub = mean(f, ss, d, 'lowpass=f=150');
  const mid = mean(f, ss, d, 'highpass=f=150,lowpass=f=1500');
  const hi = mean(f, ss, d, 'highpass=f=4000');
  const third = d / 3;
  const a = mean(f, ss, third);
  const b = mean(f, ss + d - third, third);
  const dir = b - a;
  let guess;
  if (d < 0.9 && hi > sub + 25) guess = 'CLICK / tick ngắn, nhiều treble';
  else if (dir > 4) guess = 'RISER — năng lượng tăng dần';
  else if (sub > -20 && dir < -3) guess = 'IMPACT — sub nặng, tắt dần';
  else if (sub > -20) guess = 'BOOM / drone trầm';
  else if (mid > sub + 15) guess = 'WHOOSH — quét giữa dải, ít sub';
  else guess = 'nền / ambience';
  console.log(`${id}  ${d.toFixed(2)}s ${String(sub).padStart(7)} ${String(mid).padStart(7)} ${String(hi).padStart(7)}  ${a.toFixed(1)}→${b.toFixed(1)} (${dir > 0 ? '+' : ''}${dir.toFixed(1)})  => ${guess}`);
}
