/* Student account (name + private code, progress synced to the server) and chant feedback UI for learn.html.
   Loaded after learn.html's main script; uses its globals ($, MK, saveMk, AC, BUF, UN, SELI, ALLW, V, tier ...). */
/* API_BASE (defined in learn.html): in the Android app the API lives on the real server. */
const api=async(m,p0,b)=>{const p=API_BASE+p0;const h={'Content-Type':'application/json'};const c=lsGet('shlokaCode','');if(c)h['X-Student-Code']=c;
  const r=await fetch(p,{method:m,headers:h,body:b===undefined?undefined:JSON.stringify(b)});let j={};try{j=await r.json()}catch(e){}
  if(!r.ok)throw Object.assign(new Error(j.error||r.status),{status:r.status});return j};
const ST={name:lsGet('shlokaName',''),progress:{},server:true};

/* ---------- account ---------- */
let pushT=null;
function pushState(){if(!lsGet('shlokaCode',''))return;clearTimeout(pushT);
  pushT=setTimeout(()=>api('PUT','api/me/state',{state:{marks:MK,fb:on('#fbOn')}}).catch(()=>{}),800)}
const _saveMk=saveMk;saveMk=()=>{_saveMk();pushState()};
async function pull(){try{const me=await api('GET','api/me');ST.name=me.name;ST.progress=me.progress||{};lsSet('shlokaName',me.name);
    const sm=(me.state&&me.state.marks)||{};let ch=false;      // merge: a mark set on either device stays set
    for(const [k,v] of Object.entries(sm)){const m=MK[k]=MK[k]||{};if(v.star&&!m.star){m.star=true;ch=true}if(v.done&&!m.done){m.done=true;ch=true}}
    _saveMk();pushState();if(V)paintMarks()}
  catch(e){if(e.status===401){lsSet('shlokaCode','');ST.name=''}else if(e.message==='Failed to fetch'||e.status===404)ST.server=false}
  paintStudent()}
function paintStudent(){const b=$('#stBox');b.innerHTML='';const add=(t,cls)=>{const e=document.createElement(t);if(cls)e.className=cls;b.append(e);return e};
  const code=lsGet('shlokaCode','');
  if(!ST.server){add('p','note').textContent='Student accounts need the app server (they are off on this page). Marks are saved on this device only.';return}
  if(code){const n=add('div');n.innerHTML='<b></b>';n.firstChild.textContent=ST.name||'Student';
    const t=Object.values(ST.progress),att=t.reduce((a,x)=>a+x.n,0);
    add('p','note').textContent=`${att} practice attempt${att===1?'':'s'} on ${t.length} verse${t.length===1?'':'s'}. Your code: ${code}  (write it down — it signs you in on another device)`;
    const o=add('button','pill');o.textContent='Sign out';o.onclick=()=>{lsSet('shlokaCode','');lsSet('shlokaName','');ST.name='';ST.progress={};paintStudent();if(V)paintMarks()}}
  else{const i=add('input');i.placeholder='Your name';i.maxLength=40;i.setAttribute('aria-label','Your name');
    const r=add('div','row'),a=r.appendChild(document.createElement('button')),c=r.appendChild(document.createElement('input'));
    a.className='pill';a.textContent='Start as a student';c.placeholder='or enter a code';c.setAttribute('aria-label','Sign-in code');c.size=14;
    const msg=add('p','note');
    a.onclick=async()=>{try{if(c.value.trim()){lsSet('shlokaCode',c.value.trim().toUpperCase());await pull();if(!ST.name){msg.textContent='That code was not recognised.'}}
        else{if(!i.value.trim()){msg.textContent='Type your name first.';return}const s=await api('POST','api/students',{name:i.value});lsSet('shlokaCode',s.code);lsSet('shlokaName',s.name);ST.name=s.name;pushState();await pull()}}
      catch(e){msg.textContent=e.message==='Failed to fetch'?'Could not reach the server.':e.message}}}}
function paintBest(){const p=ST.progress[V&&V.id];if(p)$('#markNote').textContent+=`  ·  Chant score here: best ${p.best}, average ${p.avg} (${p.n} tr${p.n===1?'y':'ies'})`}

/* ---------- microphone (kept open only while feedback is on) ---------- */
const Rec={stream:null,
  async ensure(){if(this.stream)return true;try{this.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:false,noiseSuppression:false,autoGainControl:true}});return true}catch(e){return false}},
  release(){if(this.stream)this.stream.getTracks().forEach(t=>t.stop());this.stream=null},
  start(){if(!this.stream||!window.MediaRecorder)return null;const mr=new MediaRecorder(this.stream),ch=[];mr.ondataavailable=e=>e.data.size&&ch.push(e.data);mr.start();
    return{stop:()=>new Promise(res=>{mr.onstop=async()=>{try{const b=await AC.decodeAudioData(await new Blob(ch,{type:mr.mimeType}).arrayBuffer());res({x:b.getChannelData(0),sr:b.sampleRate})}catch(e){res(null)}};
      mr.state!=='inactive'?mr.stop():res(null)})}}};
async function fbToggle(){const b=$('#fbOn'),want=b.getAttribute('aria-pressed')!=='true';
  if(want&&!(await Rec.ensure())){$('#fbNote').textContent='Microphone blocked or unavailable — allow it in the browser to get feedback.';return}
  if(!want)Rec.release();b.setAttribute('aria-pressed',want);$('#mic').setAttribute('aria-pressed',want);lsSet('shlokaFb',want?'1':'0');$('#fbNote').textContent=want?'In "Your turn" the mic records you; use headphones so the chant does not bleed in.':'';pushState()}
$('#fbOn').onclick=fbToggle;
if(lsGet('shlokaFb','0')==='1'){$('#fbOn').setAttribute('aria-pressed','true');$('#mic').setAttribute('aria-pressed','true')}   // mic permission is asked again on the first practice

/* ---------- compare + show ---------- */
const clearFb=()=>{ALLW.forEach(({e})=>e.removeAttribute('data-fb'));$('#fb').hidden=true};
function slice(a,b){const sr=BUF.sampleRate,x=BUF.getChannelData(0);return x.slice(Math.max(0,Math.round(a*sr)),Math.round(b*sr))}
function analyse(u,clip){clearFb();const my=tok;
  if(!clip){showFb(null,'I could not record that. Check the microphone.');return}
  setTimeout(()=>{if(my!==tok&&!RUN)return;
    const sr=BUF.sampleRate,s0=u.span.start-0.05,ws=ALLW.map((x,i)=>({x,i})).filter(({x})=>x.w.word_audio.start>=u.span.start-0.005&&x.w.word_audio.end<=u.span.end+0.005);
    const ref={x:slice(s0,u.span.end+0.1),sr,words:ws.map(({x})=>({token:x.w.token,start:x.w.word_audio.start-s0,end:x.w.word_audio.end-s0}))};
    const others=UN.filter((_,i)=>i!==SELI).sort((a,b)=>Math.abs(a.span.start-u.span.start)-Math.abs(b.span.start-u.span.start)).slice(0,3)
      .map(o=>({x:slice(o.span.start-0.05,o.span.end+0.1),sr}));
    let res;try{res=ChantFeedback.compare(ref,clip,others)}catch(e){res={ok:false,message:'Could not analyse that attempt.'}}
    if(!res.ok){showFb(null,res.message);return}
    res.words.forEach(w=>{const el=ws[w.idx]&&ws[w.idx].x.e;if(el)el.dataset.fb=w.note==='ok'?'good':'check'});
    const prev=bestOf(V.id),sn=starsFor(res.score);touchDay();
    showFb(res);
    if(res.score>prev){BEST[V.id]=res.score;lsSet('shlokaBest',JSON.stringify(BEST));
      if(prev>0||res.score>=50){const t=document.createElement('div');t.textContent='New best for this verse!';t.className='fbl';$('#fbTxt').append(t)}
      if(starsFor(res.score)>starsFor(prev)){setTimeout(()=>SFX.play('star',sn),600)}}
    SFX.play(res.score>=75?'good':res.score>=50?'chime':'soft');SFX.buzz(res.score>=75?[25,40,25]:20);
    $('#vstars').textContent=starText(V.id);
    if(lsGet('shlokaCode',''))api('POST','api/attempts',{verse:V.id,unit:tier,idx:SELI,score:res.score,sound:res.sound,pace:res.pace,ratio:res.ratio,
        detail:{w:res.words.map(w=>[w.token,w.score,w.note==='ok'?0:1])}}).then(()=>pull()).catch(()=>{})},30)}
function showFb(r,msg){const b=$('#fb');b.hidden=false;
  if(!r){b.className='fb';$('#fbScore').textContent='—';$('#fbTxt').textContent=msg;return}
  b.className='fb '+(r.score>=75?'good':r.score>=50?'ok':'low');$('#fbScore').textContent=r.score;
  $('#fbTxt').innerHTML='';const l=document.createElement('div');l.textContent=`Sound ${r.sound} · Pace ${r.pace}`;l.className='fbl';$('#fbTxt').append(l);
  r.tips.slice(0,2).forEach(t=>{const d=document.createElement('div');d.textContent=t;$('#fbTxt').append(d)})}
$('#fb').onclick=()=>{if(FBHOLD){FBHOLD=false;return}clearFb()};   // while practice waits for it, a tap means 'continue'

pull();
