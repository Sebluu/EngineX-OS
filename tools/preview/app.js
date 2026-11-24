'use strict';
const screen = document.getElementById('screen'), image = document.getElementById('frame');
let frame = null, lastMove = 0;
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
  post('/api/input', {kind:'pointer', action, x, y, button:action==='move'?0:[1,4,2][e.button]||0, buttons:e.buttons, mods:mods(e)}).catch(()=>{});
}
screen.addEventListener('pointerdown', e => {e.preventDefault();screen.focus();screen.setPointerCapture(e.pointerId);pointer(e,'down');});
screen.addEventListener('pointerup', e => {e.preventDefault();pointer(e,'up');});
screen.addEventListener('pointermove', e => {if(performance.now()-lastMove>30){lastMove=performance.now();pointer(e,'move');}});
screen.addEventListener('contextmenu', e=>e.preventDefault());
const keys={Backspace:0x01000003,Tab:0x01000001,Enter:0x01000004,Escape:0x01000000,Delete:0x01000007,Home:0x01000010,End:0x01000011,ArrowLeft:0x01000012,ArrowUp:0x01000013,ArrowRight:0x01000014,ArrowDown:0x01000015,PageUp:0x01000016,PageDown:0x01000017,Shift:0x01000020,Control:0x01000021,Meta:0x01000022,Alt:0x01000023};
function keyboard(e,action){
  if((e.ctrlKey||e.metaKey)&&['l','r','w','t'].includes(e.key.toLowerCase()))return;
  const chars=Array.from(e.key), text=chars.length===1?e.key.codePointAt(0):0;
  const key=keys[e.key]||(chars.length===1?e.key.toUpperCase().codePointAt(0):0);
  if(!key)return;
  e.preventDefault();post('/api/input',{kind:'key',action,key,text,mods:mods(e)}).catch(()=>{});
}
screen.addEventListener('keydown',e=>keyboard(e,'down'));
screen.addEventListener('keyup',e=>keyboard(e,'up'));
function save(blob,name){const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
document.getElementById('feedback').onclick=async()=>{try{const report=await post('/api/feedback',{note:document.getElementById('note').value});save(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}),'enginex-feedback.json');}catch(e){document.getElementById('notice').textContent=e.message;}};
document.getElementById('picture').onclick=async()=>{const response=await fetch('/frame.png');if(response.ok)save(await response.blob(),'enginex-preview.png');};
document.getElementById('full').onclick=()=>screen.requestFullscreen();
document.getElementById('restart').onclick=async()=>{await post('/api/restart',{});document.getElementById('status').textContent='Engine startet neu …';};
async function poll(){try{const result=await(await fetch('/api/status')).json();if(result.frame&&result.frame.width){frame=result.frame;image.src='/frame.png?frame='+frame.frame+'&t='+Date.now();document.getElementById('status').textContent='Lokale Vorschau · '+frame.width+' × '+frame.height;document.getElementById('notice').textContent='Klicke ins Bild, um Maus und Tastatur an Engine zu senden.';}}catch(e){document.getElementById('status').textContent='Verbindung zur lokalen Vorschau wird aufgebaut …';}setTimeout(poll,800);}
poll();
