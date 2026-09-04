import { spawnSync } from 'node:child_process';
const FF = 'node_modules/ffmpeg-static/ffmpeg.exe';
const pcm = (file, ss, dur) => {
  const r = spawnSync(FF, ['-hide_banner','-v','error','-ss',String(ss),'-t',String(dur),'-i',file,
    '-map','0:a','-f','s16le','-ac','1','-ar','44100','-'], { maxBuffer: 1 << 28 });
  return new Int16Array(r.stdout.buffer, r.stdout.byteOffset, Math.floor(r.stdout.length / 2));
};
const diffDb = (a, b) => {
  const n = Math.min(a.length, b.length); let s = 0;
  for (let i = 0; i < n; i++) { const d = (a[i] - b[i]) / 32768; s += d * d; }
  return 20 * Math.log10(Math.sqrt(s / n) + 1e-12);
};
const A = 'out/codex-v8.mp4', B = 'public/voice-full.mp3';
const show = (label, pts) => {
  console.log(label);
  for (const t of pts) console.log(`   ${String(t).padStart(7)}s   chênh lệch RMS: ${diffDb(pcm(A,t,0.4), pcm(B,t,0.4)).toFixed(1)} dB`);
};
show('A) ĐÚNG LÚC CHỮ HIỆN (phải to):', [0.22, 1.42, 3.01, 62.98, 64.12]);
show('B) CHỖ KHÔNG CÓ CHỮ (phải rất nhỏ):', [8.61, 10.48, 12.64, 105.8, 121.5]);
