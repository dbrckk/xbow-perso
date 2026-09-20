let campaign=null;
let findingIntelligence=null;
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
  const scanner=data.scanner_execution||{};
  const stability=data.planner_stability||{};
  const recon=data.recon_telemetry||{};
  $('scannerState').textContent=scanner.dispatch_ready?'READY':'bloqué';
  $('plannerStability').textContent=
    (stability.state||'unknown')+' '+Math.round((Number(stability.score)||0)*100)+'%';
  $('reconRequests').textContent=String(recon.requests_made||0);
  const scannerReasons=Array.isArray(scanner.dispatch_block_reasons)?scanner.dispatch_block_reasons:[];
  $('controlDetails').textContent=
    'Scanner: '+(scannerReasons.length?scannerReasons.join(' · '):'admis')+
    ' · Recon hors scope ignorés: '+String(recon.skipped_out_of_scope||0)+
    ' · cross-origin ignorés: '+String(recon.skipped_cross_origin||0);

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

const severityRank={critical:4,high:3,medium:2,low:1,info:0};

function visibleFindings(data){
  const filter=$('findingFilter')?.value||'all';
  const sort=$('findingSort')?.value||'priority';
  const findings=[...(Array.isArray(data.findings)?data.findings:[])];

  const filtered=findings.filter(item=>{
    const readiness=item.readiness?.readiness||'unknown';
    if(filter==='all')return true;
    if(filter==='saturated')return Boolean(item.cluster_saturated);
    return readiness===filter;
  });

  filtered.sort((a,b)=>{
    const ar=Number(a.readiness?.readiness_score)||0;
    const br=Number(b.readiness?.readiness_score)||0;
    if(sort==='readiness_desc')return br-ar||String(a.finding_id).localeCompare(String(b.finding_id));
    if(sort==='readiness_asc')return ar-br||String(a.finding_id).localeCompare(String(b.finding_id));
    if(sort==='severity')return (severityRank[b.severity]||0)-(severityRank[a.severity]||0)||br-ar;
    if(sort==='cluster')return String(a.cluster_id||'~').localeCompare(String(b.cluster_id||'~'))||br-ar;
    const priority={
      blocked:5,
      needs_validation:4,
      needs_review:3,
      report_review_ready:2,
      unknown:1
    };
    const ap=priority[a.readiness?.readiness||'unknown']||0;
    const bp=priority[b.readiness?.readiness||'unknown']||0;
    return bp-ap||br-ar||String(a.finding_id).localeCompare(String(b.finding_id));
  });
  return filtered;
}

function renderClusters(data){
  $('clusterCard').classList.remove('hidden');
  const clusters=Array.isArray(data.clusters)?data.clusters:[];
  const list=$('clusterList');
  list.replaceChildren();
  const saved=clusters.reduce((total,item)=>total+(Number(item.saturation?.validations_saved)||0),0);
  $('clusterSummary').textContent=clusters.length+' cluster(s) · '+saved+' validation(s) évitée(s)';

  if(!clusters.length){
    list.textContent='Aucun cluster détecté.';
    return;
  }

  for(const item of clusters){
    const cluster=item.cluster||{};
    const consensus=item.consensus||{};
    const saturation=item.saturation||{};
    const row=document.createElement('div');
    row.className='cluster';

    const head=document.createElement('div');
    head.className='finding-head';
    const title=document.createElement('strong');
    title.textContent=cluster.cluster_id||'cluster';
    const status=document.createElement('span');
    status.className='pill '+readinessClass(consensus.status||'unknown');
    status.textContent=(consensus.status||'unknown').replaceAll('_',' ');
    head.append(title,status);

    const meta=document.createElement('div');
    meta.className='cluster-meta';
    const confidence=Math.round((Number(cluster.confidence)||0)*100);
    const members=Array.isArray(cluster.finding_ids)?cluster.finding_ids:[];
    meta.textContent=
      confidence+'% confiance · '+
      members.length+' membre(s) · '+
      (saturation.saturated?'saturé':'non saturé')+' · '+
      (Number(saturation.validations_saved)||0)+' validation(s) évitée(s)';

    const details=document.createElement('details');
    const summary=document.createElement('summary');
    summary.textContent='Voir les détails';
    const memberBlock=document.createElement('div');
    memberBlock.className='muted detail-block';
    memberBlock.textContent='Membres : '+(members.length?members.join(', '):'aucun');
    const representative=document.createElement('div');
    representative.className='muted detail-block';
    representative.textContent='Représentant : '+(saturation.representative_finding_id||'aucun');
    const blockers=document.createElement('div');
    blockers.className='muted detail-block';
    const blockerValues=Array.isArray(consensus.blockers)?consensus.blockers:[];
    blockers.textContent=blockerValues.length?('Blocages : '+blockerValues.join(' · ')):'Aucun blocage cluster';
    details.append(summary,memberBlock,representative,blockers);

    row.append(head,meta,details);
    list.appendChild(row);
  }
}

function renderReviewAndSubmission(reviewQueue, reportReadiness){
  $('reviewCard').classList.remove('hidden');
  const tasks=Array.isArray(reviewQueue.tasks)?reviewQueue.tasks:[];
  const readiness=Array.isArray(reportReadiness.findings)?reportReadiness.findings:[];
  const ready=Number(reportReadiness.summary?.submission_ready)||0;
  const blocked=Number(reportReadiness.summary?.submission_blocked)||0;
  $('reviewSummary').textContent=tasks.length+' tâche(s)';
  $('submissionSummary').textContent=
    ready+' prêt(s) à soumettre · '+blocked+' bloqué(s) · approbation humaine requise';

  const list=$('reviewList');
  list.replaceChildren();

  for(const item of readiness){
    const row=document.createElement('div');
    row.className='review-item';
    const head=document.createElement('div');
    head.className='finding-head';
    const title=document.createElement('strong');
    title.textContent='Finding '+item.finding_id;
    const pill=document.createElement('span');
    pill.className='pill '+(item.submission_ready?'ok':'warn');
    pill.textContent=item.submission_ready?'submission ready':'incomplet';
    head.append(title,pill);
    const meta=document.createElement('div');
    meta.className='muted';
    meta.textContent=
      Math.round((Number(item.submission_completeness_score)||0)*100)+'% complétude · preuves '+
      (item.evidence_quality_grade||'unknown');
    const blockers=document.createElement('div');
    blockers.className='muted detail-block';
    const values=Array.isArray(item.metadata_blockers)?item.metadata_blockers:[];
    blockers.textContent=values.length?('Manques : '+values.join(' · ')):'Métadonnées complètes';
    row.append(head,meta,blockers);
    list.appendChild(row);
  }

  for(const task of tasks.slice(0,10)){
    const row=document.createElement('div');
    row.className='review-item';
    const head=document.createElement('div');
    head.className='finding-head';
    const title=document.createElement('strong');
    title.textContent=task.kind||'review';
    const pill=document.createElement('span');
    pill.className='pill';
    pill.textContent=Math.round((Number(task.priority)||0)*100)+'%';
    head.append(title,pill);
    const reason=document.createElement('div');
    reason.className='muted';
    reason.textContent=task.reason||'';
    row.append(head,reason);
    list.appendChild(row);
  }

  if(!readiness.length&&!tasks.length){
    list.textContent='Aucune tâche de revue.';
  }
}

function renderDecisionTimeline(data){
  $('timelineCard').classList.remove('hidden');
  const timeline=Array.isArray(data.timeline)?data.timeline:[];
  const audit=data.audit||{};
  const stability=data.planner_stability||{};
  $('timelineSummary').textContent=timeline.length+' événement(s)';
  const state=stability.state||'unknown';
  const score=Math.round((Number(stability.score)||0)*100);
  $('timelineAudit').textContent=
    'Chaîne audit : '+(audit.valid?'valide':'invalide')+
    ' · '+(audit.checked||0)+' décision(s) vérifiée(s)'+
    ' · stabilité '+state+' '+score+'%';
  $('timelineAudit').className=(stability.alert?'err':'muted');

  const oldAlert=$('plannerStabilityAlert');
  if(oldAlert)oldAlert.remove();
  if(stability.alert){
    const alert=document.createElement('div');
    alert.id='plannerStabilityAlert';
    alert.className='stability-alert';
    const anomalies=Array.isArray(stability.anomalies)?stability.anomalies:[];
    const labels=anomalies.map(item=>item.kind).filter(Boolean);
    alert.textContent='Alerte stabilité planner : '+(labels.length?labels.join(' · '):'comportement instable détecté');
    $('timelineAudit').insertAdjacentElement('afterend',alert);
  }

  const list=$('timelineList');
  list.replaceChildren();
  if(!timeline.length){
    list.textContent='Aucun événement horodaté.';
    return;
  }

  for(const item of timeline){
    const row=document.createElement('div');
    row.className='timeline-item';

    const dot=document.createElement('span');
    dot.className='timeline-dot '+(item.type==='planner_decision'?'decision':'event');

    const body=document.createElement('div');
    const head=document.createElement('div');
    head.className='timeline-head';

    const title=document.createElement('strong');
    if(item.type==='planner_decision'){
      title.textContent=(item.action||'decision')+' · '+(item.agent||'agent');
    }else{
      title.textContent=item.event_type||'campaign event';
    }

    const time=document.createElement('span');
    time.className='muted';
    time.textContent=item.at?new Date(item.at).toLocaleString('fr-FR'):'';

    head.append(title,time);

    const detail=document.createElement('div');
    detail.className='muted';
    if(item.type==='planner_decision'){
      detail.textContent=item.reason||'Aucune raison enregistrée';
      const why=item.why||null;
      if(why){
        const whyDetails=document.createElement('details');
        const whySummary=document.createElement('summary');
        whySummary.textContent='Why?';
        const signals=document.createElement('div');
        signals.className='why-grid';
        const entries=[
          ['Gate',why.gate?.allowed===false?'bloqué':'autorisé',why.gate?.blockers],
          ['Risque',why.risk?.level||'inconnu',why.risk?.reasons],
          ['Consensus',why.consensus?.next_focus||'aucun',why.consensus?.reasons],
          ['Cycle',why.cycle?.state||'inconnu',[why.cycle?.reason]],
          ['Surface',Math.round((Number(why.surface_enrichment?.score)||0)*100)+'%',[why.surface_enrichment?.ready?'prête':'insuffisante']],
          ['Couverture',Math.round((Number(why.coverage?.coverage_score)||0)*100)+'%',[]]
        ];
        for(const [label,value,reasons] of entries){
          const block=document.createElement('div');
          block.className='why-block';
          const strong=document.createElement('strong');
          strong.textContent=label+' : '+value;
          const text=document.createElement('div');
          text.className='muted';
          const list=(Array.isArray(reasons)?reasons:[]).filter(Boolean);
          text.textContent=list.join(' · ');
          block.append(strong,text);
          signals.appendChild(block);
        }
        whyDetails.append(whySummary,signals);
        body.appendChild(whyDetails);
      }

      if(item.causal_summary){
        const causal=document.createElement('div');
        causal.className='causal-summary';
        causal.textContent=item.causal_summary;
        body.appendChild(causal);
      }

      const changes=Array.isArray(item.signal_diff)?item.signal_diff:[];
      if(item.transition&&changes.length){
        const diffDetails=document.createElement('details');
        const diffSummary=document.createElement('summary');
        diffSummary.textContent='Changements depuis la décision précédente';
        const transition=document.createElement('div');
        transition.className='muted detail-block';
        transition.textContent=
          (item.transition.from_action||'—')+' → '+(item.transition.to_action||'—');
        const diffList=document.createElement('div');
        diffList.className='signal-diff-list';
        for(const change of changes){
          const line=document.createElement('div');
          line.className='signal-diff';
          const name=document.createElement('strong');
          name.textContent=change.signal;
          const values=document.createElement('div');
          values.className='muted';
          values.textContent=String(change.before??'—')+' → '+String(change.after??'—');
          line.append(name,values);
          if(Array.isArray(change.added)&&change.added.length){
            const added=document.createElement('div');
            added.className='ok';
            added.textContent='+ '+change.added.join(', ');
            line.appendChild(added);
          }
          if(Array.isArray(change.removed)&&change.removed.length){
            const removed=document.createElement('div');
            removed.className='err';
            removed.textContent='− '+change.removed.join(', ');
            line.appendChild(removed);
          }
          diffList.appendChild(line);
        }
        diffDetails.append(diffSummary,transition,diffList);
        body.appendChild(diffDetails);
      }
    }else{
      const parts=[
        item.finding_id?('finding '+item.finding_id):null,
        item.job_id?('job '+item.job_id):null,
        item.validator?('validator '+item.validator):null
      ].filter(Boolean);
      detail.textContent=parts.join(' · ');
    }

    body.append(head,detail);
    row.append(dot,body);
    list.appendChild(row);
  }
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
  findingIntelligence=data;
  const findings=visibleFindings(data);
  if(!findings.length){
    list.textContent='Aucun finding pour ce filtre.';
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

    const details=document.createElement('details');
    const summaryEl=document.createElement('summary');
    summaryEl.textContent='Détails';
    const blockers=document.createElement('div');
    blockers.className='muted detail-block';
    const values=Array.isArray(item.readiness?.blockers)?item.readiness.blockers:[];
    blockers.textContent=values.length?('Blocages : '+values.join(' · ')):'Aucun blocage de readiness';
    const cluster=document.createElement('div');
    cluster.className='muted detail-block';
    cluster.textContent=item.cluster_id?('Cluster : '+item.cluster_id):'Hors cluster';
    details.append(summaryEl,blockers,cluster);

    row.append(head,meta,details);
    list.appendChild(row);
  }
}

function renderTargetMemory(data,diff){
  const card=$('targetMemoryCard');
  card.classList.remove('hidden');
  const summary=data?.summary||{};
  const delta=data?.delta||{};
  const byKind=summary.by_kind||{};
  const campaigns=Number(data?.campaigns_considered)||0;
  $('targetMemoryCampaigns').textContent=campaigns+' campagne'+(campaigns===1?'':'s');
  $('targetMemoryIdentity').textContent=
    (data?.target?.host||'cible inconnue')+
    (data?.previous_campaign_id?' · comparaison '+data.previous_campaign_id:' · première référence');
  $('targetMemoryNodes').textContent=String(summary.nodes||0);
  $('targetMemoryCurrent').textContent=String(summary.current_nodes||0);
  $('targetMemoryAdded').textContent=String(delta.added_count||0);
  $('targetMemoryRemoved').textContent=String(delta.removed_count||0);
  $('targetMemoryPersistent').textContent=String(delta.persistent_count||0)+' persistant';

  const diffSummary=diff?.summary||{};
  const priority=String(diffSummary.review_priority||'stable');
  const score=Number(diffSummary.change_score)||0;
  const priorityLabels={stable:'Surface stable',low:'Changement faible',medium:'Changement notable',high:'Changement important'};
  $('surfaceDiffLabel').textContent=priorityLabels[priority]||'Évolution de surface';
  $('surfaceDiffScore').textContent=String(score);
  $('surfaceDiffSummary').textContent=diff?.baseline_available
    ? String(diffSummary.change_count||0)+' changement(s) observé(s) vs campagne précédente · lecture seule'
    : 'Première campagne de référence : le delta sera disponible au prochain snapshot.';
  const priorityPill=$('surfaceDiffPriority');
  priorityPill.textContent=priority;
  priorityPill.className='pill '+(priority==='high'?'warn':priority==='medium'?'warn':priority==='stable'?'ok':'');
  const focusWrap=$('surfaceDiffFocusWrap');
  const focusRoot=$('surfaceDiffFocus');
  const focus=Array.isArray(diff?.focus)?diff.focus:[];
  focusRoot.replaceChildren();
  if(focus.length){
    focusWrap.classList.remove('hidden');
    for(const item of focus){
      const code=document.createElement('code');
      code.textContent=(item.kind||'surface')+' · '+(item.value||'');
      code.title=item.reason||'';
      focusRoot.appendChild(code);
    }
  }else{
    focusWrap.classList.add('hidden');
  }

  const kinds=$('targetMemoryKinds');
  kinds.replaceChildren();
  for(const [key,label] of [
    ['asset','Assets'],
    ['endpoint','Endpoints'],
    ['form','Forms'],
    ['technology','Technologies'],
    ['waf','WAF']
  ]){
    const box=document.createElement('div');
    box.className='memory-kind';
    const name=document.createElement('span');
    name.textContent=label;
    const value=document.createElement('strong');
    value.textContent=String(Number(byKind[key])||0);
    box.append(name,value);
    kinds.appendChild(box);
  }

  const renderDeltaList=(id,items,empty)=>{
    const root=$(id);
    root.replaceChildren();
    const values=Array.isArray(items)?items:[];
    if(!values.length){
      root.textContent=empty;
      return;
    }
    for(const item of values.slice(0,20)){
      const code=document.createElement('code');
      code.textContent=(item.kind||'surface')+' · '+(item.value||'');
      root.appendChild(code);
    }
  };
  renderDeltaList('targetMemoryAddedList',delta.added,'Aucun nouvel élément.');
  renderDeltaList('targetMemoryRemovedList',delta.removed,'Aucun élément disparu.');
}

async function refreshDashboard(){
  if(!campaign)return;
  const [control,intelligence,timeline,reviewQueue,reportReadiness,targetMemory,surfaceDiff]=await Promise.all([
    api('/campaigns/'+campaign.id+'/control-status'),
    api('/campaigns/'+campaign.id+'/finding-intelligence'),
    api('/campaigns/'+campaign.id+'/decision-timeline'),
    api('/campaigns/'+campaign.id+'/review-queue'),
    api('/campaigns/'+campaign.id+'/report-readiness'),
    api('/campaigns/'+campaign.id+'/target-memory'),
    api('/campaigns/'+campaign.id+'/surface-diff')
  ]);
  renderControl(control);
  renderTargetMemory(targetMemory,surfaceDiff);
  renderFindingIntelligence(intelligence);
  renderClusters(intelligence);
  renderDecisionTimeline(timeline);
  renderReviewAndSubmission(reviewQueue,reportReadiness);
  $('output').textContent=JSON.stringify({control,target_memory:targetMemory,surface_diff:surfaceDiff,finding_intelligence:intelligence,decision_timeline:timeline,review_queue:reviewQueue,report_readiness:reportReadiness},null,2);
}

async function activateCampaign(value){
  campaign=value;
  $('campaignId').value=campaign.id;
  $('start').disabled=!['ready','failed'].includes(campaign.state);
  $('refresh').disabled=false;
  setStatus('Campagne chargée : '+campaign.id,'ok');
  await refreshDashboard();
}

$('findingFilter').addEventListener('change',()=>{if(findingIntelligence)renderFindingIntelligence(findingIntelligence)});
$('findingSort').addEventListener('change',()=>{if(findingIntelligence)renderFindingIntelligence(findingIntelligence)});

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
