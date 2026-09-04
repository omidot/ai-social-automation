import { spawnSync } from 'node:child_process';
const FF = 'node_modules/ffmpeg-static/ffmpeg.exe';
const band = (f, ss, dur, af) => {
  const r = spawnSync(FF, ['-hide_banner','-nostats','-ss',String(ss),'-t',String(dur),'-i',f,'-af',`${af},volumedetect`,'-f','null','-'], { encoding:'utf8', maxBuffer:1<<24 });
  const m = (r.stderr||'').match(/mean_volume:\s*(-?[\d.]+)/); return m ? Number(m[1]) : -99;
};
// wosh: mid -26.9 mạnh, sub -50 yếu => (200-3k) trừ (<200Hz) sẽ TĂNG khi có wosh
const ratio = (f, t) => band(f,t,0.30,'highpass=f=200,lowpass=f=3000') - band(f,t,0.30,'lowpass=f=200');
const SHOTS = [20.9,25.8,42.9,57.1,60.8,66.8,86.6,93.8,96.2,97.2,109.2,130.3];
const avg = a => a.reduce((x,y)=>x+y,0)/a.length;
const at = SHOTS.map(t => t-0.08), ctrl = SHOTS.map(t => t+0.9);
const r10a = avg(at.map(t=>ratio('out/codex-v10.mp4',t)));
const r9a  = avg(at.map(t=>ratio('out/codex-v9.mp4',t)));
const r10c = avg(ctrl.map(t=>ratio('out/codex-v10.mp4',t)));
const r9c  = avg(ctrl.map(t=>ratio('out/codex-v9.mp4',t)));
console.log('Tỉ số (200Hz-3k) − (<200Hz) — càng cao càng có wosh\n');
console.log(`  ĐÚNG LÚC ẢNH VÀO   v10 ${r10a.toFixed(2)} | v9 ${r9a.toFixed(2)}  → chênh ${(r10a-r9a).toFixed(2)} dB`);
console.log(`  0.9s SAU (đối chứng) v10 ${r10c.toFixed(2)} | v9 ${r9c.toFixed(2)}  → chênh ${(r10c-r9c).toFixed(2)} dB`);
console.log(`\n  Chênh của chênh: ${((r10a-r9a)-(r10c-r9c)).toFixed(2)} dB  (>0 = wosh nằm đúng chỗ ảnh vào)`);
