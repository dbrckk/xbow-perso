let campaign=null;
const $=id=>document.getElementById(id);
const lines=id=>$(id).value.split('\n').map(x=>x.trim()).filter(Boolean);
const clamp=(v,min,max)=>Math.min(max,Math.max(min,v));
const fmtSeconds=value=>{
  const seconds=Math.max(0,Number(value)||0);
  if(seconds>=3600)return (seconds/3600).toFixed(seconds%3600===0?0:1)+' h';
  if(seconds>=60)return Math.ceil(seconds/60)+' min';
  return Math.ceil(seconds)+' s';
};
$('token').value=sessionStorage.getItem('xbowApiToken')||'';
$('token').addEventListener('input',()=>sessionStorage.setItem('xbowApiToken',$('token').value));

async function api(path,opts={}){
  const token=$('token').value.trim();
  const method=(opts.method||'GET').toUpperCase();
  const mutation=['POST','PUT','PATCH','DELETE'].includes(method);
  const headers={'content-type':'application/json',...(opts.headers||{})};
  if(token)headers.authorization='Bearer '+token;
  const totp=$('totp').value.trim();
  if(mutation&&totp)headers['x-totp-code']=totp;
  try{
    const r=await fetch('/api'+path,{...opts,method,headers});
    let data;
    try{data=await r.json()}catch{data={detail:'Invalid server response'}}
    if(!r.ok)throw new Error(data.detail?(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail)):JSON.stringify(data));
    return data;
  }finally{
    if(mutation)$('totp').value='';
  }
}

function setStatus(message,type='muted'){
  $('status').className=type;
  $('status').textContent=message;
}

function budgetRow(label,used,limit){
  const safeLimit=Math.max(1,Number(limit)||1);
  const safeUsed=Math.max(0,Number(used)||0);
  const row=document.createElement('div');
  row.className='budget-row';
  const head=document.createElement('div');
  head.className='budget-head';
  const left=document.createElement('span');
  left.textContent=label;
  const right=document.createElement('span');
  right.textContent=safeUsed+' / '+safeLimit;
  head.append(left,right);
  const meter=document.createElement('div');
  meter.className='meter';
  const fill=document.createElement('span');
  fill.style.width=clamp((safeUsed/safeLimit)*100,0,100)+'%';
  meter.appendChild(fill);
  row.append(head,meter);
  return row;
}

function renderControl(data){
  $('controlCard').classList.remove('hidden');
  $('campaignState').textContent=data.campaign_state||'—';
  const breaker=data.circuit_breaker||{};
  $('breakerState').textContent=breaker.open?'OUVERT':'fermé';
  $('runtimeRemaining').textContent=fmtSeconds(data.runtime?.remaining_seconds);
  $('jobsQueued').textContent=String(data.jobs?.queued||0);
  $('jobsRunning').textContent=String(data.jobs?.running||0);
  $('jobsFailed').textContent=String(data.jobs?.failed||0);

  const pill=$('autonomyPill');
  pill.textContent=data.autonomy_blocked?'autonomie bloquée':'autonomie disponible';
  pill.className='pill '+(data.autonomy_blocked?'err':'ok');

  $('breakerReason').textContent=breaker.open&&breaker.reason?('Raison : '+breaker.reason):'';
  $('resetBreaker').classList.toggle('hidden',!breaker.open);

  const limits=data.budget?.limits||{};
  const usage=data.budget?.usage||{};
  const rows=[
    ['Actions',usage.actions,limits.max_actions],
    ['Scans',usage.scans,limits.max_scans],
    ['Validations',usage.validations,limits.max_validations],
    ['Rapports',usage.reports,limits.max_reports],
    ['Jobs simultanés',usage.inflight_jobs,limits.max_inflight_jobs],
    ['Échecs',usage.failed_jobs,limits.max_failed_jobs]
  ];
  const budgets=$('budgets');
  budgets.replaceChildren(...rows.map(row=>budgetRow(...row)));
}

function readinessClass(value){
  if(value==='report_review_ready')return 'ok';
  if(value==='needs_review')return 'warn';
  return 'err';
}

function renderFindingIntelligence(data){
  $('evidenceCard').classList.remove('hidden');
  const summary=data.summary||{};
  $('evidenceSummary').textContent=
    (summary.findings||0)+' finding(s) · '+
    (summary.saturated_clusters||0)+' cluster(s) saturé(s) · '+
    (summary.validations_saved||0)+' validation(s) évitée(s)';

  const list=$('evidenceList');
  list.replaceChildren();
  const findings=Array.isArray(data.findings)?data.findings:[];
  if(!findings.length){
    list.textContent='Aucun finding enregistré.';
    return;
  }

  for(const item of findings){
    const row=document.createElement('div');
    row.className='finding';

    const head=document.createElement('div');
    head.className='finding-head';

    const id=document.createElement('strong');
    id.textContent=item.finding_id;

    const readiness=item.readiness?.readiness||'unknown';
    const pill=document.createElement('span');
    pill.className='pill '+readinessClass(readiness);
    pill.textContent=readiness.replaceAll('_',' ');

    head.append(id,pill);

    const meta=document.createElement('div');
    meta.className='muted';
    const parts=[
      item.severity?('sévérité '+item.severity):null,
      item.cluster_status?('cluster '+item.cluster_status):null,
      item.cluster_saturated?'cluster saturé':null,
      item.readiness?('score '+Math.round((Number(item.readiness.readiness_score)||0)*100)+'%'):null
    ].filter(Boolean);
    meta.textContent=parts.join(' · ');

    const blockers=document.createElement('div');
    blockers.className='muted';
    const values=Array.isArray(item.readiness?.blockers)?item.readiness.blockers:[];
    blockers.textContent=values.length?('Blocages : '+values.join(' · ')):'Aucun blocage de readiness';

    row.append(head,meta,blockers);
    list.appendChild(row);
  }
}

async function refreshDashboard(){
  if(!campaign)return;
  const [control,intelligence]=await Promise.all([
    api('/campaigns/'+campaign.id+'/control-status'),
    api('/campaigns/'+campaign.id+'/finding-intelligence')
  ]);
  renderControl(control);
  renderFindingIntelligence(intelligence);
  $('output').textContent=JSON.stringify({control,finding_intelligence:intelligence},null,2);
}

async function activateCampaign(value){
  campaign=value;
  $('campaignId').value=campaign.id;
  $('start').disabled=!['ready','failed'].includes(campaign.state);
  $('refresh').disabled=false;
  setStatus('Campagne chargée : '+campaign.id,'ok');
  await refreshDashboard();
}

$('load').onclick=async()=>{try{
  const id=$('campaignId').value.trim();
  if(!id)throw new Error('ID campagne requis');
  await activateCampaign(await api('/campaigns/'+encodeURIComponent(id)));
}catch(e){setStatus(e.message,'err')}};

$('refresh').onclick=async()=>{try{
  await refreshDashboard();
  setStatus('État de contrôle actualisé.','ok');
}catch(e){setStatus(e.message,'err')}};

$('create').onclick=async()=>{try{
  const payload={
    name:$('name').value,
    primary_url:$('url').value,
    rules:{
      authorization_reference:$('auth').value,
      allowed_targets:lines('allowed'),
      denied_targets:lines('denied'),
      max_requests_per_second:Number($('rps').value),
      destructive_testing:false,
      denial_of_service:false,
      social_engineering:false,
      credential_attacks:false,
      automated_scanning:true,
      notes:$('notes').value
    }
  };
  const created=await api('/campaigns',{method:'POST',body:JSON.stringify(payload)});
  await activateCampaign(created);
}catch(e){setStatus(e.message,'err')}};

$('start').onclick=async()=>{if(!campaign)return;try{
  const result=await api('/campaigns/'+campaign.id+'/start',{method:'POST'});
  setStatus('Campagne démarrée.','ok');
  $('output').textContent=JSON.stringify(result,null,2);
  campaign=await api('/campaigns/'+campaign.id);
  $('start').disabled=true;
  await refreshDashboard();
}catch(e){setStatus(e.message,'err')}};

$('resetBreaker').onclick=async()=>{if(!campaign)return;try{
  const result=await api('/campaigns/'+campaign.id+'/circuit-breaker/reset',{method:'POST'});
  setStatus('Circuit breaker réinitialisé par l’opérateur.','ok');
  $('output').textContent=JSON.stringify(result,null,2);
  await refreshDashboard();
}catch(e){setStatus(e.message,'err')}};

if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
