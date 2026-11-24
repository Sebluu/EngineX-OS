import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source=readFileSync(new URL('./app.js',import.meta.url),'utf8');
function fixture(){
  const elements=new Map(),requests=[],waits=[];let now=0;
  for(const id of ['screen','frame','status','note','feedback','picture','notice','full','restart']){
    elements.set(id,{listeners:new Map(),textContent:'',value:'',focus(options){this.focusOptions=options;},setPointerCapture(){},
      addEventListener(name,handler,options){this.listeners.set(name,{handler,options});},
      getBoundingClientRect(){return {left:0,top:0,width:1280,height:800};}});
  }
  const context=vm.createContext({document:{getElementById:id=>elements.get(id)},performance:{now:()=>now},
    setTimeout(){},fetch:async(path,options)=>{
      if(path==='/api/status')return {json:async()=>({setup:'ready',engine:'running',frame:{width:1280,height:800,frame:1}})};
      requests.push(JSON.parse(options.body));
      if(requests.length===1)await new Promise(resolve=>waits.push(resolve));
      return {ok:true,json:async()=>({})};
    }});
  vm.runInContext(source,context);
  const emit=(name,changes={})=>{
    now+=35;
    const event={pointerId:1,pointerType:'touch',isPrimary:true,button:0,buttons:1,clientX:20,clientY:40,
      preventDefault(){this.prevented=true;},...changes};
    elements.get('screen').listeners.get(name).handler(event);return event;
  };
  return {elements,requests,emit,release:()=>waits.shift()?.()};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('a slow request keeps only the latest drag position and preserves release',async()=>{
  const f=fixture();await tick();f.emit('pointerdown');
  for(let i=0;i<200;i++)f.emit('pointermove',{clientX:100+i});
  f.emit('pointerup',{clientX:299,buttons:0});
  assert.equal(f.requests.length,1);
  f.release();await tick();await tick();
  assert.deepEqual(f.requests.map(x=>x.action),['down','move','up']);
  assert.equal(f.requests[1].x,299);
  assert.equal(f.requests[2].buttons,0);
  assert.equal(f.elements.get('screen').focusOptions.preventScroll,true);
});

test('hover and a second finger cannot add a competing gesture',async()=>{
  const f=fixture();await tick();f.emit('pointermove');assert.equal(f.requests.length,0);
  f.emit('pointerdown');
  f.emit('pointerdown',{pointerId:2,isPrimary:false});
  f.emit('pointermove',{pointerId:2,isPrimary:false});
  f.emit('pointerup',{pointerId:2,isPrimary:false,buttons:0});
  f.emit('pointerup',{buttons:0});f.release();await tick();await tick();
  assert.deepEqual(f.requests.map(x=>x.action),['down','up']);
});

test('legacy touchscreen gestures are cancelled only inside the device surface',async()=>{
  const f=fixture();await tick();
  for(const name of ['touchstart','touchmove','touchend','touchcancel']){
    const listener=f.elements.get('screen').listeners.get(name);
    assert.equal(listener.options.passive,false);
    let prevented=false;listener.handler({preventDefault(){prevented=true;}});
    assert.equal(prevented,true);
  }
});
