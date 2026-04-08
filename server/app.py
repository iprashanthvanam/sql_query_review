"""
SQL Query Review Environment — FastAPI Server
Full OpenEnv spec: /health /reset /step /state /schema /metadata /docs /ws /web
"""
import os, sys, json

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from sql_query_review_environment import SQLQueryReviewEnvironment, TASKS
from models import SQLReviewAction

TASK_NAME = os.getenv("SQL_REVIEW_TASK", "easy")
PORT = int(os.getenv("PORT", "7860"))

_http_env = SQLQueryReviewEnvironment(task_name=TASK_NAME)

# ── Pydantic request models ───────────────────────────────────────────────────

class ActionPayload(BaseModel):
    issues: List[str] = []
    severity: str = "low"
    fixed_query: Optional[str] = None
    explanation: str = ""

class StepRequest(BaseModel):
    action: ActionPayload
    timeout_s: int = 30

class ResetRequest(BaseModel):
    seed: Optional[int] = None
    episode_id: Optional[str] = None
    task_name: Optional[str] = None

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OpenEnv Environment HTTP API",
    version="1.0.0",
    description=(
        "SQL Query Review OpenEnv environment.\n\n"
        "**Workflow:** `POST /reset` → `POST /step` (or `/ws` WebSocket)\n\n"
        "**Tasks:** `easy` | `medium` | `hard` via `SQL_REVIEW_TASK` env var."
    ),
)

def _obs_dict(obs) -> dict:
    return {"feedback": obs.feedback, "task_name": obs.task_name,
            "sql_query": obs.sql_query, "db_schema": obs.db_schema,
            "issues_found": obs.issues_found, "step": obs.step,
            "done": obs.done, "reward": obs.reward}

def _state_dict(s) -> dict:
    return {"episode_id": s.episode_id, "task_name": s.task_name,
            "sql_query": s.sql_query, "db_schema": s.db_schema,
            "expected_issues": s.expected_issues, "expected_severity": s.expected_severity,
            "correct_fixed_query": s.correct_fixed_query,
            "step_count": s.step_count, "total_reward": s.total_reward,
            "issues_found": s.issues_found}

def _make_action(d: dict) -> SQLReviewAction:
    return SQLReviewAction(issues=d.get("issues", []), severity=d.get("severity", "low"),
                           fixed_query=d.get("fixed_query"), explanation=d.get("explanation", ""))

# ── HTTP endpoints ────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}

@app.post("/reset", tags=["Environment Control"])
def reset(req: ResetRequest = ResetRequest()):
    if req.task_name and req.task_name in ("easy", "medium", "hard"):
        _http_env._task_name = req.task_name
    obs = _http_env.reset()
    return {"observation": _obs_dict(obs), "reward": 0.0, "done": False}

@app.post("/step", tags=["Environment Control"])
def step(req: StepRequest):
    obs = _http_env.step(_make_action(req.action.model_dump()))
    return {"observation": _obs_dict(obs), "reward": obs.reward, "done": obs.done}

@app.get("/state", tags=["State Management"])
def state():
    return _state_dict(_http_env.state)

@app.get("/schema", tags=["Schema"])
def schema():
    return {
        "action": {"type": "object", "properties": {
            "issues": {"type": "array", "items": {"type": "string"}},
            "severity": {"type": "string", "enum": ["low", "medium", "high"]},
            "fixed_query": {"type": "string", "nullable": True},
            "explanation": {"type": "string"}}},
        "observation": {"type": "object", "properties": {
            "feedback": {"type": "string"}, "task_name": {"type": "string"},
            "sql_query": {"type": "string"}, "db_schema": {"type": "string"},
            "issues_found": {"type": "integer"}, "step": {"type": "integer"},
            "done": {"type": "boolean"}, "reward": {"type": "number"}}},
        "state": {"type": "object", "properties": {
            "episode_id": {"type": "string"}, "task_name": {"type": "string"},
            "step_count": {"type": "integer"}, "total_reward": {"type": "number"}}}}

@app.get("/metadata", tags=["Environment Info"])
def metadata():
    return {"name": "sql_query_review", "version": "1.0.0",
            "description": "SQL Query Review environment — 3 tasks (easy/medium/hard)",
            "current_task": TASK_NAME, "tasks": list(TASKS.keys()),
            "max_steps_per_episode": 1, "reward_range": [0.0, 1.0]}

# ── FIX: WebSocket documentation endpoint (appears in /docs) ─────────────────
# FastAPI excludes @app.websocket() routes from OpenAPI by design.
# This GET endpoint documents the WebSocket protocol so it is visible in /docs.

@app.get(
    "/ws/info",
    tags=["WebSocket"],
    summary="WebSocket session — connect at ws://<host>/ws",
    response_model=Dict[str, Any],
)
def ws_info():
    """
    **WebSocket endpoint:** `ws://<host>/ws` (or `wss://` over HTTPS)

    Each connection creates one **isolated environment instance**.
    The connection stays open for the full episode.

    ---

    **Send JSON messages:**

    | type | payload | description |
    |------|---------|-------------|
    | `reset` | `{"type":"reset"}` or `{"type":"reset","task":"medium"}` | Start new episode, optionally switch task |
    | `step`  | `{"type":"step","action":{"issues":[...],"severity":"...","fixed_query":"...","explanation":"..."}}` | Submit review |
    | `state` | `{"type":"state"}` | Fetch current episode state |

    **Receive JSON messages:**

```json
    {
      "type": "observation",
      "observation": {
        "feedback": "Issues matched: 2/3 ...",
        "task_name": "easy",
        "sql_query": "SELECT * FROM users ...",
        "db_schema": "Table: users(...)",
        "issues_found": 2,
        "step": 1,
        "done": true,
        "reward": 0.833
      },
      "reward": 0.833,
      "done": true
    }
```

    **Quick test (Python):**
```python
    import asyncio, websockets, json
    async def test():
        async with websockets.connect("ws://localhost:7860/ws") as ws:
            await ws.send(json.dumps({"type": "reset"}))
            print(await ws.recv())
            await ws.send(json.dumps({"type": "step", "action": {
                "issues": ["select star", "no index"],
                "severity": "medium",
                "fixed_query": "SELECT id, name FROM users WHERE LOWER(name)='admin';",
                "explanation": "SELECT * leaks password_hash and name column is unindexed."
            }}))
            print(await ws.recv())
    asyncio.run(test())
```
    """
    return {
        "protocol": "WebSocket",
        "url": "ws://<host>/ws",
        "url_tls": "wss://<host>/ws",
        "description": "Persistent session — one isolated environment per connection",
        "message_types": {
            "reset": {"type": "reset", "task": "easy | medium | hard (optional)"},
            "step":  {"type": "step",  "action": {
                "issues": ["list of issue strings"],
                "severity": "low | medium | high",
                "fixed_query": "corrected SQL (optional)",
                "explanation": "free-text explanation"
            }},
            "state": {"type": "state"},
        },
        "response_type": "observation",
        "fields": ["observation", "reward", "done"],
    }

# ── WebSocket /ws (actual handler — protocol only, not in OpenAPI) ────────────

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    env = SQLQueryReviewEnvironment(task_name=TASK_NAME)
    try:
        while True:
            data = await websocket.receive_json()
            t = data.get("type", "")
            if t == "reset":
                requested_task = data.get("task", TASK_NAME)
                if requested_task in ("easy", "medium", "hard"):
                    env._task_name = requested_task
                obs = env.reset()
                await websocket.send_json({"type": "observation",
                    "observation": _obs_dict(obs), "reward": 0.0, "done": False})
            elif t == "step":
                obs = env.step(_make_action(data.get("action", {})))
                await websocket.send_json({"type": "observation",
                    "observation": _obs_dict(obs), "reward": obs.reward, "done": obs.done})
            elif t == "state":
                await websocket.send_json({"type": "state", "state": _state_dict(env.state)})
            else:
                await websocket.send_json({"type": "error",
                    "message": f"Unknown type '{t}'. Use: reset, step, state"})
    except WebSocketDisconnect:
        pass

# ── Web UI /web ───────────────────────────────────────────────────────────────

@app.get("/web", response_class=HTMLResponse, tags=["Web UI"])
def web_ui():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SQL Query Review — OpenEnv</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e0e0e0;min-height:100vh}
header{background:#1a1d2e;padding:14px 24px;border-bottom:1px solid #2d3748;display:flex;align-items:center;gap:10px}
header h1{font-size:17px;font-weight:600;color:#fff}
.badge{background:#3b82f6;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px}
.dot{width:8px;height:8px;border-radius:50%;background:#10b981;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.wsb{font-size:11px;padding:3px 8px;border-radius:4px;margin-left:auto}
.wsc{background:#0d2a1a;color:#6ee7b7}.wsd{background:#2a0d0d;color:#fca5a5}
.wrap{max-width:860px;margin:0 auto;padding:20px}
.card{background:#1a1d2e;border:1px solid #2d3748;border-radius:8px;padding:18px;margin-bottom:14px}
.card h2{font-size:12px;font-weight:600;color:#a0aec0;text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px}
pre{background:#0d1117;border:1px solid #2d3748;border-radius:6px;padding:10px;font-size:12px;white-space:pre-wrap;line-height:1.5}
.sql{color:#79c0ff}.sch{color:#98c379}
label{display:block;font-size:12px;color:#a0aec0;margin-bottom:5px}
input,textarea,select{width:100%;background:#0d1117;border:1px solid #2d3748;border-radius:6px;color:#e0e0e0;padding:7px 10px;font-size:12px;font-family:inherit;outline:none}
input:focus,textarea:focus,select:focus{border-color:#3b82f6}
textarea{min-height:70px;resize:vertical}
.tags{display:flex;flex-wrap:wrap;gap:5px;background:#0d1117;border:1px solid #2d3748;border-radius:6px;padding:7px;min-height:38px}
.tag{background:#2d3748;color:#e0e0e0;padding:2px 7px;border-radius:4px;font-size:11px;display:flex;align-items:center;gap:3px}
.tag button{background:none;border:none;color:#a0aec0;cursor:pointer;font-size:13px;line-height:1}
.tags input{background:none;border:none;outline:none;color:#e0e0e0;font-size:12px;flex:1;min-width:100px;padding:2px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.btns{display:flex;gap:8px;margin-top:14px}
.btn{padding:8px 16px;border:none;border-radius:6px;cursor:pointer;font-size:12px;font-weight:500}
.btn:hover{opacity:.85}
.bp{background:#3b82f6;color:#fff}.bs{background:#10b981;color:#fff}.bg{background:#2d3748;color:#e0e0e0}
.fb{padding:10px 12px;border-radius:6px;font-size:12px;line-height:1.6;border-left:3px solid;margin-top:10px}
.fs{background:#0d2a1a;border-color:#10b981;color:#6ee7b7}
.fi{background:#0d1a2e;border-color:#3b82f6;color:#93c5fd}
.fw{background:#2a1a0d;border-color:#f59e0b;color:#fcd34d}
.rbar{height:7px;background:#2d3748;border-radius:4px;overflow:hidden;margin-top:8px}
.rfill{height:100%;background:linear-gradient(90deg,#3b82f6,#10b981);border-radius:4px;transition:width .4s}
.rlabel{font-size:11px;color:#a0aec0;margin-top:4px}
.log{font-family:monospace;font-size:10px;color:#6b7280;max-height:60px;overflow-y:auto;background:#0d1117;padding:6px;border-radius:4px;margin-top:8px}
.hidden{display:none}
</style>
</head>
<body>
<header>
  <span class="dot"></span>
  <h1>SQL Query Review</h1>
  <span class="badge">OpenEnv</span>
  
</header>
<div class="wrap">
<div class="card">
  <h2>Setup</h2>
  <div class="g2">
    <div><label>Task</label>
      <select id="task">
        <option value="easy">easy — SELECT * / unindexed string match</option>
        <option value="medium">medium — implicit join / GROUP BY bug</option>
        <option value="hard">hard — N+1 correlated subqueries</option>
      </select></div>
    <div><label>Mode</label>
      <select id="mode">
        <option value="ws">WebSocket /ws (persistent)</option>
        <option value="http">HTTP /reset + /step (stateless)</option>
      </select></div>
  </div>
  <div class="btns">
    <button class="btn bp" onclick="doReset()">Reset Episode</button>
    <a href="/docs" target="_blank"><button class="btn bg" type="button">API Docs ↗</button></a>
  </div>
</div>
<div class="card hidden" id="qcard">
  <h2>SQL Query to Review</h2>
  <pre class="sql" id="sql"></pre>
  <br><h2>Database Schema</h2>
  <pre class="sch" id="sch"></pre>
</div>
<div class="card hidden" id="acard">
  <h2>Submit Review</h2>
  <label>Issues Found <small style="color:#6b7280">(press Enter after each)</small></label>
  <div class="tags" id="tagbox">
    <input id="taginput" placeholder="e.g. select star — Enter to add" onkeydown="tagkey(event)">
  </div>
  <br>
  <div class="g2">
    <div><label>Severity</label>
      <select id="sev"><option>low</option><option selected>medium</option><option>high</option></select></div>
    <div><label>Fixed Query</label>
      <input id="fix" placeholder="SELECT id, name FROM users ..."></div>
  </div>
  <br>
  <label>Explanation</label>
  <textarea id="expl" placeholder="Explain each issue and its impact..."></textarea>
  <div class="btns">
    <button class="btn bs" onclick="doStep()">Submit Review</button>
    <button class="btn bg" onclick="clearForm()">Clear</button>
  </div>
</div>
<div class="card hidden" id="fcard">
  <h2>Grader Feedback</h2>
  <div id="ftext" class="fb fi"></div>
  <div class="rbar"><div class="rfill" id="rbar" style="width:0"></div></div>
  <div class="rlabel" id="rlabel">Reward: —</div>
  <div class="log" id="log"></div>
</div>
</div>
<script>
let ws=null,issues=[],_wsQ=[];
function setWS(on){const b=document.getElementById('wsb');b.textContent=on?'WS: connected':'WS: off';b.className='wsb '+(on?'wsc':'wsd');}
function connectWS(){
  return new Promise((resolve,reject)=>{
    if(ws&&ws.readyState===WebSocket.OPEN){resolve(ws);return;}
    if(ws&&ws.readyState===WebSocket.CONNECTING){_wsQ.push({resolve,reject});return;}
    const proto=location.protocol==='https:'?'wss':'ws';
    ws=new WebSocket(proto+'://'+location.host+'/ws');
    _wsQ=[{resolve,reject}];
    ws.onopen=()=>{setWS(true);addLog('WS connected');_wsQ.forEach(r=>r.resolve(ws));_wsQ=[];};
    ws.onclose=()=>{setWS(false);_wsQ.forEach(r=>r.reject('closed'));_wsQ=[];ws=null;};
    ws.onerror=()=>{addLog('WS error');setWS(false);_wsQ.forEach(r=>r.reject('error'));_wsQ=[];};
    ws.onmessage=e=>{
      try{const m=JSON.parse(e.data);
        if(m.type==='observation')handleObs(m.observation,m.reward,m.done);
        else if(m.type==='error')addLog('Server: '+m.message);
        else if(m.type==='state')addLog('State: '+JSON.stringify(m.state).slice(0,60));
      }catch(ex){addLog('Parse err: '+ex);}
    };
  });
}
async function doReset(){
  clearFb();const task=id('task').value;addLog('Resetting task='+task);
  if(id('mode').value==='ws'){
    try{await connectWS();ws.send(JSON.stringify({type:'reset',task:task}));}
    catch(e){addLog('WS unavailable, using HTTP fallback');await httpReset(task);}
  } else {if(ws&&ws.readyState===WebSocket.OPEN){ws.close();}await httpReset(task);}
}
async function httpReset(task){
  try{const r=await fetch('/reset',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({task_name:task||id('task').value})});
  const d=await r.json();handleObs(d.observation,0,false);}catch(e){addLog('Error: '+e);}
}
async function doStep(){
  const a={issues:[...issues],severity:id('sev').value,fixed_query:id('fix').value||null,explanation:id('expl').value};
  addLog('Step issues='+issues.length+' sev='+a.severity);
  if(id('mode').value==='ws'&&ws&&ws.readyState===1){ws.send(JSON.stringify({type:'step',action:a}));}
  else{try{const r=await fetch('/step',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action:a,timeout_s:30})});
  const d=await r.json();handleObs(d.observation,d.reward,d.done);}catch(e){addLog('Error: '+e);}}
}
function handleObs(obs,reward,done){
  if(!obs)return;
  id('sql').textContent=obs.sql_query||'';id('sch').textContent=obs.db_schema||'';
  show('qcard');show('acard');show('fcard');
  if(obs.feedback){
    const fb=id('ftext');fb.textContent=obs.feedback;
    fb.className='fb '+(reward>0.6?'fs':reward>0.3?'fw':'fi');
    const p=Math.round((reward||0)*100);
    id('rbar').style.width=p+'%';
    id('rlabel').textContent='Reward: '+(reward||0).toFixed(3)+' / 1.000'+(done?' ✓ done':'');
    addLog('reward='+(reward||0).toFixed(3)+' done='+done);
  } else {
    id('ftext').textContent='Fill in your review above and click Submit Review.';
    id('ftext').className='fb fi';addLog('Reset OK. Task: '+(obs.task_name||'?'));
  }
}
function tagkey(e){if(e.key==='Enter'){e.preventDefault();const v=e.target.value.trim();if(v){addTag(v);e.target.value=''}}}
function addTag(v){issues.push(v);const c=id('tagbox'),t=document.createElement('span');
  t.className='tag';t.innerHTML=v+'<button onclick="rmTag(this,\''+v.replace(/'/g,"\\'")+'\')">\xd7</button>';
  c.insertBefore(t,id('taginput'));}
function rmTag(b,v){issues=issues.filter(i=>i!==v);b.parentElement.remove();}
function clearForm(){issues=[];document.querySelectorAll('.tag').forEach(t=>t.remove());id('fix').value='';id('expl').value='';}
function clearFb(){id('ftext').textContent='';id('rbar').style.width='0';id('rlabel').textContent='Reward: —';}
function show(i){id(i).classList.remove('hidden');}
function addLog(m){const b=id('log');b.textContent+=new Date().toLocaleTimeString()+' '+m+'\n';b.scrollTop=b.scrollHeight;}
function id(i){return document.getElementById(i);}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)

def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()