'use strict';
// Exercise progress persistence and import/export without a browser or any network access.
const assert = require('assert');
const {Blob} = require('buffer');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');
const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'docs/server/rocketmq-host-retirement-ai-246-self-review-checklist.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const storage = new Map();

function session() {
  const nodes = new Map();
  const exports = [];
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {value:'',checked:false,disabled:true,dataset:{},listeners:{},files:[],
      addEventListener(event, callback){this.listeners[event] = callback;},
      click(){if(this.listeners.click) return this.listeners.click();}});
    return nodes.get(id);
  }
  const context = vm.createContext({
    document:{getElementById:node,querySelector:selector=>node(selector),
      createElement(){return {click(){exports.push(this);}};}},
    localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)},
    Blob, URL:{createObjectURL:blob=>{exports.push(blob);return 'blob:fixture';},revokeObjectURL(){}},
    confirm:()=>true, setTimeout:callback=>callback(), console
  });
  vm.runInContext(script, context);
  return {node, context, exports, click:id=>node(id).listeners.click(),
    change:(id,event='change')=>node(id).listeners[event]()};
}

(async()=>{
  assert(!/type="checkbox"[^>]*\bchecked\b/.test(html));
  assert(html.includes("connect-src 'none'"));
  const first = session();
  const config = vm.runInContext('config', first.context);
  const guide = fs.readFileSync(path.join(root,'docs/server/rocketmq-host-retirement-ai-246-self-review-20261111.md'));
  assert.equal(config.guide_sha256, crypto.createHash('sha256').update(guide).digest('hex'));
  assert.equal(config.task_ids.length,29);
  assert(first.node('done-P01').disabled);
  first.node('operation').value='ai246-fixture-only'; first.click('load');
  assert(!first.node('done-P01').disabled);
  first.node('done-P01').checked=true; first.change('done-P01');
  first.node('note-P01').value='fixture evidence, not a production signature'; first.change('note-P01','input');
  assert(first.node('time-P01').value.endsWith('Z'));
  assert(first.node('status').textContent.includes('1 / 29'));
  const second=session(); second.node('operation').value='ai246-fixture-only'; second.click('load');
  assert(second.node('done-P01').checked);
  assert(second.node('note-P01').value.startsWith('fixture evidence'));
  second.node('operation').value='ai246-another-fixture'; second.click('load');
  assert(!second.node('done-P01').checked);
  first.click('export');
  const exported=JSON.parse(await first.exports[0].text());
  assert.equal(exported.operation_id,'ai246-fixture-only');
  assert.equal(exported.execution_authorized,false);
  assert.equal(exported.w06_issued,false);
  second.node('import').files=[{size:100,text:async()=>JSON.stringify(exported)}];
  await second.change('import');
  assert(second.node('done-P01').checked);
  exported.execution_authorized=true;
  second.node('import').files=[{size:100,text:async()=>JSON.stringify(exported)}];
  await second.change('import');
  assert(second.node('status').textContent.startsWith('导入失败'));
  assert.equal(vm.runInContext('state.execution_authorized',second.context),false);
  console.log('PASS: 29 tasks, blank initial state, evidence fields, reload persistence, operation isolation, export/import, unauthorized-state rejection');
})().catch(error=>{console.error(error);process.exitCode=1;});
