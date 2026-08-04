// Smoke test: node domstub.js
// Catches temporal-dead-zone and missing-symbol errors that `node --check`
// cannot -- exactly the class of bug that silently killed the whole page.
// Minimal DOM/browser stub: enough to load the page script and surface
// temporal-dead-zone / missing-symbol errors that node --check cannot see.
const mkEl = (tag='div') => {
  const el = {
    tagName: (tag||'div').toUpperCase(), style:{}, dataset:{}, children:[],
    classList:{ add(){}, remove(){}, toggle(){}, contains(){return false} },
    _text:'', value:'', checked:false, hidden:false, disabled:false, title:'',
    innerHTML:'', max:0, min:0, files:[],
    get textContent(){return this._text}, set textContent(v){this._text=v},
    append(...c){this.children.push(...c)},
    appendChild(c){this.children.push(c); return c},
    addEventListener(){}, removeEventListener(){}, remove(){},
    setPointerCapture(){}, scrollIntoView(){}, click(){},
    getBoundingClientRect(){return {left:0,top:0,width:800,height:150}},
    getContext(){ return new Proxy({}, {get:()=>()=>({})}); },
    querySelector(){return mkEl()}, querySelectorAll(){return []},
    get lastElementChild(){return mkEl()},
    get clientWidth(){return 800},
  };
  return el;
};
const store = {};
global.localStorage = { getItem:k=>store[k]??null, setItem:(k,v)=>{store[k]=String(v)},
                        removeItem:k=>{delete store[k]} };
global.document = {
  createElement: mkEl,
  querySelector: () => mkEl(),
  querySelectorAll: () => [],
  addEventListener(){},
  body: Object.assign(mkEl('body'), {classList:{add(){},remove(){},toggle(){},contains(){return false}}}),
};
global.window = { devicePixelRatio:1,
                  addEventListener(){}, matchMedia:()=>({matches:false}) };
global.getComputedStyle = () => ({ getPropertyValue: () => '#000' });
global.requestAnimationFrame = () => 0;
global.cancelAnimationFrame = () => {};
global.setInterval = () => 0;
global.performance = { now: () => 0 };
global.fetch = () => Promise.resolve({ ok:false, json:()=>Promise.resolve([]),
                                       arrayBuffer:()=>Promise.resolve(new ArrayBuffer(8)) });
global.Blob = function(){}; global.URL = { createObjectURL:()=>'', revokeObjectURL(){} };
global.TextEncoder = require('util').TextEncoder;
global.btoa = s => Buffer.from(s,'binary').toString('base64');
global.AudioContext = function(){
  return { createGain:()=>({connect(){}, gain:{value:1}}),
           createBufferSource:()=>({connect(){}, start(){}, stop(){}, playbackRate:{value:1}}),
           destination:{}, currentTime:0, state:'running', resume(){},
           decodeAudioData:()=>Promise.resolve({duration:10, sampleRate:16000,
                                                getChannelData:()=>new Float32Array(160000)}) };
};
global.webkitAudioContext = global.AudioContext;
global.window.AudioContext = global.AudioContext;
global.window.webkitAudioContext = global.AudioContext;

const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
const js = html.match(/<script>([\s\S]*)<\/script>/)[1];
try {
  new Function(js)();
  console.log('LOADED OK — no top-level execution errors');
} catch (e) {
  console.log('FAILED:', e.constructor.name + ':', e.message);
  process.exit(1);
}
