const $ = s => document.querySelector(s);
const state = { inputs: [], ref: "", out: "" };

async function api(url, body){
  const r = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body||{})});
  return r.json();
}
function setPath(el, text, empty){ el.textContent = text; el.classList.toggle("empty", !!empty); }

// ---- key status ----
function renderKey(k){
  const chip = $("#keyChip"), st = $("#keyState");
  if(k.has_key){
    chip.textContent = "Key: " + k.masked;
    chip.className = "chip"; chip.style.color = "var(--ok)";
    const src = k.source === "gui" ? "saved locally" : (k.source === "env" ? "from env var" : k.source);
    st.textContent = k.masked + " · " + src; st.className = "badge ok";
  } else {
    chip.textContent = "Key: not set"; chip.style.color = "var(--warn)";
    st.textContent = "not set"; st.className = "badge warn";
  }
  $("#cfgPath").textContent = k.config_path || "~/.editmyraw/config.json";
}

// ---- init ----
fetch("/config").then(r=>r.json()).then(c=>{
  state.out = c.default_out; setPath($("#outPath"), c.default_out, false);
  fillSelect($("#model"), c.models, c.key.model);
  fillSelect($("#imageModel"), c.image_models, c.key.image_model);
  renderKey(c.key);
});
function fillSelect(sel, items, current){
  sel.innerHTML = "";
  items.forEach(m=>{ const o=document.createElement("option"); o.value=o.textContent=m; if(m===current)o.selected=true; sel.appendChild(o); });
}

$("#keyChip").onclick = ()=>{ $("#settings").open = true; $("#settings").scrollIntoView({behavior:"smooth"}); };
$("#keySave").onclick = async ()=>{
  const key = $("#keyInput").value.trim();
  if(!key){ $("#keyMsg").textContent = "Enter a key first."; return; }
  const r = await api("/key", {key, model:$("#model").value, image_model:$("#imageModel").value});
  if(r.ok){ renderKey(r.key); $("#keyInput").value=""; $("#keyMsg").textContent="Saved locally."; }
  else $("#keyMsg").textContent = "Error: " + (r.error||"?");
};
$("#keyTest").onclick = async ()=>{
  $("#keyMsg").textContent = "Testing…";
  const r = await api("/key/test", {});
  $("#keyMsg").textContent = r.ok ? `Key works — ${r.model_count} models available (${r.source}).` : "Test failed: " + (r.error||"?");
};
$("#keyClear").onclick = async ()=>{ const r = await api("/key/clear", {}); renderKey(r.key); $("#keyMsg").textContent="Key cleared."; };

// ---- pickers ----
$("#pickFiles").onclick = async ()=>{ const r = await api("/pick",{kind:"files"}); if(r.paths&&r.paths.length){ state.inputs=r.paths; showInputs(); } };
$("#pickFolder").onclick = async ()=>{ const r = await api("/pick",{kind:"folder"}); if(r.expanded&&r.expanded.length){ state.inputs=r.expanded; showInputs(); } };
$("#pickRef").onclick = async ()=>{ const r = await api("/pick",{kind:"file"}); if(r.paths&&r.paths[0]){ state.ref=r.paths[0]; setPath($("#refPath"),state.ref,false); } };
$("#refClear").onclick = ()=>{ state.ref=""; setPath($("#refPath"),"none",true); };
$("#pickOut").onclick = async ()=>{ const r = await api("/pick",{kind:"folder"}); if(r.paths&&r.paths[0]){ state.out=r.paths[0]; setPath($("#outPath"),state.out,false); } };
$("#openOut").onclick = ()=> api("/openfolder",{dir:state.out});
function showInputs(){
  const n=state.inputs.length, names=state.inputs.slice(0,3).map(p=>p.split("/").pop()).join(", ");
  setPath($("#inPath"), n?`${n} image(s): ${names}${n>3?" +"+(n-3):""}`:"none selected", !n);
}

// ---- sliders ----
$("#strength").addEventListener("input", e=>$("#strVal").textContent=(+e.target.value).toFixed(2));
$("#quality").addEventListener("input", e=>$("#qVal").textContent=e.target.value);
$("#format").addEventListener("change", e=>{
  const jpg = e.target.value==="jpg";
  $("#quality").disabled=!jpg; $("#qLbl").style.opacity=jpg?"1":".4"; $("#qVal").style.opacity=jpg?"1":".4";
  $("#qLbl").textContent = jpg ? "JPEG quality" : "(TIFF = lossless)";
});

function radio(name){ return document.querySelector(`input[name=${name}]:checked`).value; }

// ---- run ----
$("#run").onclick = ()=>{
  if(!state.inputs.length){ alert("Choose target images first."); return; }
  const wf = radio("wf");
  if((wf==="example"||wf==="combo") && !state.ref){ alert("This workflow needs a reference image."); return; }
  const cfg = {
    inputs: state.inputs, reference: state.ref || null, out_dir: state.out,
    workflow: wf, mode: radio("md"), prompt: $("#prompt").value,
    skin_mode: $("#skin").value, fmt: $("#format").value, quality: +$("#quality").value,
    dry_run: $("#dryrun").checked, allow_generative: $("#generative").checked,
    batch_consistency: $("#consistency").checked, consistency_rounds: +$("#rounds").value,
  };
  $("#run").disabled=true; $("#bar").style.width="0%"; $("#results").innerHTML=""; $("#resultsCard").style.display="none"; $("#zipLink").hidden=true;
  api("/process", cfg).then(({job_id})=>listen(job_id));
};

function listen(jobId){
  const es = new EventSource("/progress/"+jobId);
  es.onmessage = ev=>{
    const d = JSON.parse(ev.data);
    if(d.type==="progress"){
      $("#bar").style.width = Math.round(d.frac*100)+"%";
      $("#status").innerHTML = d.msg.startsWith("AI ") ? `<span class="ai">${d.msg}</span>` : d.msg;
    } else if(d.type==="done"){
      es.close(); $("#run").disabled=false; $("#bar").style.width="100%"; render(d);
    } else if(d.type==="error"){
      es.close(); $("#run").disabled=false; $("#status").textContent="Error."; alert("Error:\n"+d.msg);
    }
  };
  es.onerror = ()=>{ es.close(); $("#run").disabled=false; };
}

function render(d){
  let extra = d.gemini_log && d.gemini_log.length ? "  ·  AI: "+d.gemini_log[d.gemini_log.length-1] : "";
  $("#status").innerHTML = `Done — <b>${d.count}</b> image(s) in ${d.out_dir}${extra}`;
  if(d.zip){ const z=$("#zipLink"); z.hidden=false; z.textContent="ZIP ready — open folder"; z.onclick=()=>api("/openfolder",{dir:d.out_dir}); }
  const box = $("#results"); box.innerHTML="";
  d.rows.forEach(r=>{
    const div = document.createElement("div"); div.className="pair";
    div.innerHTML = `
      <div class="meta">
        <div class="name">${r.stem}</div>
        ${r.generated?'<div class="gen">✨ generated edit</div>':''}
        <div class="diag">${r.diagnosis||""}</div>
        <details class="recipe"><summary>recipe</summary><pre>${JSON.stringify(r.recipe,null,2)}</pre></details>
      </div>
      <div class="imgs">
        <figure><img src="${r.before}"><figcaption>before</figcaption></figure>
        <figure><img src="${r.after}"><figcaption>after</figcaption></figure>
      </div>`;
    box.appendChild(div);
  });
  $("#resultsCard").style.display="block";
}
