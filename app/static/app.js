let DATA=null, selected=null;
const $=s=>document.querySelector(s);
function esc(v){return String(v??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]))}
function record(p){return `${p.match_wins??0}-${p.match_losses??0}`}
function renderList(){
 const q=($("#search").value||"").toLowerCase();
 const list=(DATA.players||[]).filter(p=>p.name.toLowerCase().includes(q));
 $("#playerList").innerHTML=list.map((p,i)=>`<button class="player ${selected===p.name?"active":""}" data-name="${esc(p.name)}"><div class="pname">${esc(p.name)}</div><div class="sub"><span>${esc(p.tag||"")}</span><span>${record(p)} · ${p.points??0} pts</span></div></button>`).join("")||'<div class="empty">No tracked players found.</div>';
 document.querySelectorAll(".player").forEach(b=>b.addEventListener("click",()=>{selected=b.dataset.name;renderList();renderProfile()}));
}
function renderProfile(){
 const p=(DATA.players||[]).find(x=>x.name===selected);
 if(!p){$("#profile").innerHTML='<div class="empty">Select a player.</div>';return}
 const wr=(p.game_wins??0)+(p.game_losses??0)?Math.round(100*p.game_wins/(p.game_wins+p.game_losses)):0;
 const matches=p.matches||[];
 $("#profile").innerHTML=`<div class="eyebrow">${esc(p.tag||"TRACKED PLAYER")}</div><h2>${esc(p.name)}</h2><div class="muted">${esc(p.status||"")}</div>
 <div class="profilegrid">
 <div class="metric"><b>${record(p)}</b><span>MATCH RECORD</span></div>
 <div class="metric"><b>${p.points??0}</b><span>POINTS</span></div>
 <div class="metric"><b>#${p.rank??"—"}</b><span>RANK</span></div>
 <div class="metric"><b>${wr}%</b><span>GAME WIN RATE</span></div>
 </div>
 <h3>Match history</h3>
 <div class="tablewrap"><table class="matches"><thead><tr><th>Round</th><th>Opponent</th><th>Result</th><th>Score</th><th>Table</th></tr></thead><tbody>
 ${matches.length?matches.map(m=>`<tr><td>${esc(m.round)}</td><td>${esc(m.opponent)}</td><td class="${m.result==="W"?"win":"loss"}">${esc(m.result)}</td><td>${esc(m.score||"—")}</td><td>${esc(m.table??"—")}</td></tr>`).join(""):'<tr><td colspan="5" class="empty">No match data yet.</td></tr>'}
 </tbody></table></div>`;
}
async function load(){
 try{
  const r=await fetch("/api/event",{cache:"no-store"});DATA=await r.json();
  const e=DATA.event||{};
  $("#eventName").textContent=e.name||"Lorcana Player Dashboard";
  $("#eventMeta").textContent=`Event ${e.id||"1007231"} · ${e.format||"Core Constructed"}`;
  $("#playerCount").textContent=e.players??"—";
  $("#trackedCount").textContent=(DATA.players||[]).length;
  $("#roundName").textContent=e.current_round?`R${e.current_round}`:"—";
  $("#updated").textContent=DATA.last_updated?new Date(DATA.last_updated).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}):"—";
  if(!selected && DATA.players?.length)selected=DATA.players[0].name;
  renderList();renderProfile();
 }catch(err){$("#profile").innerHTML='<div class="empty">Unable to load tournament data.</div>'}
}
$("#search").addEventListener("input",renderList);load();setInterval(load,60000);
