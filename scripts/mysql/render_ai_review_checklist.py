"""Render the fillable offline checklist from the authoritative Markdown guide."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / 'docs/server/rocketmq-host-retirement-ai-246-self-review-20261111.md'
OUTPUT = GUIDE.with_name('rocketmq-host-retirement-ai-246-self-review-checklist.html')
POLICY = ROOT / 'docs/evidence/2026-11-11-ai246-self-review-policy.json'


def inline(value):
    return re.sub(r'`([^`]+)`', r'<code>\1</code>', escape(value))


def render():
    guide = GUIDE.read_text()
    groups, tasks = [], []
    for line in guide.splitlines():
        if line.startswith('## '):
            groups.append(dict(title=line[3:], tasks=[]))
        match = re.fullmatch(r'- \[ \] \*\*([A-Z0-9a-z]+) (.+?)\*\* (.+)', line)
        if match:
            task_id, title, description = match.groups()
            tasks.append(task_id)
            groups[-1]['tasks'].append((task_id, title, description))
    if len(tasks) != 29 or len(set(tasks)) != len(tasks):
        raise ValueError('unexpected checklist task set')
    rows = []
    for group in groups:
        if not group['tasks']:
            continue
        rows.append('<section><h2>' + escape(group['title']) + '</h2>')
        for task_id, title, description in group['tasks']:
            rows.append(f'''<article data-task="{task_id}">
<label class="task"><input type="checkbox" id="done-{task_id}" disabled>
<strong>{task_id} {escape(title)}</strong></label>
<p>{inline(description)}</p>
<div class="record"><label>完成 UTC<input id="time-{task_id}" placeholder="勾选时记录，可据原件修正" disabled></label>
<label>原件位置、SHA 或本人决定<textarea id="note-{task_id}" rows="2" placeholder="填写原件引用和结论；不填密码、令牌或业务正文" disabled></textarea></label></div>
</article>''')
        rows.append('</section>')
    config = dict(schema='ai246-self-review-progress/v1', policy_id='AI246-20261111-SHUJIE-SELF-REVIEW',
                  guide_sha256=sha256(guide.encode()).hexdigest(), policy_sha256=sha256(POLICY.read_bytes()).hexdigest(),
                  task_ids=tasks)
    before = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>AI #424 · 舒杰逐项操作清单</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,-apple-system,sans-serif;line-height:1.6;background:Canvas;color:CanvasText}
body{max-width:1050px;margin:0 auto;padding:24px}h1{font-size:1.7rem}h2{margin-top:32px;font-size:1.2rem}
p{overflow-wrap:anywhere}code{overflow-wrap:anywhere}input,textarea,button{font:inherit;color:inherit}
input,textarea{box-sizing:border-box;width:100%;padding:9px;background:Field;border:1px solid GrayText;border-radius:5px}
button{padding:8px 14px;background:ButtonFace;border:1px solid GrayText;border-radius:5px;cursor:pointer}
button:disabled{opacity:.5;cursor:default}.task{display:flex;align-items:flex-start;gap:10px}.task input{width:20px;height:20px;flex-shrink:0;margin-top:4px}
article{padding:20px 0;border-bottom:1px solid color-mix(in srgb,CanvasText 20%,Canvas)}article p{margin:8px 0 12px}
article[data-done="true"] strong{text-decoration:line-through}.record,.fields{display:grid;grid-template-columns:1fr 2fr;gap:12px}
label{display:block}.toolbar{display:flex;gap:12px;flex-wrap:wrap;align-items:end}#operation{min-width:260px}
header{position:sticky;top:0;background:Canvas;padding:10px 0;z-index:1;border-bottom:1px solid GrayText}
#status{margin:8px 0;font-weight:500}small{display:block}a{color:LinkText}details{margin-top:24px}.fields{margin-top:16px}
@media(max-width:650px){body{padding:12px}.record,.fields{grid-template-columns:1fr}header{position:static}h1{font-size:1.35rem}}
@media print{header{position:static}.toolbar{display:none}article{break-inside:avoid}input,textarea{border:0}}
</style></head><body>
<h1>AI #424 · 舒杰操作、自审清单</h1>
<p>舒杰（shujie）同时操作与自审。模式变更已授权；新窗口、现场证据和 W06 尚待逐项完成。发布继续冻结。初始 29 项均未勾选。</p>
<p>输入本次新操作 ID 后打开清单，每完成一部分再勾选，并填写时间、本人决定和原件引用。草稿保存在当前浏览器；请定期导出进度文件，换浏览器或清除缓存前务必导出。</p>
<p><strong>此页不会停业务、连接数据库或签发批准。勾选全部完成也不等于执行授权。</strong></p>
<header><div class="toolbar"><label>本次操作 ID<input id="operation" placeholder="ai246-YYYYMMDD-HHMM"></label>
<button id="load" type="button">打开本次清单</button><button id="export" type="button" disabled>导出进度 JSON</button>
<button id="import-button" type="button">导入进度 JSON</button><input id="import" type="file" accept="application/json,.json" hidden></div>
<p id="status" role="status" aria-live="polite">尚未打开操作；0 / 29 项。</p>
<small>仅在可信浏览器的私有本机环境填写；不输入凭据、数据库 URL、令牌或业务正文。</small></header>
<div class="fields"><label>北京时间开始<input id="window-start" placeholder="YYYY-MM-DD HH:mm" disabled></label>
<label>北京时间最晚中止<input id="window-abort" placeholder="YYYY-MM-DD HH:mm" disabled></label>
<label>北京时间结束<input id="window-end" placeholder="YYYY-MM-DD HH:mm" disabled></label>
<label>当次证据索引 SHA／签署引用<input id="evidence" placeholder="索引 SHA 和本人记录位置" disabled></label></div>
'''
    after = '''
<details><summary>恢复与停止点</summary><ul>
<li>完整 43 且原空表仍在：R0，废止批准，核对原 43 后按受审取消路线恢复。</li>
<li>43 ledger、目标缺席：保持停写，另做 F1 自审并签新前向批准。</li>
<li>完整 44：验证后使用受核 44；重开已发出或有新 44 事实，只走 44 前向修复。</li>
<li>其他 head、目标非空、保留漂移或缺原件：停止本包，保全现场，另立故障决定。</li>
<li>最晚中止到达仍未具备资格时，不开始新的变更，按现库实读收口；不强杀、不删凭证。</li>
</ul></details>
<p><a href="rocketmq-host-retirement-ai-246-self-review-20261111.md">完整文字指南、预算与本地校验命令</a> ·
<a href="rocketmq-host-retirement-ai-246-window-signoff.md">正式窗口签收标准</a></p>
<script>
'use strict';
const config = CONFIG;
const fieldIds = ['window-start','window-abort','window-end','evidence'];
let state = null;
const byId = id => document.getElementById(id);
const key = operation => config.schema + ':' + config.guide_sha256 + ':' + operation;
function validOperation(value){return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{3,95}$/.test(value);}
function empty(operation){return {schema:config.schema,policy_id:config.policy_id,guide_sha256:config.guide_sha256,
 policy_sha256:config.policy_sha256,operation_id:operation,actor:'shujie',review_mode:'owner_self_review',
 execution_authorized:false,w06_issued:false,fields:{},tasks:{},updated_at:null};}
function validateProgress(value){
 if(!value || value.schema!==config.schema || value.policy_id!==config.policy_id || value.guide_sha256!==config.guide_sha256 ||
 value.policy_sha256!==config.policy_sha256 || !validOperation(value.operation_id) || value.actor!=='shujie' ||
 value.review_mode!=='owner_self_review' || value.execution_authorized!==false || value.w06_issued!==false ||
 !value.tasks || typeof value.tasks!=='object' || Array.isArray(value.tasks) || !value.fields || typeof value.fields!=='object' || Array.isArray(value.fields)) throw Error('进度版本、操作身份或范围不匹配');
 for(const [id,item] of Object.entries(value.tasks)){
  if(!config.task_ids.includes(id) || !item || typeof item.done!=='boolean' || typeof item.time!=='string' || typeof item.note!=='string') throw Error('待办记录格式不匹配');
 }
 for(const [id,text] of Object.entries(value.fields)) if(!fieldIds.includes(id) || typeof text!=='string') throw Error('窗口字段不匹配');
 return value;
}
function save(){
 state.updated_at=new Date().toISOString();
 let message='已保存本机草稿';
 try{localStorage.setItem(key(state.operation_id),JSON.stringify(state));}catch(error){message='浏览器未能保存，请立即导出 JSON';}
 const count=config.task_ids.filter(id=>state.tasks[id]?.done).length;
 byId('status').textContent=state.operation_id+' · '+count+' / '+config.task_ids.length+' 项 · '+message+'；不代表生产授权';
}
function show(next){
 state=next;byId('operation').value=state.operation_id;
 byId('export').disabled=false;
 for(const id of fieldIds){byId(id).disabled=false;byId(id).value=state.fields[id]||'';}
 for(const id of config.task_ids){
  const row=state.tasks[id]||{done:false,time:'',note:''};
  for(const prefix of ['done','time','note']) byId(prefix+'-'+id).disabled=false;
  byId('done-'+id).checked=row.done;byId('time-'+id).value=row.time;byId('note-'+id).value=row.note;
  document.querySelector('[data-task="'+id+'"]').dataset.done=String(row.done);
 }
 save();
}
byId('load').addEventListener('click',()=>{
 try{const operation=byId('operation').value.trim();if(!validOperation(operation))throw Error('操作 ID 须为 4–96 位字母、数字、下划线或短横线');
 let raw=null;try{raw=localStorage.getItem(key(operation));}catch(error){}
 show(raw?validateProgress(JSON.parse(raw)):empty(operation));
 }catch(error){byId('status').textContent=error.message;}
});
for(const id of config.task_ids){
 for(const prefix of ['done','time','note']) byId(prefix+'-'+id).addEventListener(prefix==='done'?'change':'input',()=>{
  if(!state)return;
  const done=byId('done-'+id).checked;
  if(prefix==='done' && done && !byId('time-'+id).value)byId('time-'+id).value=new Date().toISOString();
  state.tasks[id]={done,time:byId('time-'+id).value,note:byId('note-'+id).value};
  document.querySelector('[data-task="'+id+'"]').dataset.done=String(done);save();
 });
}
for(const id of fieldIds)byId(id).addEventListener('input',()=>{if(state){state.fields[id]=byId(id).value;save();}});
byId('export').addEventListener('click',()=>{
 if(!state)return;save();const blob=new Blob([JSON.stringify(state,null,2)+'\\n'],{type:'application/json'});
 const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=state.operation_id+'-progress.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
byId('import-button').addEventListener('click',()=>byId('import').click());
byId('import').addEventListener('change',async()=>{
 try{const file=byId('import').files[0];if(!file)return;if(file.size>1048576)throw Error('进度文件超出 1 MiB');
 const next=validateProgress(JSON.parse(await file.text()));
 if(confirm('导入 '+next.operation_id+' 的进度？将替换此操作当前的本机草稿。'))show(next);
 }catch(error){byId('status').textContent='导入失败：'+error.message;}finally{byId('import').value='';}
});
</script></body></html>
'''.replace('CONFIG', json.dumps(config, ensure_ascii=False))
    OUTPUT.write_text(before + '\n'.join(rows) + after)
    return OUTPUT


if __name__ == '__main__':
    print(render())
