// Execute real UI JS against only the IDs actually present in the HTML.
// No browser, camera, GUI or network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[2],'utf8');
const source=html.match(/<script>([\s\S]*?)<\/script>/)[1];
assert(!html.includes('staff-hand-draw'));
assert(!html.includes('スタッフと遊ぶ'));
assert(html.includes('マイクラ風へ切り替え'));
assert(html.includes('aria-label="通常モードのシーン"'));
assert(html.indexOf('id="staff-panel"')<html.indexOf('id="current-scene"'));
function element(){return {disabled:false,textContent:'',value:'100',checked:true,children:[],style:{},dataset:{},
  classList:{values:new Set(),toggle(n,v){if(v)this.values.add(n);else this.values.delete(n)}},
  addEventListener(){},checkValidity(){return true},replaceChildren(){this.children=[]},append(v){this.children.push(v)}}}
const nodes=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],element()]));
const context=vm.createContext({document:{getElementById:id=>nodes.get(id)||null,createElement:element},
  location:{hash:'#token=test'},URLSearchParams,setTimeout(){},fetch:()=>new Promise(()=>{}),confirm:()=>true});
vm.runInContext(source,context);
const normal={scenes:['living_mosaic_acer.py','modern_otedama_acer.py','earth_acer.py'],
  current:'modern_otedama_acer.py',next:'earth_acer.py',mode_revision:17,busy:false,safe:false,covered:false,
  staff:{mode:'normal',scenes:[{id:'minecraft',label:'マイクラ風'}]}};
function render(s){context.fixture=s;vm.runInContext('connected=true;sending=false;renderScenes(fixture)',context)}
render(normal);
assert.equal(nodes.get('current-scene').textContent,'現在 · Otedama');
assert.equal(nodes.get('scene-list').children.filter(b=>b.textContent==='Otedama').length,1);
assert.equal(nodes.get('staff-minecraft').disabled,false);
assert.equal(nodes.get('staff-return').disabled,true);
assert.equal(nodes.get('next').disabled,false);assert.equal(nodes.get('back').disabled,false);
let cases=7;
for(const mode of ['entering','active','blocked','recovery_failed','returning','return_reveal']){
  render({...normal,staff:{mode,label:'マイクラ風',return_scene:'modern_otedama_acer.py'}});
  assert.equal(nodes.get('next').disabled,true);assert.equal(nodes.get('back').disabled,true);
  assert.equal(nodes.get('staff-minecraft').disabled,true);
  assert.equal(nodes.get('current-scene').textContent,'復帰先 · Otedama');
  assert.equal(nodes.get('staff-return').disabled,['returning','return_reveal'].includes(mode));
  cases++;
}
render({...normal,staff:{mode:'entering',return_requested:true}});
assert.equal(nodes.get('staff-return').disabled,true);
assert(nodes.get('staff-return').textContent.includes('予約済み'));cases++;
const requests=[];
context.fetch=async(url,init)=>{requests.push({url,body:JSON.parse(init.body),headers:init.headers});return {ok:true,json:async()=>({})}};
(async()=>{
  render(normal);await nodes.get('staff-minecraft').onclick();
  assert.deepEqual(requests.at(-1).body,{action:'staff_start',scene:'minecraft',revision:17});cases++;
  render({...normal,staff:{mode:'active',label:'マイクラ風',return_scene:normal.current}});
  await nodes.get('staff-return').onclick();
  assert.deepEqual(requests.at(-1).body,{action:'staff_return',revision:17});cases++;
  render(normal);const otedama=nodes.get('scene-list').children.find(b=>b.textContent==='Otedama');
  await otedama.onclick();assert.deepEqual(requests.at(-1).body,{action:'select',scene:normal.current,revision:17});cases++;
  await nodes.get('next').onclick();assert.deepEqual(requests.at(-1).body,{action:'next',revision:17});cases++;
  await nodes.get('back').onclick();assert.deepEqual(requests.at(-1).body,{action:'back',revision:17});cases++;
  assert(requests.every(r=>r.url==='/api/action'&&r.headers.Authorization==='Bearer test'));
  const result={cases,passed:true,browser_opened:false,camera_opened:false,network_used:false};
  if(process.argv[3])fs.writeFileSync(process.argv[3],JSON.stringify(result,null,2));console.log(JSON.stringify(result));
})().catch(error=>{console.error(error);process.exitCode=1});
