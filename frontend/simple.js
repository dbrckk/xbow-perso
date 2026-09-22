(()=>{
  const TOKEN_KEY='xbowApiToken';
  const ACTIVE_KEY='xbow:simple-bounty:active-batch:v1';
  const REVIEW_CONCURRENCY=2;
  const UI_VERSION='v79';
  let selection=[];
  let selectionResult=null;
  let reviewDrafts=[];
  let runtimeReady=false;
  let batchActive=false;
  let activeBatchId='';
  let timer=null;

  const $=id=>document.getElementById(id);

  function token(){
    return String($('token')?.value||'').trim();
  }

  function saveToken(){
    try{localStorage.setItem(TOKEN_KEY,$('token')?.value||'');}catch(_error){}
  }

  function setStatus(message,kind=''){
    const node=$('status');
    if(!node)return;
    node.textContent=message;
    node.className='simple-status '+kind;
  }

  function updateStartAvailability(){
    const button=$('start');
    if(!button)return;
    const reviewsPending=Number(selectionResult?.review_count||0)>0;
    button.disabled=!(
      selection.length===6
      && !reviewsPending
      && runtimeReady===true
      && batchActive===false
    );
  }

  function requireToken(){
    if(token())return true;
    setStatus('Entre le jeton API une seule fois. Il restera enregistré sur cet appareil.','err');
    $('token')?.focus();
    return false;
  }

  async function api(path,options={}){
    if(!requireToken())throw new Error('Jeton API requis');
    const headers={'content-type':'application/json',...(options.headers||{})};
    headers.authorization='Bearer '+token();
    let response;
    try{
      response=await fetch('/api'+path,{...options,headers,cache:'no-store'});
    }catch(_error){
      throw new Error('Serveur inaccessible');
    }
    let data={};
    try{data=await response.json();}catch(_error){}
    if(!response.ok){
      const detail=data?.detail;
      const message=typeof detail==='string'
        ?detail
        :(detail?.message?String(detail.message):'HTTP '+response.status);
      const error=new Error(message);
      error.status=response.status;
      error.reason=String(detail?.reason||'');
      error.detail=detail;
      throw error;
    }
    return data;
  }

  function money(value){
    const amount=Number(value||0);
    return amount>0?' · historique max $'+amount.toLocaleString():'';
  }

  function stateLabel(item){
    const status=String(item?.status||'');
    if(status==='READY')return 'prêt';
    if(status==='REVALIDATE')return 'revalidation au démarrage';
    return 'revue initiale';
  }

  function renderSelection(result){
    const groups=result?.groups||{};
    const root=$('selection');
    root.replaceChildren();
    const rows=[
      ['2 faciles',groups.easy||[],false],
      ['2 moyens',groups.medium||[],false],
      ['2 fort potentiel',groups.high_value||[],true]
    ];
    for(const [title,items,showValue] of rows){
      const section=document.createElement('div');
      section.className='simple-group';
      const head=document.createElement('strong');
      head.textContent=title;
      section.appendChild(head);
      for(const item of items){
        const row=document.createElement('div');
        row.className='simple-program';
        const text=document.createElement('span');
        text.textContent=String(item?.name||item?.handle||'Programme')+
          ' · '+String(item?.handle||'')+
          (showValue?money(item?.historical_usd_awarded_max):'');
        const state=document.createElement('span');
        state.className=['READY','REVALIDATE'].includes(String(item?.status||''))?'state-ready':'state-review';
        state.textContent=' · '+stateLabel(item);
        row.append(text,state);
        section.appendChild(row);
      }
      root.appendChild(section);
    }
  }

  function clearReviewPanel(){
    reviewDrafts=[];
    const panel=$('reviewPanel');
    const list=$('reviewList');
    if(list)list.replaceChildren();
    panel?.classList.add('hidden');
  }

  function reviewableDraft(draft){
    return Boolean(
      draft?.prefill?.primary_url
      && draft?.evidence?.scope_complete===true
      && draft?.evidence?.offers_bounties===true
      && draft?.evidence?.submission_state!=='closed'
      && draft?.evidence?.program_state!=='closed'
    );
  }

  function renderReviewDrafts(){
    const panel=$('reviewPanel');
    const list=$('reviewList');
    list.replaceChildren();

    for(const draft of reviewDrafts){
      const details=document.createElement('details');
      details.className='simple-review-item';

      const summary=document.createElement('summary');
      summary.textContent=String(draft?.prefill?.name||draft?.handle||'Programme')+
        ' · '+String(draft?.handle||'');
      details.appendChild(summary);

      const body=document.createElement('div');
      body.className='simple-review-body';

      const meta=document.createElement('p');
      meta.className='muted compact';
      meta.textContent='Cible proposée : '+String(draft?.prefill?.primary_url||'aucune cible compatible')+
        ' · safe harbor H1 : '+(draft?.evidence?.gold_standard_safe_harbor===true?'oui':'à vérifier')+
        ' · scope complet : '+(draft?.evidence?.scope_complete===true?'oui':'non');
      body.appendChild(meta);

      const policy=document.createElement('div');
      policy.className='simple-review-policy';
      policy.textContent=String(draft?.policy_text||'Aucun texte de politique fourni par HackerOne.');
      body.appendChild(policy);

      const exclusions=Array.isArray(draft?.scope_exclusions)?draft.scope_exclusions:[];
      if(exclusions.length){
        const exclusionsBox=document.createElement('div');
        exclusionsBox.className='simple-review-policy';
        const title=document.createElement('strong');
        title.textContent='Exclusions HackerOne';
        exclusionsBox.appendChild(title);
        for(const item of exclusions){
          const line=document.createElement('p');
          line.className='muted compact';
          line.textContent=(String(item?.category||'exclusion')+' · '+String(item?.details||'')).trim();
          exclusionsBox.appendChild(line);
        }
        body.appendChild(exclusionsBox);
      }

      const reviewState=document.createElement('p');
      reviewState.className='muted compact';
      reviewState.textContent=reviewableDraft(draft)
        ?'Compatible avec une validation groupée conservatrice à 1 requête/s.'
        :'Ce programme ne peut pas être validé depuis cette vue : cible ou scope incompatible/incomplet.';
      body.appendChild(reviewState);

      details.appendChild(body);
      list.appendChild(details);
    }

    panel.classList.remove('hidden');
  }

  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

  function retryableReviewError(error){
    const status=Number(error?.status||0);
    const reason=String(error?.reason||'');
    if(reason==='hackerone_program_review_unavailable')return false;
    if([429,502,503,504].includes(status))return true;
    return [
      'hackerone_rate_limited',
      'hackerone_timeout',
      'hackerone_connection_failed',
      'hackerone_io_failed',
      'hackerone_upstream_unavailable'
    ].includes(reason);
  }

  async function loadReviewDraft(handle){
    let lastError=null;
    for(let attempt=0;attempt<2;attempt+=1){
      try{
        return await api('/imports/hackerone/programs/'+encodeURIComponent(handle)+'/review-draft');
      }catch(error){
        lastError=error;
        if(!retryableReviewError(error)||attempt>=1)break;
        await sleep(1200);
      }
    }
    throw lastError||new Error('Revue HackerOne indisponible');
  }

  async function loadReviewDrafts(result,draftCache=new Map()){
    const candidates=(result?.selection||[])
      .filter(item=>String(item?.status||'')==='REVIEW')
      .map(item=>String(item?.handle||''))
      .filter(Boolean);
    if(!candidates.length){
      clearReviewPanel();
      return {failedHandles:[]};
    }

    const draftsByHandle=new Map();
    const pending=[];
    for(const handle of candidates){
      const cached=draftCache.get(handle);
      if(cached&&reviewableDraft(cached)){
        draftsByHandle.set(handle,cached);
      }else{
        pending.push(handle);
      }
    }

    let completed=draftsByHandle.size;
    const total=candidates.length;
    const updateProgress=()=>{
      setStatus(
        'Première utilisation : politiques vérifiées '+completed+'/'+total+
        (pending.length?' · chargement des remplacements…':'…')
      );
    };
    updateProgress();

    const settled=new Array(pending.length);
    let cursor=0;
    async function reviewWorker(){
      while(true){
        const index=cursor;
        cursor+=1;
        if(index>=pending.length)return;
        const handle=pending[index];
        try{
          settled[index]={
            status:'fulfilled',
            value:{handle,draft:await loadReviewDraft(handle)}
          };
        }catch(error){
          error.handle=handle;
          settled[index]={status:'rejected',reason:error};
        }finally{
          completed+=1;
          updateProgress();
        }
      }
    }
    const workers=Math.min(REVIEW_CONCURRENCY,pending.length);
    if(workers>0){
      await Promise.all(Array.from({length:workers},()=>reviewWorker()));
    }

    const failedHandles=[];
    const upstreamErrors=[];
    for(const item of settled){
      if(item?.status==='fulfilled'){
        const handle=String(item.value.handle||'');
        const draft=item.value.draft;
        if(reviewableDraft(draft)){
          draftsByHandle.set(handle,draft);
          draftCache.set(handle,draft);
        }else{
          const normalized=String(handle||draft?.handle||'').trim().toLowerCase();
          if(normalized&&!failedHandles.includes(normalized))failedHandles.push(normalized);
        }
        continue;
      }
      if(!item)continue;
      const error=item.reason;
      if(error?.reason==='hackerone_program_review_unavailable'){
        const handle=String(error?.detail?.handle||error?.handle||'').trim().toLowerCase();
        if(handle&&!failedHandles.includes(handle))failedHandles.push(handle);
        continue;
      }
      upstreamErrors.push({handle:String(error?.handle||''),error});
    }

    if(upstreamErrors.length){
      let probe=null;
      try{
        probe=await api('/imports/hackerone/connection?probe=true');
      }catch(_error){}
      if(probe?.reachable===true&&probe?.authenticated===true){
        for(const item of upstreamErrors){
          const handle=String(item.handle||'').trim().toLowerCase();
          if(handle&&!failedHandles.includes(handle))failedHandles.push(handle);
        }
      }else{
        const first=upstreamErrors[0].error;
        if(probe?.reason)first.connectionReason=String(probe.reason);
        if(probe?.upstream_status)first.upstreamStatus=Number(probe.upstream_status);
        throw first;
      }
    }

    reviewDrafts=candidates
      .map(handle=>draftsByHandle.get(handle))
      .filter(Boolean);
    if(failedHandles.length)return {failedHandles};
    renderReviewDrafts();
    return {failedHandles:[]};
  }

  async function refreshRuntimeReadiness({quiet=true}={}){
    const node=$('runtimeStatus');
    if(!node||!token())return null;
    try{
      const readiness=await api('/hackerone/live-readiness');
      const failed=(Array.isArray(readiness?.checks)?readiness.checks:[])
        .filter(item=>item?.required===true&&item?.ok!==true);
      runtimeReady=readiness?.live_scan_ready===true;
      const actionNode=$('runtimeAction');
      if(runtimeReady){
        node.textContent='Scanner : prêt pour les programmes autorisés.';
        node.className='muted compact state-ready';
        if(actionNode)actionNode.textContent='Tout est prêt côté runtime. Après validation des politiques, le bouton Commencer devient disponible.';
      }else{
        const labels=failed.slice(0,3)
          .map(item=>String(item?.label||item?.id||'contrôle'))
          .filter(Boolean);
        node.textContent='Scanner : non prêt'+(labels.length?' · '+labels.join(' · '):'')+'.';
        node.className='muted compact state-review';
        const firstAction=String(failed[0]?.action||'').trim();
        const activation=String(readiness?.scanner_start_command||'').trim();
        if(actionNode){
          actionNode.textContent=firstAction
            ?'À faire : '+firstAction+(activation?' · Commande : '+activation:'')
            :(activation?'Commande : '+activation:'');
        }
        if(!quiet)setStatus('Le scanner doit être prêt avant le lancement.','warn');
      }
      updateStartAvailability();
      return readiness;
    }catch(error){
      runtimeReady=false;
      updateStartAvailability();
      node.textContent='Scanner : état indisponible.';
      node.className='muted compact state-review';
      const actionNode=$('runtimeAction');
      if(actionNode)actionNode.textContent='Vérifie la stack de production puis relance le diagnostic.';
      if(!quiet)setStatus('État scanner indisponible : '+error.message,'warn');
      return null;
    }
  }

  async function loadSimpleSelection(excludedHandles=[]){
    try{
      const query=excludedHandles.length
        ?'?exclude='+encodeURIComponent(excludedHandles.join(','))
        :'';
      return await api('/hackerone/simple-selection'+query);
    }catch(error){
      if(error?.reason!=='hackerone_catalog_not_initialized')throw error;
      setStatus('Premier démarrage : initialisation du catalogue HackerOne…');
      const connection=await api('/imports/hackerone/connection');
      if(connection?.configured!==true){
        const missing=new Error('Connexion HackerOne non configurée sur le serveur.');
        missing.reason='hackerone_credentials_missing';
        throw missing;
      }
      await api('/imports/hackerone/programs?refresh=true');
      const query=excludedHandles.length
        ?'?exclude='+encodeURIComponent(excludedHandles.join(','))
        :'';
      return await api('/hackerone/simple-selection'+query);
    }
  }

  function rebuildSimpleSelection(base,groups){
    const easy=Array.isArray(groups?.easy)?groups.easy:[];
    const medium=Array.isArray(groups?.medium)?groups.medium:[];
    const highValue=Array.isArray(groups?.high_value)?groups.high_value:[];
    const selected=[...easy,...medium,...highValue];
    const count=status=>selected.filter(item=>String(item?.status||'')===status).length;
    const complete=easy.length===2&&medium.length===2&&highValue.length===2;
    return {
      ...(base||{}),
      groups:{easy,medium,high_value:highValue},
      selection:selected,
      handles:selected.map(item=>String(item?.handle||'')).filter(Boolean),
      complete,
      selection_count:selected.length,
      ready_count:count('READY'),
      review_count:count('REVIEW'),
      revalidation_count:count('REVALIDATE'),
      launch_ready:complete&&count('REVIEW')===0
    };
  }

  function replaceFailedSelection(current,replacements,failedHandles){
    const failed=new Set(
      (Array.isArray(failedHandles)?failedHandles:[])
        .map(value=>String(value||'').trim().toLowerCase())
        .filter(Boolean)
    );
    const used=new Set();
    const nextGroups={easy:[],medium:[],high_value:[]};
    for(const key of ['easy','medium','high_value']){
      const currentItems=Array.isArray(current?.groups?.[key])?current.groups[key]:[];
      const kept=currentItems.filter(item=>{
        const handle=String(item?.handle||'').trim().toLowerCase();
        return handle&&!failed.has(handle);
      });
      for(const item of kept){
        nextGroups[key].push(item);
        used.add(String(item?.handle||'').trim().toLowerCase());
      }
      const needed=Math.max(0,2-nextGroups[key].length);
      const candidates=Array.isArray(replacements?.groups?.[key])?replacements.groups[key]:[];
      for(const item of candidates){
        if(nextGroups[key].length>=2)break;
        const handle=String(item?.handle||'').trim().toLowerCase();
        if(!handle||failed.has(handle)||used.has(handle))continue;
        nextGroups[key].push(item);
        used.add(handle);
      }
      if(needed>0&&nextGroups[key].length<2){
        return null;
      }
    }
    return rebuildSimpleSelection(current,nextGroups);
  }

  async function prepare(initialExcluded=[]){
    if(!requireToken())return;
    const button=$('prepare');
    button.disabled=true;
    $('start').disabled=true;
    clearReviewPanel();
    setStatus('Préparation serveur des 6 programmes et de leurs politiques…');
    try{
      const excluded=[...new Set(
        (Array.isArray(initialExcluded)?initialExcluded:[])
          .map(value=>String(value||'').trim().toLowerCase())
          .filter(Boolean)
      )];
      const query=excluded.length
        ?'?exclude='+encodeURIComponent(excluded.join(','))
        :'';
      let result;
      try{
        result=await api('/hackerone/simple-review-package'+query);
      }catch(error){
        if(error?.reason!=='hackerone_catalog_not_initialized')throw error;
        setStatus('Premier démarrage : initialisation du catalogue HackerOne…');
        const connection=await api('/imports/hackerone/connection');
        if(connection?.configured!==true){
          const missing=new Error('Connexion HackerOne non configurée sur le serveur.');
          missing.reason='hackerone_credentials_missing';
          throw missing;
        }
        await api('/imports/hackerone/programs?refresh=true');
        result=await api('/hackerone/simple-review-package'+query);
      }

      selectionResult=result;
      selection=Array.isArray(result?.handles)?result.handles.filter(Boolean):[];
      renderSelection(result);
      if(result?.complete!==true||selection.length!==6){
        throw new Error('Le serveur n’a pas pu constituer les 6 campagnes.');
      }

      reviewDrafts=Array.isArray(result?.review_drafts)?result.review_drafts:[];
      const reviewCount=Number(result?.review_count||0);
      if(reviewCount>0){
        if(reviewDrafts.length!==reviewCount){
          throw new Error('Le paquet de revue HackerOne est incomplet.');
        }
        renderReviewDrafts();
        if($('reviewAllConfirm'))$('reviewAllConfirm').checked=false;
        setStatus(
          reviewCount+' programme(s) nécessitent une validation initiale. Les remplacements incompatibles ont déjà été résolus côté serveur.',
          'warn'
        );
        return;
      }

      clearReviewPanel();
      await refreshRuntimeReadiness({quiet:true});
      updateStartAvailability();
      const revalidationCount=Number(result?.revalidation_count||0);
      setStatus(
        revalidationCount
          ?'Sélection prête : '+revalidationCount+' programme(s) déjà revu(s) seront revalidés au démarrage.'
          :'Sélection prête : les 6 programmes sont READY.',
        'ok'
      );
    }catch(error){
      selection=[];
      selectionResult=null;
      runtimeReady=false;
      updateStartAvailability();
      $('selection').textContent='Aucune sélection exploitable.';
      clearReviewPanel();
      let message=error.message;
      const reason=String(error?.reason||error?.detail?.reason||'');
      if(reason==='simple_review_package_incomplete'||reason==='simple_review_package_exhausted'){
        const rejected=Number(error?.detail?.rejected_count||0);
        message='Pas assez de programmes compatibles après vérification'+(rejected?' ('+rejected+' rejeté(s))':'')+'.';
      }else if(reason==='hackerone_credentials_missing'){
        message='Connexion HackerOne absente sur le serveur.';
      }else if(reason==='hackerone_authentication_failed'){
        message='Identifiants HackerOne refusés par HackerOne.';
      }else if(reason==='hackerone_rate_limited'){
        message='Limite HackerOne atteinte. Réessaie dans quelques minutes.';
      }else if(reason==='hackerone_timeout'){
        message='HackerOne ne répond pas avant le délai serveur.';
      }else if(reason==='hackerone_connection_failed'||reason==='hackerone_io_failed'){
        message='Le VPS ne parvient pas à joindre HackerOne.';
      }else if(reason==='hackerone_upstream_unavailable'){
        message='HackerOne est momentanément inaccessible.';
      }
      setStatus('Sélection impossible : '+message,'err');
    }finally{
      button.disabled=false;
    }
  }

  function reviewProfilePayload(draft){
    const prefill=draft?.prefill||{};
    return {
      document:prefill.scope_document,
      policy:{
        authorization_reference:String(prefill.authorization_reference||''),
        policy_version:String(prefill.policy_version||''),
        reviewed_at:new Date().toISOString(),
        reviewed_by:'simple-dashboard-operator',
        safe_harbor_confirmed:true,
        automated_scanning:true,
        max_requests_per_second:1,
        test_account_required:false,
        test_account_constraints:'',
        additional_restrictions:[],
        program_notes:'Revue humaine confirmée depuis le dashboard minimal. Profil conservateur à 1 requête/s.'
      },
      remote_handle:String(draft?.handle||''),
      remote_snapshot_sha256:String(draft?.snapshot_sha256||''),
      remember_review_profile:true,
      preferred_primary_url:String(prefill.primary_url||'')
    };
  }

  async function persistReviewDraft(draft){
    let lastError=null;
    for(let attempt=0;attempt<2;attempt+=1){
      try{
        const result=await api('/imports/hackerone/rules-preview',{
          method:'POST',
          body:JSON.stringify(reviewProfilePayload(draft))
        });
        if(result?.review_profile_persisted!==true){
          const error=new Error(
            String(draft?.handle||'programme')+' : '+
            String(result?.review_profile_persist_reason||'profil non enregistré')
          );
          error.handle=String(draft?.handle||'');
          throw error;
        }
        return result;
      }catch(error){
        lastError=error;
        error.handle=String(error?.handle||draft?.handle||'');
        if(!retryableReviewError(error)||attempt>=1)break;
        await sleep(1200);
      }
    }
    throw lastError||new Error('Validation du profil HackerOne indisponible');
  }

  async function saveReviews(){
    if(!requireToken())return;
    if(!reviewDrafts.length){
      setStatus('Aucune revue initiale à enregistrer.','err');
      return;
    }
    if(reviewDrafts.some(draft=>!reviewableDraft(draft))){
      setStatus('Au moins un programme a un scope incompatible ou incomplet. Relance la sélection.','err');
      return;
    }
    const confirmation=$('reviewAllConfirm');
    if(!confirmation?.checked){
      setStatus('Lis les politiques affichées puis coche la confirmation groupée.','err');
      return;
    }

    const button=$('saveReviews');
    button.disabled=true;
    const drafts=[...reviewDrafts];
    let completed=0;
    let cursor=0;
    const settled=new Array(drafts.length);
    const updateProgress=()=>setStatus(
      'Validation des profils '+completed+'/'+drafts.length+'…'
    );
    updateProgress();
    try{
      async function persistWorker(){
        while(true){
          const index=cursor;
          cursor+=1;
          if(index>=drafts.length)return;
          const draft=drafts[index];
          try{
            settled[index]={
              status:'fulfilled',
              value:await persistReviewDraft(draft)
            };
          }catch(error){
            settled[index]={status:'rejected',reason:error};
          }finally{
            completed+=1;
            updateProgress();
          }
        }
      }
      const workers=Math.min(REVIEW_CONCURRENCY,drafts.length);
      await Promise.all(Array.from({length:workers},()=>persistWorker()));
      const failures=settled.filter(item=>item?.status==='rejected');
      if(failures.length){
        const replaceable=[];
        for(const item of failures){
          const error=item.reason;
          const handles=(Array.isArray(error?.detail?.handles)?error.detail.handles:[error?.handle])
            .map(value=>String(value||'').trim().toLowerCase())
            .filter(Boolean);
          if(replaceableLaunchReason(error?.reason)){
            for(const handle of handles){
              if(!replaceable.includes(handle))replaceable.push(handle);
            }
          }
        }
        if(replaceable.length){
          setStatus(
            'La politique de '+replaceable.length+' programme(s) a changé. Nouvelle sélection…',
            'warn'
          );
          await prepare(replaceable);
          return;
        }
        throw failures[0].reason;
      }
      setStatus('Profils enregistrés. Revalidation de la sélection…','ok');
      await prepare();
    }catch(error){
      setStatus('Validation interrompue : '+error.message,'err');
    }finally{
      button.disabled=false;
    }
  }

  function replaceableLaunchReason(reason){
    return [
      'program_submissions_not_open',
      'program_not_currently_open',
      'review_profile_required',
      'review_profile_binding_mismatch',
      'review_profile_incomplete',
      'review_profile_invalid',
      'stale_hackerone_snapshot',
      'hackerone_snapshot_document_mismatch'
    ].includes(String(reason||''));
  }

  function preflightBlockerMessage(preflight){
    const runtime=preflight?.runtime||{};
    const checks=Array.isArray(runtime?.checks)?runtime.checks:[];
    const failed=checks.filter(item=>item?.required===true&&item?.ok!==true);
    if(!failed.length){
      const blockers=(Array.isArray(preflight?.blockers)?preflight.blockers:[])
        .map(value=>String(value||'')).filter(Boolean);
      return blockers.length?'Pré-vol bloqué · '+blockers.join(' · '):'Pré-vol bloqué';
    }
    const labels=failed.slice(0,3)
      .map(item=>String(item?.label||item?.id||'contrôle'))
      .filter(Boolean);
    const command=String(runtime?.scanner_start_command||'').trim();
    return 'Scanner non prêt'+(labels.length?' · '+labels.join(' · '):'')+
      (command?' · À exécuter sur le VPS : '+command:'');
  }

  async function start(){
    if(!requireToken())return;
    if(selection.length!==6){
      setStatus('Sélectionne d’abord les 6 campagnes.','err');
      return;
    }
    if(Number(selectionResult?.review_count||0)>0){
      setStatus('Valide d’abord les programmes indiqués « revue initiale ».','err');
      return;
    }
    const button=$('start');
    button.disabled=true;
    const mode=$('mode').value==='parallel'?'parallel':'sequential';
    setStatus('Validation finale serveur : scope, profils, runtime et fingerprints…');
    try{
      const batch=await api('/imports/hackerone/batches/launch-reviewed',{
        method:'POST',
        body:JSON.stringify({mode,handles:selection})
      });
      const id=String(batch?.id||'');
      activeBatchId=id;
      if(id){
        try{localStorage.setItem(ACTIVE_KEY,id);}catch(_error){}
      }
      batchActive=true;
      setStatus(
        mode==='parallel'
          ?'6 campagnes lancées en parallèle. Tu peux fermer la page.'
          :'6 campagnes mises en file. Elles seront exécutées une après l’autre.',
        'ok'
      );
      updateStartAvailability();
      await refreshJournal({quiet:true});
    }catch(error){
      if(!Number(error?.status||0)&&String(error?.message||'')==='Serveur inaccessible'){
        await refreshJournal({quiet:true});
        if(batchActive){
          setStatus(
            'Le téléphone a perdu la réponse, mais le lot est bien actif côté serveur. Aucun doublon ne sera lancé.',
            'ok'
          );
          updateStartAvailability();
          return;
        }
      }
      if(error?.reason==='batch_go_no_go_blocked'){
        const detail=error?.detail||{};
        setStatus(
          'Lancement bloqué : '+preflightBlockerMessage({
            runtime:detail?.runtime||{},
            blockers:detail?.blockers||[]
          }),
          'err'
        );
        await refreshRuntimeReadiness({quiet:true});
        updateStartAvailability();
        return;
      }
      if(error?.reason==='active_batch_exists'){
        batchActive=true;
        const activeId=String(error?.detail?.batch_id||'');
        activeBatchId=activeId;
        if(activeId){
          try{localStorage.setItem(ACTIVE_KEY,activeId);}catch(_error){}
        }
        setStatus('Un lot HackerOne est déjà en cours côté serveur. Aucun doublon n’a été créé.','warn');
        await refreshJournal({quiet:true});
        updateStartAvailability();
        return;
      }
      const handles=(Array.isArray(error?.detail?.handles)?error.detail.handles:[])
        .map(value=>String(value||'').trim().toLowerCase())
        .filter(handle=>handle&&selection.includes(handle));
      if(replaceableLaunchReason(error?.reason)&&handles.length){
        setStatus(
          'Lancement : '+handles.length+' programme(s) ont changé après le pré-vol. Remplacement automatique…',
          'warn'
        );
        button.disabled=false;
        await prepare(handles);
        return;
      }
      setStatus('Lancement bloqué : '+error.message,'err');
      await refreshRuntimeReadiness({quiet:true});
      updateStartAvailability();
    }
  }

  function repoSyncLabel(entry){
    const sync=entry?.repository_sync||{};
    if(sync.status==='synced'){
      return ' · apprentissage GitHub synchronisé'+
        (sync.issue_number?' #'+String(sync.issue_number):'');
    }
    if(sync.status==='error')return ' · apprentissage GitHub à réessayer';
    return '';
  }

  function renderJournal(payload){
    const entries=Array.isArray(payload?.journal)?payload.journal:[];
    const root=$('journal');
    root.replaceChildren();

    if(!entries.length){
      root.textContent='Aucune campagne enregistrée.';
    }else{
      for(const entry of entries.slice(0,30)){
        const card=document.createElement('article');
        card.className='simple-log';
        const head=document.createElement('strong');
        const when=entry?.created_at?new Date(entry.created_at).toLocaleString():'';
        head.textContent=(when?when+' · ':'')+
          String(entry?.mode||'')+' · '+String(entry?.state||'')+repoSyncLabel(entry);
        card.appendChild(head);

        for(const member of (entry?.members||[])){
          const line=document.createElement('div');
          const reason=member?.reason?' · '+String(member.reason):'';
          line.textContent=String(member?.handle||'campagne')+
            ' — '+String(member?.status||member?.campaign_state||'—')+
            ' · '+String(member?.brief||'aucun brief')+reason;
          card.appendChild(line);

          for(const finding of (member?.finding_brief||[]).slice(0,5)){
            const f=document.createElement('div');
            f.className='simple-finding';
            f.textContent='↳ '+String(finding.severity||'')+
              ' · '+String(finding.title||'')+
              ' · '+String(finding.status||'');
            card.appendChild(f);
          }
        }
        root.appendChild(card);
      }
    }

    const digest=payload?.learning_digest||{};
    const sync=payload?.repository_sync||{};
    let syncText='sync repo désactivée';
    if(sync.enabled&&sync.configured)syncText='sync repo automatique active vers '+String(sync.repository||'GitHub');
    else if(sync.enabled&&!sync.configured)syncText='sync repo en attente du credential GitHub';
    $('learning').textContent=
      'Mémoire : '+String(digest.campaign_count||0)+' campagne(s), '+
      String(digest.confirmed_findings||0)+' finding(s) confirmé(s) · '+syncText+'.';
  }

  async function refreshJournal({quiet=false}={}){
    if(!token()){
      if(!quiet)setStatus('Entre ton jeton API pour charger le journal.','err');
      return;
    }
    try{
      const payload=await api('/hackerone/journal?limit=50');
      renderJournal(payload);
      const entries=Array.isArray(payload?.journal)?payload.journal:[];
      const active=entries.find(item=>!['completed','cancelled'].includes(String(item?.state||'')));
      batchActive=Boolean(active);
      activeBatchId=active?String(active?.id||''):'';
      const cancelButton=$('cancelActive');
      if(cancelButton)cancelButton.classList.toggle('hidden',!batchActive||!activeBatchId);
      if(!batchActive){
        try{localStorage.removeItem(ACTIVE_KEY);}catch(_error){}
      }else if(activeBatchId){
        try{localStorage.setItem(ACTIVE_KEY,activeBatchId);}catch(_error){}
      }
      updateStartAvailability();
      if(active){
        if(!quiet)setStatus('Campagnes en cours côté serveur. Tu peux revenir plus tard.','ok');
      }else if(entries.length&&!quiet){
        setStatus('Derniers résultats chargés.','ok');
      }
    }catch(error){
      const root=$('journal');
      if(root&&!root.textContent.trim())root.textContent='Journal momentanément indisponible.';
      if(!quiet)setStatus('Journal indisponible : '+error.message,'err');
    }
  }

  async function cancelActiveBatch(){
    if(!requireToken())return;
    if(!activeBatchId){
      setStatus('Aucun lot HackerOne actif à annuler.','warn');
      await refreshJournal({quiet:true});
      return;
    }
    const button=$('cancelActive');
    if(button)button.disabled=true;
    try{
      await api('/imports/hackerone/batches/'+encodeURIComponent(activeBatchId)+'/cancel',{
        method:'POST',
        body:'{}'
      });
      batchActive=false;
      activeBatchId='';
      try{localStorage.removeItem(ACTIVE_KEY);}catch(_error){}
      if(button)button.classList.add('hidden');
      setStatus('Lot HackerOne annulé. Tu peux préparer un nouveau lancement.','ok');
      await refreshJournal({quiet:true});
      await refreshRuntimeReadiness({quiet:true});
      updateStartAvailability();
    }catch(error){
      setStatus('Annulation impossible : '+error.message,'err');
    }finally{
      if(button)button.disabled=false;
    }
  }

  function bind(){
    try{$('token').value=localStorage.getItem(TOKEN_KEY)||'';}catch(_error){}
    const versionNode=$('buildVersion');
    if(versionNode)versionNode.textContent='Interface '+UI_VERSION;
    if('serviceWorker' in navigator){
      navigator.serviceWorker.register('/sw.js?v=79',{updateViaCache:'none'})
        .then(registration=>registration.update())
        .catch(()=>{});
    }
    $('token').addEventListener('input',saveToken);
    $('token').addEventListener('change',()=>void refreshRuntimeReadiness({quiet:true}));
    $('prepare').addEventListener('click',()=>void prepare());
    $('saveReviews').addEventListener('click',()=>void saveReviews());
    $('start').addEventListener('click',()=>void start());
    $('refresh').addEventListener('click',()=>void refreshJournal());
    $('cancelActive').addEventListener('click',()=>void cancelActiveBatch());
    window.addEventListener('unhandledrejection',event=>{
      const message=event?.reason?.message||String(event?.reason||'Erreur JavaScript');
      setStatus('Erreur interface : '+message,'err');
    });
    window.addEventListener('error',event=>{
      if(event?.message)setStatus('Erreur interface : '+event.message,'err');
    });
    void refreshRuntimeReadiness({quiet:true});
    void refreshJournal({quiet:true});
    timer=setInterval(()=>{
      void refreshRuntimeReadiness({quiet:true});
      void refreshJournal({quiet:true});
    },15000);
  }

  window.addEventListener('beforeunload',()=>{if(timer)clearInterval(timer);});
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',bind,{once:true});
  }else{
    bind();
  }
})();
