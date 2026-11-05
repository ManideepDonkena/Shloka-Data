/* Chant feedback: how closely a learner's recording follows the reference chant of the same part.
   Pure functions (works in the browser and in node). No server, no model download.

   What it measures: the SOUND SHAPE (MFCC, speaker-normalised) and the RHYTHM of the recording, lined up with the
   reference by dynamic time warping. It does NOT check phonemes the way a trained speech model would, so treat it as a
   practice aid: "did you chant this part, at a steady pace, hitting each word?"                                       */
(function(root){
const SR=16000,WIN=400,HOP=160,NFFT=512,NMEL=26,NCEP=13;

function resample(x,from){if(from===SR)return x;const r=from/SR,n=Math.floor(x.length/r),o=new Float32Array(n);
  for(let i=0;i<n;i++){const p=i*r,j=p|0,f=p-j;o[i]=x[j]*(1-f)+(x[j+1]??x[j])*f}return o}

const hann=new Float32Array(WIN).map((_,i)=>0.5-0.5*Math.cos(2*Math.PI*i/(WIN-1)));
const mel=h=>2595*Math.log10(1+h/700),imel=m=>700*(10**(m/2595)-1);
const FB=(()=>{const lo=mel(80),hi=mel(7600),pts=[];for(let i=0;i<NMEL+2;i++)pts.push(imel(lo+(hi-lo)*i/(NMEL+1)));
  const bins=pts.map(f=>Math.floor((NFFT+1)*f/SR)),fb=[];
  for(let m=1;m<=NMEL;m++){const row=new Float32Array(NFFT/2+1);
    for(let k=bins[m-1];k<bins[m];k++)row[k]=(k-bins[m-1])/Math.max(1,bins[m]-bins[m-1]);
    for(let k=bins[m];k<bins[m+1];k++)row[k]=(bins[m+1]-k)/Math.max(1,bins[m+1]-bins[m]);fb.push(row)}return fb})();
const DCT=(()=>{const d=[];for(let c=1;c<=NCEP;c++){const r=new Float32Array(NMEL);for(let m=0;m<NMEL;m++)r[m]=Math.cos(Math.PI*c*(m+0.5)/NMEL);d.push(r)}return d})();

function fft(re,im){const n=re.length;
  for(let i=1,j=0;i<n;i++){let b=n>>1;for(;j&b;b>>=1)j^=b;j^=b;if(i<j){[re[i],re[j]]=[re[j],re[i]];[im[i],im[j]]=[im[j],im[i]]}}
  for(let len=2;len<=n;len<<=1){const a=-2*Math.PI/len,wr=Math.cos(a),wi=Math.sin(a);
    for(let i=0;i<n;i+=len){let cr=1,ci=0;for(let k=0;k<len/2;k++){const u=i+k,v=i+k+len/2,
      xr=re[v]*cr-im[v]*ci,xi=re[v]*ci+im[v]*cr;re[v]=re[u]-xr;im[v]=im[u]-xi;re[u]+=xr;im[u]+=xi;const t=cr*wr-ci*wi;ci=cr*wi+ci*wr;cr=t}}}}

/* x: Float32Array at sample rate sr -> {mf:[frames][NCEP] (mean/var normalised), en:[frames] log energy} */
function features(x,sr){x=resample(x,sr);const n=Math.max(0,1+Math.floor((x.length-WIN)/HOP)),mf=[],en=[];
  const re=new Float32Array(NFFT),im=new Float32Array(NFFT);
  for(let f=0;f<n;f++){re.fill(0);im.fill(0);let e=0;for(let i=0;i<WIN;i++){const p=i?x[f*HOP+i]-0.97*x[f*HOP+i-1]:x[f*HOP+i];re[i]=p*hann[i];e+=x[f*HOP+i]**2}
    fft(re,im);const pw=new Float32Array(NFFT/2+1);for(let k=0;k<pw.length;k++)pw[k]=re[k]*re[k]+im[k]*im[k];
    const lm=FB.map(r=>{let s=0;for(let k=0;k<r.length;k++)s+=r[k]*pw[k];return Math.log(s+1e-9)});
    mf.push(DCT.map(r=>{let s=0;for(let m=0;m<NMEL;m++)s+=r[m]*lm[m];return s}));en.push(Math.log(e/WIN+1e-10))}
  /* per-recording mean/variance normalisation removes most of the voice/microphone difference */
  for(let c=0;c<NCEP;c++){let m=0;for(const v of mf)m+=v[c];m/=Math.max(1,mf.length);let s=0;for(const v of mf)s+=(v[c]-m)**2;s=Math.sqrt(s/Math.max(1,mf.length))||1;for(const v of mf)v[c]=(v[c]-m)/s}
  return{mf,en}}

/* drop leading/trailing silence: speech = frames within 30 dB of the loudest (smoothed) */
function trim(F){const en=F.en.map((_,i)=>{let s=0,c=0;for(let k=-3;k<=3;k++)if(F.en[i+k]!==undefined){s+=F.en[i+k];c++}return s/c});
  const mx=Math.max(...en),th=mx-3.0*Math.LN10*1.0; // 30 dB in natural-log power ≈ 6.9; use 3*ln10
  let a=0,b=en.length-1;while(a<b&&en[a]<th)a++;while(b>a&&en[b]<th)b--;
  return{mf:F.mf.slice(a,b+1),en:F.en.slice(a,b+1),off:a}}

const dist=(a,b)=>{let s=0;for(let i=0;i<NCEP;i++){const d=a[i]-b[i];s+=d*d}return Math.sqrt(s/NCEP)};

/* DTW with a Sakoe-Chiba band; returns {cost (mean along path), path:[[i,j]...]} */
function dtw(R,S,band=0.35){const n=R.length,m=S.length;if(!n||!m)return{cost:Infinity,path:[]};
  const w=Math.max(Math.abs(n-m),Math.round(Math.max(n,m)*band)),INF=1e9;
  const D=Array.from({length:n+1},()=>new Float32Array(m+1).fill(INF)),P=Array.from({length:n+1},()=>new Uint8Array(m+1));D[0][0]=0;
  for(let i=1;i<=n;i++){const c=i*m/n,j0=Math.max(1,Math.floor(c-w)),j1=Math.min(m,Math.ceil(c+w));
    for(let j=j0;j<=j1;j++){const d=dist(R[i-1],S[j-1]),a=D[i-1][j-1],b=D[i-1][j],c2=D[i][j-1];
      let best=a,p=0;if(b+0.0<best){best=b;p=1}if(c2<best){best=c2;p=2}D[i][j]=d+best;P[i][j]=p}}
  const path=[];let i=n,j=m;while(i>0&&j>0){path.push([i-1,j-1]);const p=P[i][j];if(p===0){i--;j--}else if(p===1)i--;else j--}
  path.reverse();return{cost:D[n][m]/path.length,path}}

const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));

/* ref: {x:Float32Array, sr, words:[{start,end,token}] relative to x start (seconds)}   me: {x, sr}
   others: optional [{x,sr}] other parts of the verse, used to calibrate "what a wrong part costs".               */
function compare(ref,me,others){
  const R0=features(ref.x,ref.sr),R=trim(R0),S0=features(me.x,me.sr),S=trim(S0);
  if(S.mf.length<8||R.mf.length<4)return{ok:false,reason:'too-quiet',message:'I could not hear you. Check the microphone and chant a little louder.'};
  const fr=HOP/SR,refDur=R.mf.length*fr,meDur=S.mf.length*fr,ratio=meDur/refDur;
  const {cost,path}=dtw(R.mf,S.mf);
  /* how much better the target fits than a different part would: 1 = clearly this part, 0 = no better than another */
  let base=null;if(others&&others.length){const cs=others.map(o=>{const O=trim(features(o.x,o.sr));return dtw(O.mf,S.mf).cost}).filter(isFinite);if(cs.length)base=cs.reduce((a,b)=>a+b,0)/cs.length}
  const ref0=1.45;                                   // typical cost between two different chants after normalisation
  const against=base||ref0,sound=clamp((against-cost)/(against-0.55*against)*1,0,1);
  /* pace: full marks within ±15 %, none beyond ±60 % */
  const dev=Math.abs(Math.log(ratio)),pace=clamp(1-(dev-Math.log(1.15))/(Math.log(1.6)-Math.log(1.15)),0,1);
  /* per word: local cost along the path inside the word, and how long the learner took vs the pace overall */
  const words=[];
  if(ref.words){const byRef=new Map();for(const [i,j] of path){(byRef.get(i)||byRef.set(i,[]).get(i)).push(j)}
    const costs=[];
    ref.words.forEach((w,wi)=>{const a=Math.max(0,Math.round(w.start/fr)-R.off),b=Math.min(R.mf.length-1,Math.round(w.end/fr)-R.off);if(b<a)return;
      let c=0,k=0,js=[];for(let i=a;i<=b;i++){for(const j of byRef.get(i)||[]){c+=dist(R.mf[i],S.mf[j]);k++;js.push(j)}}
      if(!k)return;const jd=(Math.max(...js)-Math.min(...js)+1)*fr,rd=(b-a+1)*fr;
      costs.push(c/k);words.push({idx:wi,token:w.token,cost:c/k,rel:(jd/rd)/ratio})});
    const med=costs.slice().sort((x,y)=>x-y)[costs.length>>1]||1;
    for(const w of words){const q=clamp(1-(w.cost-med)/(med*0.9),0,1);w.score=Math.round(100*q);
      w.note=w.rel<0.6?'short — hold it longer':w.rel>1.7?'drawn out':w.score<55?'check this word':'ok'}}
  const total=Math.round(100*(0.65*sound+0.35*pace));
  const tips=[];
  if(ratio<0.85)tips.push(`You chanted faster than the reference (${Math.round(ratio*100)}% of its length) — slow down and let long vowels ring.`);
  else if(ratio>1.2)tips.push(`You were slower than the reference (${Math.round(ratio*100)}% of its length) — try a steadier, flowing pace.`);
  else tips.push('Your pace matches the reference well.');
  const bad=words.filter(w=>w.note!=='ok');if(bad.length)tips.push('Look at: '+bad.slice(0,3).map(w=>`${w.token} (${w.note})`).join(', ')+'.');
  else if(words.length)tips.push('Every word lines up with the reference.');
  if(sound<0.35)tips.push('The sound is quite different from the reference — listen once more, then chant along with it.');
  return{ok:true,score:total,sound:Math.round(100*sound),pace:Math.round(100*pace),ratio:+ratio.toFixed(2),cost:+cost.toFixed(3),words,tips}}

root.ChantFeedback={compare,features,trim,dtw,SR};
if(typeof module!=='undefined')module.exports=root.ChantFeedback;
})(typeof window!=='undefined'?window:globalThis);
