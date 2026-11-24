// Disposable CI Chrome only. No user browser profile or external service.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {readFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';

const [chrome,directory]=process.argv.slice(2);
const profile=join(directory,'touch-browser');await mkdir(profile,{recursive:true});
const child=spawn(chrome,['--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage',
  '--window-size=1600,1000',
  '--disable-background-networking','--no-first-run','--remote-debugging-address=127.0.0.1',
  '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws;
try{
  let port;
  for(let i=0;i<200;i++){
    try{port=Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);if(port)break;}catch{}
    await delay(50);
  }
  assert.ok(port,'Chrome DevTools did not start');
  const tab=await(await fetch(`http://127.0.0.1:${port}/json/new?http://127.0.0.1:8765`,{method:'PUT'})).json();
  ws=new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  let serial=0;const pending=new Map();
  ws.addEventListener('message',event=>{
    const reply=JSON.parse(event.data);if(!reply.id)return;
    const entry=pending.get(reply.id);if(!entry)return;pending.delete(reply.id);
    if(reply.error)entry.reject(new Error(JSON.stringify(reply.error)));else entry.resolve(reply.result);
  });
  const command=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{
    const result=await command('Runtime.evaluate',{expression,returnByValue:true});
    if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await command('Emulation.setDeviceMetricsOverride',{width:1600,height:1000,deviceScaleFactor:1,mobile:false});
  await command('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1});
  let loaded=false;
  for(let i=0;i<200;i++){
    loaded=await evaluate('Boolean(document.getElementById("frame")?.naturalWidth && document.getElementById("status").textContent.includes("Lokale Vorschau"))');
    if(loaded)break;await delay(50);
  }
  assert.ok(loaded,'The preview image did not load in Chrome');
  await evaluate('document.body.style.minHeight="2200px";window.scrollTo(0,180)');
  const bounds=await evaluate('JSON.stringify((()=>{const r=document.getElementById("frame").getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,scroll:window.scrollY}})())');
  const r=JSON.parse(bounds),x=r.x+r.width*.6,y=r.y+r.height*.6;
  const touch=async(type,x,y)=>command('Input.dispatchTouchEvent',{type,touchPoints:type==='touchEnd'?[]:[{x,y,id:1,radiusX:4,radiusY:4,force:1}]});
  await touch('touchStart',x,y);
  for(let i=1;i<=5;i++){await touch('touchMove',x,y-i*20);await delay(25);}
  await touch('touchEnd');await delay(200);
  assert.ok(Math.abs(await evaluate('window.scrollY')-r.scroll)<=1,'Touch inside Engine scrolled the browser page');
  // Use the blank page below the device/feedback controls. A textarea has its
  // own touch-scrolling behavior and is not a test of surrounding page scroll.
  await evaluate('window.scrollTo(0,700)');await delay(100);
  const outsideBefore=await evaluate('window.scrollY');
  await command('Input.synthesizeScrollGesture',{x:200,y:450,yDistance:-130,speed:500,gestureSourceType:'touch'});
  await delay(200);
  const outsideAfter=await evaluate('window.scrollY');
  assert.ok(outsideAfter>outsideBefore+20,`Touch outside Engine did not scroll the blank page: ${outsideBefore} → ${outsideAfter}`);
  await evaluate('window.scrollTo(0,0)');
  const box=JSON.parse(await evaluate('JSON.stringify((()=>{const r=document.getElementById("frame").getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})())'));
  const cx=box.x+box.width*100/1280,cy=box.y+box.height*725/800;
  await touch('touchStart',cx,cy);await delay(100);await touch('touchEnd');
  let drained=false;
  for(let i=0;i<100;i++){drained=await evaluate('inputQueue.length===0&&!sending');if(drained)break;await delay(50);}
  assert.ok(drained,'Touch input was not delivered');
  console.log('PASS real Chrome touchscreen: in-frame drag stays in Engine; outside scroll works; native checkbox tapped');
}finally{
  ws?.close();child.kill('SIGTERM');
  await Promise.race([new Promise(resolve=>child.once('exit',resolve)),delay(3000)]);
  if(child.exitCode===null)child.kill('SIGKILL');
}
