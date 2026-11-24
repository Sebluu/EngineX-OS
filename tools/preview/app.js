'use strict';
const screen = document.getElementById('screen'), image = document.getElementById('frame');
let frame = null, lastMove = 0, heldButton = 0, activePointer = null;
let sending = false, imageLoading = false, requestedImage = '';
const inputQueue = [];
const heldKeys = new Map();
const mods = e => (e.shiftKey ? 0x02000000 : 0) | (e.ctrlKey ? 0x04000000 : 0) | (e.altKey ? 0x08000000 : 0) | (e.metaKey ? 0x10000000 : 0);
async function post(path, body) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  if (!response.ok) throw new Error('Vorschau momentan nicht erreichbar');
  return response.json();
}
function pointer(e, action) {
  if (!frame) return;
  const rect = image.getBoundingClientRect();
  const x = Math.max(0, Math.min(frame.width - 1, (e.clientX - rect.left) * frame.width / rect.width));
  const y = Math.max(0, Math.min(frame.height - 1, (e.clientY - rect.top) * frame.height / rect.height));
  const button = action==='move'?0:(heldButton||[1,4,2][e.button]||0);
  sendInput({kind:'pointer', action, x, y, button, buttons:action==='up'?0:e.buttons, mods:mods(e)});
}
function sendInput(body){
  const last=inputQueue[inputQueue.length-1];
  // Keep the most recent drag position while a request is outstanding. Never
  // discard or reorder a press, release or keyboard event.
  if(body.kind==='pointer'&&body.action==='move'&&last?.kind==='pointer'&&last.action==='move')inputQueue[inputQueue.length-1]=body;
  else inputQueue.push(body);
  flushInput();
}
async function flushInput(){
  if(sending)return;
  sending=true;
  try{while(inputQueue.length){try{await post('/api/input',inputQueue.shift());}catch{}}}
  finally{sending=false;}
}
function releasePointer(e){
  e.preventDefault();
  if(e.pointerId!==activePointer)return;
  pointer(e,'up');heldButton=0;activePointer=null;
}
screen.addEventListener('pointerdown', e => {
  e.preventDefault();
  if(activePointer!==null||e.isPrimary===false)return;
  activePointer=e.pointerId;heldButton=e.pointerType==='touch'?1:([1,4,2][e.button]||1);
  screen.focus({preventScroll:true});screen.setPointerCapture(e.pointerId);pointer(e,'down');
});
screen.addEventListener('pointerup', releasePointer);
screen.addEventListener('pointercancel', releasePointer);
screen.addEventListener('pointermove', e => {
  if(e.pointerId!==activePointer||!heldButton)return;
  e.preventDefault();
  if(performance.now()-lastMove>30){lastMove=performance.now();pointer(e,'move');}
});
// Keep touchscreen drags inside the device view, including browsers that also
// emit legacy TouchEvents. Scrolling outside this view remains available.
for(const event of ['touchstart','touchmove','touchend','touchcancel'])screen.addEventListener(event,e=>e.preventDefault(),{passive:false});
screen.addEventListener('contextmenu', e=>e.preventDefault());
const keys={Backspace:0x01000003,Tab:0x01000001,Enter:0x01000004,Escape:0x01000000,Delete:0x01000007,Home:0x01000010,End:0x01000011,ArrowLeft:0x01000012,ArrowUp:0x01000013,ArrowRight:0x01000014,ArrowDown:0x01000015,PageUp:0x01000016,PageDown:0x01000017,Shift:0x01000020,Control:0x01000021,Meta:0x01000022,Alt:0x01000023};
function keyboard(e,action){
  if((e.ctrlKey||e.metaKey)&&['l','r','w','t'].includes(e.key.toLowerCase()))return;
  const chars=Array.from(e.key), text=chars.length===1?e.key.codePointAt(0):0;
  const key=keys[e.key]||(chars.length===1?e.key.toUpperCase().codePointAt(0):0);
  if(!key)return;
  e.preventDefault();
  const body={kind:'key',action,key,text,mods:mods(e)};
  if(action==='down')heldKeys.set(key,body);else heldKeys.delete(key);
  sendInput(body);
}
screen.addEventListener('keydown',e=>keyboard(e,'down'));
screen.addEventListener('keyup',e=>keyboard(e,'up'));
screen.addEventListener('blur',()=>{for(const body of heldKeys.values())sendInput({...body,action:'up'});heldKeys.clear();});
function save(blob,name){const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
document.getElementById('feedback').onclick=async()=>{try{const report=await post('/api/feedback',{note:document.getElementById('note').value});save(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}),'enginex-feedback.json');}catch(e){document.getElementById('notice').textContent=e.message;}};
document.getElementById('picture').onclick=async()=>{const response=await fetch('/frame.png');if(response.ok)save(await response.blob(),'enginex-preview.png');};
document.getElementById('full').onclick=()=>screen.requestFullscreen();
document.getElementById('restart').onclick=async()=>{await post('/api/restart',{});document.getElementById('status').textContent='Engine startet neu …';};
image.onload=image.onerror=()=>{imageLoading=false;};
async function poll(){try{
  const result=await(await fetch('/api/status')).json();
  if(result.setup==='failed'){
    document.getElementById('status').textContent='Einrichtung fehlgeschlagen';
    document.getElementById('notice').textContent='Details stehen im VM-Protokoll console.log in deinem Testordner.';
  }else if(result.frame&&result.frame.width){
    frame=result.frame;
    const key=(frame.stream||'')+':'+frame.frame;
    if(!imageLoading&&key!==requestedImage){requestedImage=key;imageLoading=true;image.src='/frame.png?frame='+encodeURIComponent(key);}
    const age=Number.isFinite(frame.ageMs)?' · Bildalter '+(frame.ageMs/1000).toFixed(1)+' s':'';
    document.getElementById('status').textContent=result.engine==='stopped'?'Engine beendet · mit dem Neustartknopf wieder starten':'Lokale Vorschau · '+frame.width+' × '+frame.height+age;
    document.getElementById('notice').textContent='Im Bild direkt tippen und ziehen. Außerhalb des Bildes kannst du die Webseite scrollen.';
  }
}catch{document.getElementById('status').textContent='Verbindung zur lokalen Vorschau wird aufgebaut …';}
setTimeout(poll,200);}
poll();
