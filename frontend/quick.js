(()=>{
  const $=id=>document.getElementById(id);
  const STORAGE_KEY='xbowApiToken';
  let currentPlan=null;
  let journalTimer=null;

  function savedToken(){
    try{return localStorage.getItem(STORAGE_KEY)||'';}catch(_error){return '';}
  }

  function saveToken(value){
    try{localStorage.setItem(STORAGE_KEY,value);}catch(_error){}
    const legacy=$('token');
    if(legacy)legacy.value=value;
  }

  async function api(path,options={}){
    const token=String($('quickToken')?.value||'').trim();
    const headers={'content-type':'application/json',...(options.headers||{})};
    if(token)headers.authorization='Bearer '+token;
    const response=await fetch('/api'+path,{...options,headers});
    let payload={};
    try{payload=await response.json();}catch(_error){}
    if(!response.ok){
      const detail=payload?.detail;
      const message=typeof detail==='string'
        ?detail
        :(detail?.message||detail?.reason||('HTTP '+response.status));
      const error=new Error(message);
      error.detail=detail;
      throw error;
    }
    return payload;
  }

  function money(value){
    const amount=Number(value)||0;
    if(amount<=0)return 'historique non chiffré';
    try{
      return new Intl.NumberFormat('fr-FR',{
        style:'currency',
        currency:'USD',
        maximumFractionDigits:0
      }).format(amount);
    }catch(_error){
      return '$'+Math.round(amount);
    }
  }

  function setStatus(message,kind=''){
    const node=$('quickStatus');
    if(!node)return;
    node.textContent=message;
    node.className='quick-status '+kind;
  }

  function groupTitle(group){
    if(group==='easy')return '2 faciles estimés';
    if(group==='medium')return '2 moyens estimés';
    return '2 forts gains historiques';
  }

  function renderPlan(plan){
    currentPlan=plan;
    const wrap=$('quickSelection');
    wrap.replaceChildren();
    const groups=plan?.groups||{};
    for(const group of ['easy','medium','high_value']){
      const box=document.createElement('section');
      box.className='quick-group';
      const title=document.createElement('h3');
      title.textContent=groupTitle(group);
      box.appendChild(title);
      const items=Array.isArray(groups[group])?groups[group]:[];
      if(!items.length){
        const empty=document.createElement('p');
        empty.className='muted compact';
        empty.textContent='Aucun programme READY disponible dans ce groupe.';
        box.appendChild(empty);
      }
      for(const item of items){
        const row=document.createElement('div');
        row.className='quick-program';
        const left=document.createElement('div');
        const strong=document.createElement('strong');
        strong.textContent=String(item.name||item.handle||'Programme');
        const meta=document.createElement('span');
        meta.textContent=String(item.handle||'');
        left.append(strong,meta);

        const right=document.createElement('span');
        right.className='pill';
        right.textContent=group==='high_value'
          ?money(item.historical_usd_awarded_max)
          :('effort '+String(item.effort_factor||'—'));
        row.append(left,right);
        box.appendChild(row);
      }
      wrap.appendChild(box);
    }

    const start=$('quickStart');
    start.disabled=plan?.complete!==true;
    if(plan?.complete===true){
      setStatus('6 programmes READY sélectionnés. Tu peux démarrer.','ok-text');
    }else{
      setStatus(
        String(plan?.selected||0)+'/6 programmes READY disponibles. '+
        'Aucun programme non validé ne sera lancé automatiquement.',
        'warn'
      );
    }
  }

  async function selectSix(){
    const button=$('quickSelect');
    button.disabled=true;
    setStatus('Sélection des 6 programmes…');
    try{
      const plan=await api('/hackerone/quick-plan');
      renderPlan(plan);
    }catch(error){
      currentPlan=null;
      $('quickStart').disabled=true;
      setStatus('Sélection impossible : '+error.message,'err-text');
    }finally{
      button.disabled=false;
    }
  }

  async function startSix(){
    if(!currentPlan?.complete)return;
    const button=$('quickStart');
    button.disabled=true;
    const mode=String($('quickMode')?.value||'sequential');
    setStatus(
      mode==='parallel'
        ?'Démarrage des 6 campagnes en parallèle…'
        :'Démarrage du lot séquentiel…'
    );
    try{
      const payload=await api('/hackerone/quick-run',{
        method:'POST',
        body:JSON.stringify({
          mode,
          handles:Array.isArray(currentPlan.handles)?currentPlan.handles:[]
        })
      });
      const batch=payload?.batch||{};
      setStatus(
        'Lot '+String(batch.id||'créé')+
        ' démarré. Tu peux fermer cette page et revenir plus tard.',
        'ok-text'
      );
      await refreshJournal();
    }catch(error){
      if(error?.detail?.reason==='quick_selection_stale'){
        currentPlan=null;
        setStatus('La sélection a changé. Appuie à nouveau sur « Sélectionner 6 ».','warn');
      }else{
        setStatus('Démarrage refusé : '+error.message,'err-text');
      }
    }finally{
      button.disabled=currentPlan?.complete!==true;
    }
  }

  function stateLabel(state){
    const labels={
      queued:'en attente',
      running:'en cours',
      completed:'terminé',
      cancelled:'annulé'
    };
    return labels[String(state||'')]||String(state||'inconnu');
  }

  function briefLine(brief){
    if(!brief?.totals)return 'Brief en préparation.';
    const t=brief.totals;
    return [
      String(t.campaigns||0)+' campagne(s)',
      String(t.confirmed_findings||0)+' finding(s) confirmé(s)',
      String(t.high_critical_confirmed||0)+' high/critical',
      String(t.worker_failed||0)+' job(s) échoué(s)'
    ].join(' · ');
  }

  function renderBatch(entry){
    const card=document.createElement('article');
    card.className='quick-journal-entry';

    const head=document.createElement('div');
    head.className='quick-journal-head';
    const title=document.createElement('div');
    const strong=document.createElement('strong');
    strong.textContent='Lot '+String(entry.id||'').slice(0,8);
    const meta=document.createElement('span');
    meta.textContent=(entry.mode==='parallel'?'Parallèle':'Séquentiel')+
      ' · '+stateLabel(entry.state);
    title.append(strong,meta);
    const pill=document.createElement('span');
    pill.className='pill '+(entry.state==='completed'?'ok':entry.state==='running'?'warn':'');
    pill.textContent=stateLabel(entry.state);
    head.append(title,pill);
    card.appendChild(head);

    const summary=document.createElement('p');
    summary.className='muted compact';
    const s=entry.summary||{};
    summary.textContent=
      String(s.done||0)+' terminée(s) · '+
      String(s.running||0)+' en cours · '+
      String(s.ready||0)+' en attente · '+
      String((s.review||0)+(s.blocked||0))+' à revoir';
    card.appendChild(summary);

    if(entry.brief){
      const brief=document.createElement('p');
      brief.className='quick-brief-line';
      brief.textContent=briefLine(entry.brief);
      card.appendChild(brief);
    }

    const learning=document.createElement('p');
    learning.className='muted compact';
    const delivery=entry.learning_delivery||{};
    learning.textContent=delivery.delivered
      ?'Apprentissage : résumé envoyé au repo.'
      :(delivery.queued
        ?'Apprentissage : résumé détaillé stocké dans l’outbox.'
        :'Apprentissage : sera généré à la fin du lot.');
    card.appendChild(learning);

    const details=document.createElement('details');
    const detailsTitle=document.createElement('summary');
    detailsTitle.textContent='Voir le journal détaillé';
    details.appendChild(detailsTitle);

    const members=Array.isArray(entry.members)?entry.members:[];
    for(const member of members){
      const row=document.createElement('div');
      row.className='quick-log-row';
      const label=document.createElement('strong');
      const group=String(member.quick_group||'');
      const prefix=group==='easy'?'Facile':group==='medium'?'Moyen':group==='high_value'?'Gain élevé':'Campagne';
      label.textContent=prefix+' · '+String(member.handle||member.campaign_id||'');
      const status=document.createElement('span');
      status.textContent=String(member.status||'');
      row.append(label,status);
      details.appendChild(row);
    }

    const campaigns=Array.isArray(entry.brief?.campaigns)?entry.brief.campaigns:[];
    for(const campaign of campaigns){
      const block=document.createElement('div');
      block.className='quick-campaign-brief';
      const title=document.createElement('strong');
      title.textContent=String(campaign.name||campaign.handle||'Campagne');
      const fs=campaign.finding_summary||{};
      const text=document.createElement('p');
      text.className='muted compact';
      text.textContent=
        'État '+String(campaign.state||'—')+
        ' · '+String(fs.total||0)+' finding(s)'+
        ' · '+String(fs.confirmed||0)+' confirmé(s)'+
        ' · '+String(fs.high_critical_confirmed||0)+' high/critical';
      block.append(title,text);

      const confirmed=Array.isArray(campaign.confirmed_findings)?campaign.confirmed_findings:[];
      for(const finding of confirmed.slice(0,8)){
        const findingLine=document.createElement('div');
        findingLine.className='quick-finding-line';
        findingLine.textContent=
          String(finding.severity||'').toUpperCase()+' · '+
          String(finding.title||'Finding');
        block.appendChild(findingLine);
      }
      details.appendChild(block);
    }

    card.appendChild(details);
    return card;
  }

  function renderJournal(payload){
    const journal=$('quickJournal');
    journal.replaceChildren();
    const items=Array.isArray(payload?.journal)?payload.journal:[];
    if(!items.length){
      const empty=document.createElement('p');
      empty.className='muted';
      empty.textContent='Aucune campagne dans le journal pour le moment.';
      journal.appendChild(empty);
      return;
    }
    for(const item of items)journal.appendChild(renderBatch(item));
  }

  async function refreshJournal(){
    const button=$('quickRefreshJournal');
    if(button)button.disabled=true;
    try{
      const payload=await api('/hackerone/quick-journal?limit=20');
      renderJournal(payload);
      $('quickJournalUpdated').textContent='Mis à jour à '+new Date().toLocaleTimeString();
    }catch(error){
      $('quickJournalUpdated').textContent='Journal indisponible : '+error.message;
    }finally{
      if(button)button.disabled=false;
    }
  }

  function init(){
    const token=$('quickToken');
    token.value=savedToken();
    saveToken(token.value);
    token.addEventListener('input',()=>saveToken(token.value));

    $('quickSelect').addEventListener('click',()=>void selectSix());
    $('quickStart').addEventListener('click',()=>void startSix());
    $('quickRefreshJournal').addEventListener('click',()=>void refreshJournal());

    void refreshJournal();
    journalTimer=setInterval(()=>void refreshJournal(),15000);
    window.addEventListener('beforeunload',()=>{
      if(journalTimer!==null)clearInterval(journalTimer);
    });
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',init,{once:true});
  }else{
    init();
  }
})();
