"""Battle viewer: turn a run directory into one self-contained HTML page (no network, no assets).

    python -m pokejev view runs/jev-ha05            # writes runs/jev-ha05/viewer.html and opens it

URL parameters (used to render video frames): ?battle=0&step=12&autoplay=0
"""
import json
import webbrowser
from pathlib import Path

from pokejev.intents import INTENTS
from pokejev.render import EFF, option_names
from pokejev.rules import rule_pick


def _option_view(o, name, probs, chosen, rule):
    f = o["facts"]
    v = {"id": o["id"], "name": name, "kind": o["kind"], "p": probs.get(o["id"]), "chosen": o["id"] == chosen,
         "rule": o["id"] == rule}
    if o["kind"] == "switch":
        v.update(hp=f["hp_pct"], matchup=f["matchup"], faster=f["faster"])
    else:
        v.update(type=f["type"], category=f["category"], status=f["is_status"], acc=round(100 * f["accuracy"]),
                 priority=f["priority"], tera=bool(f.get("terastallize")), becomes=f.get("tera_type"))
        if not f["is_status"]:
            v.update(damage=f["est_damage_pct"], ko=f["likely_ko"], eff=EFF.get(f["type_mult"], "%gx" % f["type_mult"]))
    if "exchange" in f:
        v["next_turn"] = f["exchange"]
    return v


def build_data(run_dir):
    d = Path(run_dir)
    s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    intent = INTENTS.get(s.get("intent")) if s.get("intent") else None
    battles, order = {}, []
    for line in (d / "decisions.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        req, dec = r["request"], r["decision"]
        if r["battle"] not in battles:
            battles[r["battle"]] = {"tag": r["battle"], "won": r.get("won"), "steps": []}
            order.append(r["battle"])
        names = option_names(req)
        rule = rule_pick(req)
        probs = dec.get("probs2") or dec.get("probs") or {}
        st = req["state"]
        step = {"turn": st["turn"], "state": {k: st.get(k) for k in (
            "our_species", "opp_species", "our_hp_pct", "opp_hp_pct", "our_types", "opp_types", "our_status",
            "opp_status", "our_left", "opp_left", "we_faster", "forced_switch")},
                "memory": st.get("memory"), "chosen": r["chosen_id"], "rule": rule,
                "fallback": dec.get("fallback"), "skipped": dec.get("skipped"),
                "shortlist": dec.get("shortlist"),
                "options": sorted((_option_view(o, names[o["id"]], probs, r["chosen_id"], rule) for o in req["options"]),
                                  key=lambda v: -(v["p"] or 0))}
        if intent is not None:
            applies = bool(intent["applies"](req))
            byid = {o["id"]: o for o in req["options"]}
            step["intent"] = {"applies": applies,
                              "conflict": applies and not intent["complies"](req, byid[rule]),
                              "followed": applies and bool(intent["complies"](req, byid[r["chosen_id"]]))}
        battles[r["battle"]]["steps"].append(step)
    for tag, b in battles.items():
        b.update(_replay(d / "replays", tag))
    return {"run": {k: s.get(k) for k in ("decider", "version", "intent", "battles", "wins", "model", "stub")},
            "intent_text": intent["text"] if intent else None, "battles": [battles[t] for t in order]}


def _replay(folder, tag):
    """Showdown battle log and our side (p1/p2) from poke-env's saved replay, if present."""
    files = sorted(folder.glob("* - %s.html" % tag)) if folder.exists() else []
    if not files:
        return {"log": None, "side": None}
    html = files[0].read_text(encoding="utf-8")
    start = html.find('class="battle-log-data">')
    end = html.find("</script>", start)
    log = html[start + len('class="battle-log-data">'):end].strip() if start >= 0 else None
    me = files[0].name.split(" - ")[0]
    side = None
    for line in (log or "").splitlines():
        parts = line.split("|")
        if len(parts) > 3 and parts[1] == "player" and parts[3] == me:
            side = parts[2]
    return {"log": log, "side": side}


def write(run_dir, open_browser=True):
    data = build_data(run_dir)
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    out = Path(run_dir) / "viewer.html"
    out.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(out.resolve().as_uri())
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>pokejev · viewer</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" rel="stylesheet">
<script>const DATA=__DATA__;const Q=new URLSearchParams(location.search);const BI=Math.min(+(Q.get("battle")||0),DATA.battles.length-1);
/* Showdown picks a random backdrop on every load; seed it by the battle id so a battle always looks the same. */
(function(){let h=2166136261;for(const c of DATA.battles[BI].tag)h=Math.imul(h^c.charCodeAt(0),16777619);let a=h>>>0;
Math.random=function(){a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}})();</script>
<style>
/* Game Boy palette; pixel font for labels/numbers, monospace for details. Battle screen: Pokemon Showdown's replay player. */
:root{--g0:#0f380f;--g1:#1b4a1b;--g2:#306230;--g3:#8bac0f;--g4:#9bbc0f;--g5:#e0f8d0;--bad:#e0745a;--warn:#e8d44d;
--px:"Press Start 2P",ui-monospace,monospace;--mono:ui-monospace,"Cascadia Mono",Consolas,"Noto Sans Mono",monospace;
--pop:0 0 0 4px var(--g0),6px 6px 0 4px var(--g2)}
*{box-sizing:border-box}html,body{margin:0;background-color:var(--g0);color:var(--g5);min-height:100vh;font:15px/1.55 var(--mono);
background-image:linear-gradient(rgba(155,188,15,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(155,188,15,.05) 1px,transparent 1px);background-size:16px 16px}
header.top{display:flex;align-items:center;gap:14px;padding:14px 24px;border-bottom:4px solid var(--g2);background:rgba(15,56,15,.94);position:sticky;top:0;z-index:20}
.logo{font:16px var(--px);letter-spacing:1px;color:var(--g5)}.logo b{color:var(--g4)}
.chip{padding:6px 10px;border:2px solid var(--g2);color:var(--g3);font:9px var(--px);text-transform:uppercase;white-space:nowrap}
.chip b{color:var(--g5);font-weight:400}.spacer{flex:1}
select.x,button.x{background:var(--g4);color:var(--g0);border:0;padding:9px 12px;font:10px var(--px);cursor:pointer;box-shadow:var(--pop);text-transform:uppercase}
select.x{background:var(--g2);color:var(--g5)}button.x:hover{background:var(--g5)}
.intentbar{margin:20px 28px 0;padding:12px 18px;background:var(--g1);border:4px solid var(--g4);box-shadow:6px 6px 0 var(--g2)}
.intentbar small{display:block;font:9px var(--px);color:var(--g4);letter-spacing:1px;margin-bottom:8px}
main.grid{display:grid;grid-template-columns:744px 1fr;gap:26px;padding:22px 28px 120px;align-items:start}
.device{background:#c4cfa1;border-radius:16px 16px 56px 16px;padding:22px 26px 18px;box-shadow:10px 10px 0 #0a260a;border:4px solid #8b956d}
.screenbox{background:#5c6a4a;border-radius:10px 10px 30px 10px;padding:14px 16px 16px}
.screenbox .label{font:8px var(--px);color:#cfd7b5;margin-bottom:10px;display:flex;align-items:center;gap:10px}
.screenbox .led{width:9px;height:9px;border-radius:50%;background:#e04b4b;box-shadow:0 0 8px #ff6b6b}
.lcd{width:648px;height:368px;border:4px solid var(--g0);background:#0a260a;position:relative;overflow:hidden}
.lcd .replay-wrapper{position:absolute;left:0;top:0;width:640px;height:360px;margin:0!important;max-width:none!important}
.lcd .replay-wrapper .battle-log,.lcd .replay-controls,.lcd .replay-controls-2{display:none!important}
.lcd .replay-wrapper .battle{margin:0!important;top:0!important;left:0!important}
#offline{position:absolute;inset:0;display:none;align-items:center;justify-content:center;text-align:center;padding:30px;font:10px/2 var(--px);color:var(--g3)}
.brandrow{display:flex;justify-content:space-between;align-items:center;margin-top:12px}.brand{font:15px var(--px);color:#3b3f7a;font-style:italic}.brand b{font-style:normal}
.ab{display:flex;gap:14px}.ab span{width:34px;height:34px;border-radius:50%;background:#9a2f5a;display:grid;place-items:center;font:9px var(--px);color:#c4cfa1;box-shadow:3px 3px 0 #5a1a35}
.card{background:var(--g1);border:4px solid var(--g2);padding:16px;box-shadow:6px 6px 0 #0a260a}
.below{margin-top:22px;display:grid;grid-template-columns:1fr 1fr;gap:14px}
.mon{display:flex;flex-direction:column;gap:8px;padding:12px;background:var(--g0);border:2px solid var(--g2)}
.mon .who{font:8px var(--px);color:var(--g3);letter-spacing:1px}.mon .nm{font:12px var(--px);text-transform:uppercase;color:var(--g5);line-height:1.6}
.hpx{height:12px;background:var(--g0);border:2px solid var(--g3);padding:1px}
.hpx>i{display:block;height:100%;background:repeating-linear-gradient(90deg,var(--g4) 0 7px,transparent 7px 9px)}
.hpx.mid>i{background:repeating-linear-gradient(90deg,var(--warn) 0 7px,transparent 7px 9px)}.hpx.low>i{background:repeating-linear-gradient(90deg,var(--bad) 0 7px,transparent 7px 9px)}
.row{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.meta{color:var(--g3);font-size:13px}
.ty{padding:3px 6px;font:8px var(--px);color:#0b1a0b;text-transform:uppercase;border:2px solid var(--g0)}
.stx{padding:3px 6px;font:8px var(--px);background:var(--warn);color:var(--g0);text-transform:uppercase}
.mem{grid-column:1/-1;font-size:13px;color:var(--g3)}.mem b{font:9px var(--px);color:var(--g4)}
.mem div{padding:5px 9px;border-left:4px solid var(--g2);margin-top:6px}.mem .warn{border-color:var(--warn);color:var(--warn)}
.panel h2{margin:0 0 6px;font:12px var(--px);color:var(--g4);letter-spacing:1px;display:flex;align-items:center;gap:12px}
.turnno{font:20px var(--px);color:var(--g5);margin-left:auto}
.sub{font-size:13px;color:var(--g3);margin:0 0 14px}
.opt{display:grid;grid-template-columns:1fr 170px;gap:14px;align-items:center;padding:11px 13px;background:var(--g0);border:2px solid var(--g2);margin-bottom:10px}
.opt.chosen{border:4px solid var(--g4);box-shadow:6px 6px 0 var(--g2);padding:9px 11px}
.opt .ttl{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font:10px var(--px);line-height:1.7;color:var(--g5)}
.opt .ttl .k{font:12px var(--mono);color:var(--g3)}
.tg{padding:2px 6px;font-size:12px;border:2px solid var(--g2);color:var(--g3)}
.tg.ko{background:var(--g4);border-color:var(--g4);color:var(--g0);font-weight:700}
.tg.se{color:var(--warn);border-color:var(--warn)}.tg.imm{color:var(--bad);border-color:var(--bad)}
.tg.tera{background:var(--g5);border-color:var(--g5);color:var(--g0);font-weight:700}
.tg.rule{color:var(--warn);border-color:var(--warn)}.tg.pick{background:var(--g4);border-color:var(--g4);color:var(--g0);font:8px var(--px);padding:5px 7px}
.dmg{margin-top:8px;height:10px;border:2px solid var(--g2);padding:1px}.dmg>i{display:block;height:100%;background:repeating-linear-gradient(90deg,var(--g3) 0 5px,transparent 5px 7px)}
.nt{margin-top:6px;font-size:12.5px;color:var(--g3)}
.prob .lbl{display:flex;justify-content:space-between;font:9px var(--px);color:var(--g3);margin-bottom:7px}
.prob .bar{height:18px;border:2px solid var(--g3);padding:2px;background:var(--g0)}
.prob .bar>i{display:block;height:100%;background:repeating-linear-gradient(90deg,var(--g3) 0 8px,transparent 8px 10px)}
.opt.chosen .prob .bar>i{background:repeating-linear-gradient(90deg,var(--g4) 0 8px,transparent 8px 10px)}.opt.chosen .prob .lbl{color:var(--g5)}
.verdict{padding:7px 10px;font:8px var(--px);line-height:1.6;text-transform:uppercase;display:inline-block;margin-bottom:12px}
.verdict.ok{background:var(--g4);color:var(--g0)}.verdict.no{background:var(--bad);color:var(--g0)}.verdict.na{border:2px solid var(--g2);color:var(--g3)}
footer.ctl{position:fixed;left:0;right:0;bottom:0;padding:14px 28px;background:rgba(15,56,15,.96);border-top:4px solid var(--g2);display:flex;gap:16px;align-items:center;z-index:20}
input[type=range]{flex:1;accent-color:var(--g4)}#step{font:9px var(--px)}.caption{color:var(--g5);font-size:14px;min-width:320px;text-align:right}
.res{padding:7px 10px;font:9px var(--px);text-transform:uppercase}.res.w{background:var(--g4);color:var(--g0)}.res.l{background:var(--bad);color:var(--g0)}
@media (max-width:1300px){main.grid{grid-template-columns:1fr}}
</style></head><body>
<header class="top"><div class="logo">poke<b>·</b>jev</div><div id="chips" class="row"></div><div class="spacer"></div>
<select id="battle" class="x" aria-label="Battle"></select><span id="result" class="res"></span></header>
<div id="intent" class="intentbar" hidden><small>Designer intent</small><div id="intentText"></div></div>
<main class="grid"><section>
<div class="device"><div class="screenbox"><div class="label"><span class="led"></span>DOT MATRIX WITH STEREO SOUND · POKéMON SHOWDOWN REPLAY</div>
<div class="lcd"><div class="wrapper replay-wrapper"><div class="battle"></div><div class="battle-log"></div><div class="replay-controls"></div><div class="replay-controls-2"></div>
<script>if(DATA.battles[BI].log){document.write('<script type="text/plain" class="battle-log-data">'+DATA.battles[BI].log+'</'+'script>')}</script></div>
<div id="offline">Battle screen unavailable<br>(needs internet: it uses Pokémon Showdown's replay player)<br>Jev's decisions are on the right.</div></div></div>
<div class="brandrow"><span class="brand"><b>JEV</b> BOY</span><div class="ab"><span>B</span><span>A</span></div></div></div>
<div class="below"><div id="opp" class="mon"></div><div id="ours" class="mon"></div><div id="memory" class="mem"></div></div>
</section>
<section class="card panel"><h2>Jev's decision <span class="turnno">T<span id="turn"></span></span></h2>
<p class="sub">facts computed by code · bars show Jev's probability for each option</p><span id="verdict" class="verdict" hidden></span><div id="options"></div></section></main>
<footer class="ctl"><button id="prev" class="x" title="Previous (←)">◀</button><button id="play" class="x" title="Play/pause (space)">▶ Play</button>
<button id="next" class="x" title="Next (→)">▶</button><input id="slider" type="range" min="0" value="0" aria-label="Timeline">
<span id="step" class="meta"></span><span id="caption" class="caption"></span></footer>
<script>if(DATA.battles[BI].log)document.write('<script src="https://play.pokemonshowdown.com/js/replay-embed.js"></'+'script>')</script>
<script>
const TYPE={normal:"#A8A77A",fire:"#EE8130",water:"#6390F0",electric:"#F7D02C",grass:"#7AC74C",ice:"#96D9D6",fighting:"#C22E28",
poison:"#A33EA1",ground:"#E2BF65",flying:"#A98FF3",psychic:"#F95587",bug:"#A6B91A",rock:"#B6A136",ghost:"#735797",dragon:"#6F35FC",
dark:"#705746",steel:"#B7B7CE",fairy:"#D685AD",stellar:"#7c9cff"};
const el=id=>document.getElementById(id),esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const BT=DATA.battles[BI];let S=+(Q.get("step")||0),poll=null,timer=null,ready=false;
const badge=t=>t?`<span class="ty" style="background:${TYPE[t]||"#888"}">${esc(t)}</span>`:"";
const hpBar=p=>`<div class="hpx ${p>50?"":p>20?"mid":"low"}"><i style="width:${Math.max(0,Math.min(100,p))}%"></i></div>`;
function mon(el,who,sp,hp,types,status,left,extra){el.innerHTML=`<div class="who">${who}</div><div class="row"><span class="nm">${esc(sp)}</span>${(types||[]).map(badge).join("")}${status?`<span class="stx">${esc(status)}</span>`:""}</div>${hpBar(hp)}<div class="row meta"><span>${Math.round(hp)}% HP</span><span>·</span><span>${left} left</span>${extra||""}</div>`}
function chips(){const r=DATA.run,c=[["version",r.version],["model",r.model],["wins",`${r.wins}/${r.battles}`]];if(r.intent)c.unshift(["intent",r.intent]);if(r.stub)c.push(["mode","stub"]);
el("chips").innerHTML=c.filter(x=>x[1]!=null).map(([k,v])=>`<span class="chip">${k} <b>${esc(v)}</b></span>`).join("")}
function optHTML(o){const g=[];if(o.kind==="switch"){g.push(`<span class="tg">${Math.round(o.hp)}% HP</span>`,`<span class="tg">matchup ${o.matchup>0?"+":""}${o.matchup}</span>`)}
else{if(o.ko)g.push(`<span class="tg ko">KO</span>`);if(o.eff){const e=/^[24]/.test(o.eff)?"se":o.eff.startsWith("immune")?"imm":"";g.push(`<span class="tg ${e}">${esc(o.eff)}</span>`)}
if(o.tera)g.push(`<span class="tg tera">Tera → ${esc(o.becomes)}</span>`);if(o.priority>0)g.push(`<span class="tg">priority +${o.priority}</span>`);if(o.acc<100)g.push(`<span class="tg">${o.acc}% acc</span>`);if(o.status)g.push(`<span class="tg">status</span>`)}
if(o.chosen)g.push(`<span class="tg pick">Jev's choice</span>`);if(o.rule)g.push(`<span class="tg rule">rule's pick</span>`);
const dmg=o.damage!=null?`<div class="dmg"><i style="width:${Math.min(100,o.damage)}%"></i></div><div class="nt">≈ ${o.damage}% of the opponent's HP</div>`:"";
let nt="";const x=o.next_turn;if(o.chosen&&x)nt=x.opponent_best_reply?`<div class="nt">next turn: ${x.we_move_first?"we move first":"opponent first"} · reply “${esc(x.opponent_best_reply)}” ≈ ${x.reply_damage_pct_of_our_hp}% of our HP${x.reply_likely_ko_us?" · can KO us":""}</div>`:`<div class="nt">switch-in takes “${esc(x.switch_in_takes_reply)}” ≈ ${x.reply_damage_pct_of_switch_in_hp}%</div>`;
const p=o.p==null?null:Math.round(o.p*100);
return `<div class="opt${o.chosen?" chosen":""}"><div><div class="ttl">${o.kind==="switch"?"⇄ ":""}${esc(o.name)} ${o.type?badge(o.type):""}<span class="k">${o.kind==="switch"?"switch":esc(o.category||"")}</span></div><div class="row" style="margin-top:6px">${g.join("")}</div>${dmg}${nt}</div><div class="prob"><div class="lbl"><span>Jev</span><span>${p==null?"–":p+"%"}</span></div><div class="bar"><i style="width:${p||0}%"></i></div></div></div>`}
function render(){S=Math.max(0,Math.min(S,BT.steps.length-1));const s=BT.steps[S],st=s.state;el("turn").textContent=s.turn;
mon(el("opp"),"Opponent",st.opp_species,st.opp_hp_pct,st.opp_types,st.opp_status,st.opp_left);mon(el("ours"),"Jev",st.our_species,st.our_hp_pct,st.our_types,st.our_status,st.our_left);
el("options").innerHTML=s.options.map(optHTML).join("");const m=s.memory||[];
el("memory").innerHTML=m.length?"<b>Memory</b>"+m.map(e=>`<div class="${e.no_visible_effect?"warn":""}">T${e.turn}: ${esc(e.we_used)}${e.opponent_switched_out?" · opponent switched":""}${e.opponent_hp_change_pct!=null?` · opp ${e.opponent_hp_change_pct}%`:""}${e.our_hp_change_pct!=null?` · us ${e.our_hp_change_pct}%`:""}${e.no_visible_effect?" · no visible effect":""}</div>`).join(""):"";
const v=el("verdict");if(s.intent){v.hidden=false;if(!s.intent.applies){v.className="verdict na";v.textContent="intent not relevant this turn"}else{v.className="verdict "+(s.intent.followed?"ok":"no");v.textContent=(s.intent.followed?"✓ intent followed":"✗ intent broken")+(s.intent.conflict?" — the rule would have broken it":"")}}else v.hidden=true;
const ch=s.options.find(o=>o.chosen),ru=s.options.find(o=>o.rule);
el("caption").textContent=s.skipped?"only one legal option":s.fallback?"fallback to the rule":`Jev chose ${ch?ch.name:"?"}${ch&&ch.p!=null?` (${Math.round(ch.p*100)}%)`:""}${ru&&!ru.chosen?` · rule: ${ru.name}`:" · same as the rule"}`;
el("slider").max=BT.steps.length-1;el("slider").value=S;el("step").textContent=`step ${S+1}/${BT.steps.length}`}
function seek(){if(ready){try{Replays.battle.seekTurn(BT.steps[S].turn)}catch(e){}}}
function go(n){stop();S=n;render();seek()}
function stop(){clearInterval(poll);clearInterval(timer);poll=timer=null;el("play").textContent="▶ Play";if(ready)try{Replays.battle.pause()}catch(e){}}
function play(){if(poll||timer){stop();return}el("play").textContent="❚❚ Pause";
if(ready){Replays.battle.play();poll=setInterval(()=>{const t=Replays.battle.turn,c=Replays.battle.currentStep;let k=0;BT.steps.forEach((s,i)=>{if(s.turn<t||(s.turn===t&&!(s.at>=0&&c<=s.at)))k=i});if(k!==S){S=k;render()}if(Replays.battle.ended)stop()},250)}
else timer=setInterval(()=>{if(S>=BT.steps.length-1){stop();return}S++;render()},1400)}
/* A second decision in the same turn (switch after a faint or a pivot move) is shown once the replay reaches
   our faint or move line that leads to that switch-in, not at the start of the turn. */
function marks(){const q=Replays.battle.stepQueue||[],sd=BT.side||"p1",ours=l=>l.startsWith(`|faint|${sd}a:`)||l.startsWith(`|move|${sd}a:`);
let n=0;BT.steps.forEach((s,i)=>{s.at=-1;if(!i||BT.steps[i-1].turn!==s.turn){n=0;return}n++;
const a=q.indexOf("|turn|"+s.turn),e=q.indexOf("|turn|"+(s.turn+1)),end=e<0?q.length:e;if(a<0)return;
let trig=-1,m=0;for(let j=a+1;j<end;j++){if(ours(q[j]))trig=j;else if(trig>=0&&q[j].startsWith(`|switch|${sd}a:`)&&++m===n){s.at=trig;return}}})}
/* Embedded, Showdown sometimes leaves its move-effect images (lightning, water, fists...) as bare file names, or
   protocol-relative ones that break on file:// pages; either way every effect shows as an empty box. */
function fixEffects(){const fx="https://play.pokemonshowdown.com/fx/";for(const k in window.BattleEffects||{}){const e=BattleEffects[k];
if(e&&e.url&&!/^https?:/.test(e.url))e.url=e.url.startsWith("//")?"https:"+e.url:fx+e.url.split("/").pop()}try{Replays.battle.scene.preloadEffects()}catch(e){}}
function waitShowdown(n){if(window.Replays&&Replays.battle){ready=true;try{fixEffects();marks()}catch(e){}try{if(BT.side==="p2")Replays.battle.switchViewpoint()}catch(e){}
if(Q.has("step"))seek();if(Q.get("autoplay")==="1")play();return}if(n>40||!BT.log){el("offline").style.display="flex";return}setTimeout(()=>waitShowdown(n+1),250)}
function init(){chips();if(DATA.intent_text){el("intent").hidden=false;el("intentText").textContent=DATA.intent_text}
el("battle").innerHTML=DATA.battles.map((b,i)=>`<option value="${i}">Battle ${i+1} — ${b.won?"won":b.won===false?"lost":"?"} (${b.steps.length} decisions)</option>`).join("");
el("battle").value=BI;el("battle").onchange=e=>{const u=new URL(location.href);u.searchParams.set("battle",e.target.value);u.searchParams.delete("step");location.href=u};
el("slider").oninput=e=>go(+e.target.value);el("prev").onclick=()=>go(S-1);el("next").onclick=()=>go(S+1);el("play").onclick=play;
document.onkeydown=e=>{if(e.key==="ArrowLeft")go(S-1);if(e.key==="ArrowRight")go(S+1);if(e.key===" "){e.preventDefault();play()}};
const r=el("result");r.className="res "+(BT.won?"w":"l");r.textContent=BT.won?"Jev won":BT.won===false?"Jev lost":"unfinished";render();waitShowdown(0)}
window.addEventListener("load",()=>setTimeout(init,50));
</script></body></html>
"""
