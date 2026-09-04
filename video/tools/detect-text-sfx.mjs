import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
const FF = 'node_modules/ffmpeg-static/ffmpeg.exe';
const band = (file, ss, dur, af) => {
  const r = spawnSync(FF, ['-hide_banner','-nostats','-ss',String(ss),'-t',String(dur),'-i',file,'-af',`${af},volumedetect`,'-f','null','-'], { encoding:'utf8', maxBuffer:1<<24 });
  const m = ((r.stderr||'')).match(/mean_volume:\s*(-?[\d.]+)/);
  return m ? Number(m[1]) : -99;
};
// text.mp3 mạnh ở 500-4k, rất yếu ở <500Hz. Giọng thì ngược lại.
// => tỉ số (500-4k) trừ (<500Hz) sẽ TĂNG khi có tiếng này chồng lên.
const ratio = (file, t) => band(file,t,0.22,'highpass=f=500,lowpass=f=4000') - band(file,t,0.22,'lowpass=f=500');

const tl = JSON.parse(fs.readFileSync('src/timeline.json','utf8'));
const L = []; tl.cards.forEach(c=>c.lines.filter(l=>!l.hidden).forEach(l=>L.push(l.start)));
L.sort((a,b)=>a-b);
// điểm đối chứng: 0.75s sau mỗi dòng, và phải cách dòng kế tiếp >0.5s
const ctrl = [];
for (let i=0;i<L.length-1;i++){ const t=L[i]+0.75; if (L[i+1]-t>0.5) ctrl.push(t); }

const pick = (arr,n)=>arr.filter((_,i)=>i%Math.max(1,Math.floor(arr.length/n))===0).slice(0,n);
const A = pick(L.slice(2),18), B = pick(ctrl,18);
const avg = a=>a.reduce((x,y)=>x+y,0)/a.length;
const rA = A.map(t=>ratio('out/codex-v8.mp4',t-0.02));
const rB = B.map(t=>ratio('out/codex-v8.mp4',t));
const vA = A.map(t=>ratio('public/voice-full.mp3',t-0.02));
const vB = B.map(t=>ratio('public/voice-full.mp3',t));
console.log('Tỉ số (500Hz-4k) − (<500Hz), càng CAO càng có tiếng text.mp3\n');
console.log(`  video v8   — tại dòng chữ: ${avg(rA).toFixed(2)} dB   | đối chứng: ${avg(rB).toFixed(2)} dB   → chênh ${(avg(rA)-avg(rB)).toFixed(2)} dB`);
console.log(`  giọng gốc  — tại dòng chữ: ${avg(vA).toFixed(2)} dB   | đối chứng: ${avg(vB).toFixed(2)} dB   → chênh ${(avg(vA)-avg(vB)).toFixed(2)} dB`);
console.log(`\n  Chênh của chênh: ${((avg(rA)-avg(rB))-(avg(vA)-avg(vB))).toFixed(2)} dB  (>0 = có tiếng thêm vào đúng tại dòng chữ)`);
