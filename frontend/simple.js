(()=>{
  const TOKEN_KEY='xbowApiToken';
  const ACTIVE_KEY='xbow:simple-bounty:active-batch:v1';
  const HTB_ACTIVE_KEY='xbow:htb:last-campaign:v1';
  const REVIEW_CONCURRENCY=2;
  const UI_VERSION='v98';
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
      selection.length===1
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
    const timeoutMs=Math.max(1000,Number(options.timeoutMs||45000));
    const controller=new AbortController();
    const timerId=setTimeout(()=>controller.abort(),timeoutMs);
    const fetchOptions={...options};
    delete fetchOptions.timeoutMs;
    let response;
    try{
      response=await fetch('/api'+path,{
        ...fetchOptions,
        headers,
        cache:'no-store',
        signal:controller.signal
      });
    }catch(error){
      if(error?.name==='AbortError'){
        throw new Error('Délai serveur dépassé');
      }
      throw new Error('Serveur inaccessible');
    }finally{
      clearTimeout(timerId);
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
    const items=Array.isArray(result?.selection)?result.selection:[];
    const root=$('selection');
    root.replaceChildren();
    const section=document.createElement('div');
    section.className='simple-group';
    const head=document.createElement('strong');
    head.textContent=items.length===1?'1 programme accessible':'2 programmes accessibles';
    section.appendChild(head);
    for(const item of items){
      const row=document.createElement('div');
      row.className='simple-program';
      const text=document.createElement('span');
      text.textContent=String(item?.name||item?.handle||'Programme')+
        ' · '+String(item?.handle||'')+
        money(item?.historical_usd_awarded_max);
      const state=document.createElement('span');
      state.className=['READY','REVALIDATE'].includes(String(item?.status||''))?'state-ready':'state-review';
      state.textContent=' · '+stateLabel(item);
      row.append(text,state);
      section.appendChild(row);
    }
    root.appendChild(section);
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

  function browserBlockReasonLabel(reason){
    const labels={
      browser_automation_disabled:'automatisation désactivée',
      playwright_runtime_unattested:'runtime Playwright non attesté',
      invalid_boolean_configuration:'configuration invalide'
    };
    return labels[String(reason||'')]||String(reason||'blocage runtime');
  }

  async function refreshBrowserReadiness({quiet=true}={}){
    const node=$('browserRuntimeStatus');
    if(!node||!token())return null;
    try{
      const capabilities=await api('/capabilities');
      const browser=capabilities?.execution?.browser_detail||{};
      const reasons=Array.isArray(browser?.dispatch_block_reasons)
        ?browser.dispatch_block_reasons
        :[];
      if(browser?.dispatch_ready===true){
        node.textContent='Navigateur : Playwright prêt et attesté.';
        node.className='muted compact state-ready';
      }else if(browser?.browser_automation_enabled!==true){
        node.textContent='Navigateur : désactivé.';
        node.className='muted compact';
      }else{
        const labels=reasons.slice(0,2).map(browserBlockReasonLabel).filter(Boolean);
        node.textContent='Navigateur : non prêt'+(labels.length?' · '+labels.join(' · '):'')+'.';
        node.className='muted compact state-review';
      }
      return browser;
    }catch(error){
      node.textContent='Navigateur : état indisponible.';
      node.className='muted compact state-review';
      if(!quiet)setStatus('État navigateur indisponible : '+error.message,'warn');
      return null;
    }
  }

  function rejectionSummaryText(detail){
    const summary=detail&&typeof detail.rejection_summary==='object'
      ?detail.rejection_summary
      :{};
    const labels={
      scope_exclusions_require_manual_enforcement:'exclusions de scope',
      scope_incomplete_for_web_engine:'scope incompatible',
      no_compatible_primary_domain:'aucun domaine compatible',
      policy_text_unavailable:'politique absente',
      bounties_not_offered:'pas de bounty',
      submissions_not_open:'soumissions fermées',
      program_not_open:'programme fermé',
      review_unavailable:'revue indisponible'
    };
    return Object.entries(summary)
      .sort((a,b)=>Number(b[1]||0)-Number(a[1]||0))
      .slice(0,3)
      .map(([reason,count])=>String(count)+'× '+String(labels[reason]||reason))
      .join(' · ');
  }

  async function prepare(initialExcluded=[]){
    if(!requireToken())return;
    const button=$('prepare');
    button.disabled=true;
    $('start').disabled=true;
    clearReviewPanel();
    setStatus('Recherche d’un programme HackerOne réellement accessible…');
    const searchStarted=Date.now();
    const searchTimer=setInterval(()=>{
      const seconds=Math.max(1,Math.floor((Date.now()-searchStarted)/1000));
      setStatus('Recherche de programmes accessibles… '+seconds+' s');
    },5000);
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
        result=await api('/hackerone/simple-review-package'+query,{timeoutMs:130000});
      }catch(error){
        if(error?.reason!=='hackerone_catalog_not_initialized')throw error;
        setStatus('Premier démarrage : initialisation du catalogue HackerOne…');
        const connection=await api('/imports/hackerone/connection');
        if(connection?.configured!==true){
          const missing=new Error('Connexion HackerOne non configurée sur le serveur.');
          missing.reason='hackerone_credentials_missing';
          throw missing;
        }
        await api('/imports/hackerone/programs?refresh=true',{timeoutMs:130000});
        result=await api('/hackerone/simple-review-package'+query,{timeoutMs:130000});
      }

      selectionResult=result;
      selection=Array.isArray(result?.handles)?result.handles.filter(Boolean):[];
      renderSelection(result);
      if(result?.complete!==true||selection.length!==1){
        throw new Error('Le serveur n’a pas trouvé de programme exploitable.');
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
          reviewCount+' programme(s) nécessitent une validation initiale avant lancement.',
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
          :'Sélection prête : '+selection.length+' programme(s) accessible(s).',
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
        const summary=rejectionSummaryText(error?.detail||{});
        message='Aucun programme compatible trouvé après vérification'+
          (rejected?' ('+rejected+' rejeté(s))':'')+
          (summary?' · '+summary:'')+'.';
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
      clearInterval(searchTimer);
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
      const reviewedHandles=new Set(
        drafts.map(draft=>String(draft?.handle||'').trim().toLowerCase()).filter(Boolean)
      );
      const nextSelection=(Array.isArray(selectionResult?.selection)?selectionResult.selection:[])
        .map(item=>{
          const handle=String(item?.handle||'').trim().toLowerCase();
          if(!reviewedHandles.has(handle))return item;
          return {...item,status:'REVALIDATE',revalidation_deferred:true};
        });
      selectionResult={
        ...(selectionResult||{}),
        groups:{accessible:nextSelection},
        selection:nextSelection,
        handles:nextSelection.map(item=>String(item?.handle||'')).filter(Boolean),
        review_count:0,
        revalidation_count:nextSelection.filter(item=>String(item?.status||'')==='REVALIDATE').length,
        launch_ready:nextSelection.length>=1
      };
      renderSelection(selectionResult);
      clearReviewPanel();
      await refreshRuntimeReadiness({quiet:true});
      updateStartAvailability();
      setStatus('Profils enregistrés. La sélection reste en place et sera revalidée au lancement.','ok');
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
      'scope_exclusions_require_manual_enforcement',
      'safe_harbor_required',
      'automated_scanning_not_authorized',
      'test_account_workflow_not_supported',
      'test_account_constraints_not_supported',
      'additional_restrictions_require_manual_enforcement',
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
    if(selection.length<1||selection.length>2){
      setStatus('Sélectionne d’abord un programme accessible.','err');
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
          ?selection.length+' campagne(s) lancée(s) en parallèle. Tu peux fermer la page.'
          :selection.length+' campagne(s) mise(s) en file.',
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

  function setHtbStatus(message,kind=''){
    const node=$('htbStatus');
    if(!node)return;
    node.textContent=message;
    node.className='simple-status '+kind;
  }

  async function startHtbLab(){
    if(!requireToken())return;
    const target=String($('htbTarget')?.value||'').trim();
    const confirmed=$('htbConfirm')?.checked===true;
    if(!target){
      setHtbStatus('Entre l’URL exacte de la machine HTB active.','err');
      $('htbTarget')?.focus();
      return;
    }
    if(!confirmed){
      setHtbStatus('Confirme d’abord que cette cible est bien ton lab Hack The Box autorisé.','err');
      return;
    }

    const button=$('htbStart');
    if(button)button.disabled=true;
    setHtbStatus('Vérification du runtime HTB…');
    try{
      const readiness=await api('/labs/htb/readiness');
      if(readiness?.live_scan_ready!==true){
        const failed=(Array.isArray(readiness?.checks)?readiness.checks:[])
          .filter(item=>item?.required===true&&item?.ok!==true);
        const labels=failed.slice(0,3)
          .map(item=>String(item?.label||item?.id||'contrôle'))
          .filter(Boolean);
        throw new Error(
          'Runtime HTB non prêt'+(labels.length?' · '+labels.join(' · '):'')
        );
      }
      setHtbStatus('Création de la campagne HTB à scope exact…');
      const campaign=await api('/labs/htb/campaigns',{
        method:'POST',
        body:JSON.stringify({
          target_url:target,
          authorized_lab:true,
          name:'Hack The Box Lab'
        })
      });
      const campaignId=String(campaign?.campaign_id||'');
      if(!campaignId)throw new Error('Le serveur n’a pas renvoyé d’identifiant de campagne.');
      try{localStorage.setItem(HTB_ACTIVE_KEY,campaignId);}catch(_error){}
      setHtbStatus('Campagne créée. Démarrage du recon borné…');
      const started=await api('/campaigns/'+encodeURIComponent(campaignId)+'/start',{
        method:'POST',
        body:'{}'
      });
      const kind=String(started?.job?.kind||'tâche');
      setHtbStatus(
        'Entraînement HTB lancé · '+kind+' · campagne '+campaignId+'.',
        'ok'
      );
      if($('htbConfirm'))$('htbConfirm').checked=false;
      $('htbFeedback')?.classList.remove('hidden');
      await refreshHtbSession({quiet:true});
    }catch(error){
      setHtbStatus('Entraînement HTB bloqué : '+error.message,'err');
    }finally{
      if(button)button.disabled=false;
    }
  }

  function parseTechniqueList(value){
    return [...new Set(
      String(value||'').split(',')
        .map(item=>item.trim().toLowerCase().replace(/\s+/g,'-'))
        .filter(Boolean)
    )].slice(0,20);
  }

  async function saveHtbLearning(){
    if(!requireToken())return;
    let campaignId='';
    try{campaignId=String(localStorage.getItem(HTB_ACTIVE_KEY)||'');}catch(_error){}
    if(!campaignId){
      setHtbStatus('Lance d’abord une campagne HTB depuis ce dashboard.','err');
      return;
    }
    const button=$('htbLearn');
    if(button)button.disabled=true;
    const solved=$('htbSolved')?.value!=='false';
    const successful=parseTechniqueList($('htbSuccessTechniques')?.value);
    const missed=parseTechniqueList($('htbMissedTechniques')?.value);
    try{
      const result=await api(
        '/labs/htb/campaigns/'+encodeURIComponent(campaignId)+'/finish',
        {
          method:'POST',
          body:JSON.stringify({
            solved,
            successful_techniques:successful,
            missed_techniques:missed,
            notes:''
          })
        }
      );
      const summary=await api(
        '/labs/htb/campaigns/'+encodeURIComponent(campaignId)+'/learning'
      );
      const globalSummary=await api('/labs/htb/learning');
      await refreshHtbBenchmark({quiet:true});
      await refreshHtbFocus({quiet:true});
      const techniques=Array.isArray(summary?.techniques)?summary.techniques:[];
      const globalTechniques=Array.isArray(globalSummary?.techniques)?globalSummary.techniques:[];
      const node=$('htbLearningStatus');
      if(node){
        node.textContent=
          String(result?.outcome?.learning_observations_written||0)+' signal(aux) ajouté(s) · '+
          techniques.length+' technique(s) dans ce lab · '+
          globalTechniques.length+' technique(s) globales sur '+
          String(globalSummary?.campaign_count||0)+' lab(s).';
      }
      try{localStorage.removeItem(HTB_ACTIVE_KEY);}catch(_error){}
      $('htbFeedback')?.classList.add('hidden');
      const session=$('htbSession');
      if(session)session.textContent='Session HTB : terminée et apprentissage enregistré.';
      setHtbStatus('Entraînement HTB terminé. Apprentissage enregistré sans payload ni secret.','ok');
    }catch(error){
      setHtbStatus('Apprentissage HTB bloqué : '+error.message,'err');
    }finally{
      if(button)button.disabled=false;
    }
  }

  async function cancelHtbLab(){
    if(!requireToken())return;
    let campaignId='';
    try{campaignId=String(localStorage.getItem(HTB_ACTIVE_KEY)||'');}catch(_error){}
    if(!campaignId){
      setHtbStatus('Aucune campagne HTB active sur cet appareil.','warn');
      return;
    }
    const button=$('htbCancel');
    if(button)button.disabled=true;
    try{
      await api('/campaigns/'+encodeURIComponent(campaignId)+'/cancel',{
        method:'POST',
        body:'{}'
      });
      try{localStorage.removeItem(HTB_ACTIVE_KEY);}catch(_error){}
      $('htbFeedback')?.classList.add('hidden');
      const session=$('htbSession');
      if(session)session.textContent='Session HTB : arrêtée sans apprentissage.';
      setHtbStatus('Campagne HTB arrêtée.','ok');
    }catch(error){
      if(Number(error?.status||0)===409&&String(error?.message||'').includes('Completed campaign')){
        try{localStorage.removeItem(HTB_ACTIVE_KEY);}catch(_error){}
        $('htbFeedback')?.classList.add('hidden');
        setHtbStatus('Campagne HTB déjà terminée.','ok');
      }else{
        setHtbStatus('Arrêt HTB impossible : '+error.message,'err');
      }
    }finally{
      if(button)button.disabled=false;
    }
  }

  async function refreshHtbSession({quiet=true}={}){
    const node=$('htbSession');
    if(!node||!token())return null;
    let campaignId='';
    try{campaignId=String(localStorage.getItem(HTB_ACTIVE_KEY)||'');}catch(_error){}
    if(!campaignId){
      node.textContent='Session HTB : aucune campagne active sur cet appareil.';
      $('htbFeedback')?.classList.add('hidden');
      return null;
    }
    try{
      const summary=await api(
        '/labs/htb/campaigns/'+encodeURIComponent(campaignId)+'/status'
      );
      const counts=summary?.job_counts||{};
      const state=String(summary?.state||'inconnu');
      const queued=Number(counts?.queued||0);
      const running=Number(counts?.running||0);
      const completed=Number(counts?.completed||0);
      const failed=Number(counts?.failed||0);
      const findings=Number(summary?.finding_count||0);
      const confirmed=Number(summary?.confirmed_finding_count||0);
      node.textContent=
        'Session HTB : '+state+
        ' · jobs '+running+' actif(s), '+queued+' en attente, '+completed+' terminé(s), '+failed+' échec(s)'+
        ' · findings '+findings+' ('+confirmed+' confirmé(s))'+
        (summary?.evaluated===true
          ?' · évaluation '+(summary?.solved===true?'résolue':'non résolue')
          :' · évaluation à renseigner');
      $('htbFeedback')?.classList.remove('hidden');
      return summary;
    }catch(error){
      if(Number(error?.status||0)===404){
        try{localStorage.removeItem(HTB_ACTIVE_KEY);}catch(_error){}
        node.textContent='Session HTB : campagne précédente introuvable.';
        $('htbFeedback')?.classList.add('hidden');
      }else if(!quiet){
        node.textContent='Session HTB indisponible : '+error.message;
      }
      return null;
    }
  }

  async function refreshHtbBenchmark({quiet=true}={}){
    const node=$('htbBenchmark');
    if(!node||!token())return null;
    try{
      const summary=await api('/labs/htb/benchmark');
      const evaluated=Number(summary?.evaluated_campaign_count||0);
      const solved=Number(summary?.solved_campaign_count||0);
      const solveRate=summary?.solve_rate;
      const techniqueRate=summary?.technique_success_rate;
      const confirmed=Number(summary?.confirmed_finding_count||0);
      if(!evaluated){
        node.textContent='Benchmark HTB : aucun lab évalué pour le moment.';
      }else{
        const solveText=solveRate===null||solveRate===undefined
          ?'—'
          :Math.round(Number(solveRate)*100)+'%';
        const techniqueText=techniqueRate===null||techniqueRate===undefined
          ?'—'
          :Math.round(Number(techniqueRate)*100)+'%';
        node.textContent=
          'Benchmark HTB : '+solved+'/'+evaluated+' lab(s) résolu(s) · '+
          'taux '+solveText+' · techniques '+techniqueText+' · '+
          confirmed+' finding(s) confirmé(s).';
      }
      return summary;
    }catch(error){
      if(!quiet)node.textContent='Benchmark HTB indisponible : '+error.message;
      return null;
    }
  }

  async function refreshHtbFocus({quiet=true}={}){
    const node=$('htbFocus');
    if(!node||!token())return null;
    try{
      const summary=await api('/labs/htb/focus?limit=3');
      const focus=Array.isArray(summary?.focus)?summary.focus:[];
      if(!focus.length){
        node.textContent='Prochain focus HTB : pas encore assez de feedback.';
        return summary;
      }
      node.textContent='Prochain focus HTB : '+
        focus.map(item=>{
          const rate=Math.round(Number(item?.success_rate||0)*100);
          return String(item?.technique||'technique')+
            ' · '+String(item?.failures||0)+' échec(s) · '+rate+'% réussite';
        }).join(' · ');
      return summary;
    }catch(error){
      if(!quiet)node.textContent='Focus HTB indisponible : '+error.message;
      return null;
    }
  }


  function openapiCategoryLabel(category){
    const labels={
      bola_idor_review:'BOLA / IDOR',
      ssrf_input_review:'Entrées URL / SSRF',
      auth_session_review:'Auth / session',
      sensitive_data_review:'Données sensibles'
    };
    return labels[String(category||'')]||String(category||'signal');
  }

  function renderOpenapiSummary(payload){
    const root=$('openapiSummary');
    if(!root)return;
    root.replaceChildren();

    const summary=payload?.summary||{};
    const review=summary?.review||{};

    const coverage=document.createElement('p');
    coverage.className='muted compact';
    const schemaLabel=String(payload?.schema||'preview inconnu');
    const sourceVersion=String(payload?.source_version||'version inconnue');
    coverage.textContent=
      'Spécification '+sourceVersion+' · '+schemaLabel+' · '+
      String(summary?.paths_seen||0)+' chemin(s) · '+
      String(summary?.cases_generated||0)+' opération(s) en lecture seule · '+
      String(summary?.mutating_operations_skipped||0)+' mutation(s) ignorée(s) · '+
      String(summary?.invalid_entries_skipped||0)+' entrée(s) invalide(s) ignorée(s) · '+
      String(payload?.network_requests_sent||0)+' requête(s) réseau.';
    root.appendChild(coverage);

    const headline=document.createElement('p');
    headline.className='muted compact';
    headline.textContent=
      String(review?.flagged_operations||0)+' opération(s) signalée(s) · '+
      String(review?.unflagged_operations||0)+' non signalée(s) · priorité max '+
      String(review?.max_review_priority||0)+'/100 · aucune vulnérabilité confirmée.';
    root.appendChild(headline);

    const categories=review?.category_counts&&typeof review.category_counts==='object'
      ?Object.entries(review.category_counts)
      :[];
    if(categories.length){
      const categoryLine=document.createElement('p');
      categoryLine.className='muted compact';
      categoryLine.textContent='Catégories : '+
        categories
          .sort((a,b)=>Number(b[1]||0)-Number(a[1]||0))
          .map(([name,count])=>openapiCategoryLabel(name)+' '+String(count))
          .join(' · ');
      root.appendChild(categoryLine);
    }

    const auth=payload?.summary?.authentication||{};
    const schemes=Array.isArray(auth?.security_schemes)?auth.security_schemes:[];
    const referenced=Array.isArray(auth?.referenced_scheme_names)?auth.referenced_scheme_names:[];
    const unknown=Array.isArray(auth?.unknown_scheme_references)?auth.unknown_scheme_references:[];
    const publicOverrides=Array.isArray(auth?.explicit_public_overrides)?auth.explicit_public_overrides:[];
    const unauthenticated=Array.isArray(auth?.sensitive_unauthenticated_operations)
      ?auth.sensitive_unauthenticated_operations
      :[];

    const authHeadline=document.createElement('p');
    authHeadline.className='muted compact';
    authHeadline.textContent=
      'Auth déclarée : '+String(auth?.defined_scheme_count||0)+' schéma(s) · '+
      String(referenced.length)+' référencé(s) · '+
      String(publicOverrides.length)+' override(s) public(s) · '+
      String(unauthenticated.length)+' opération(s) sensible(s) sans auth.';
    root.appendChild(authHeadline);

    if(schemes.length){
      const schemeLine=document.createElement('p');
      schemeLine.className='muted compact';
      schemeLine.textContent='Schémas : '+
        schemes.slice(0,12).map(item=>{
          const parts=[String(item?.name||'schéma'),String(item?.type||'type inconnu')];
          if(item?.scheme)parts.push(String(item.scheme));
          if(Array.isArray(item?.oauth_flows)&&item.oauth_flows.length){
            parts.push(item.oauth_flows.join('/'));
          }
          return parts.join(' · ');
        }).join(' | ');
      root.appendChild(schemeLine);
    }

    if(unknown.length){
      const warning=document.createElement('p');
      warning.className='muted compact state-review';
      warning.textContent='Références auth inconnues : '+unknown.slice(0,12).join(', ')+'.';
      root.appendChild(warning);
    }

    if(publicOverrides.length){
      const publicLine=document.createElement('p');
      publicLine.className='muted compact state-review';
      publicLine.textContent='Overrides publics : '+
        publicOverrides.slice(0,12).map(item=>
          String(item?.method||'GET')+' '+String(item?.path||'/')
        ).join(' · ');
      root.appendChild(publicLine);
    }

    if(unauthenticated.length){
      const unauthLine=document.createElement('p');
      unauthLine.className='muted compact state-review';
      unauthLine.textContent='Surfaces sensibles sans auth : '+
        unauthenticated.slice(0,12).map(item=>
          String(item?.method||'GET')+' '+String(item?.path||'/')
        ).join(' · ');
      root.appendChild(unauthLine);
    }

    const cases=Array.isArray(payload?.cases)?payload.cases:[];
    const caseByOperation=new Map(
      cases.map(item=>[
        String(item?.method||'').toUpperCase()+' '+String(item?.path||''),
        item,
      ])
    );
    const prioritized=Array.isArray(review?.top_review_operations)
      ?review.top_review_operations.slice(0,10)
      :[];
    const visibleOperations=prioritized.length
      ?prioritized
      :cases.slice(0,10);
    for(const item of visibleOperations){
      const row=document.createElement('div');
      row.className='simple-log';
      const method=String(item?.method||'GET').toUpperCase();
      const path=String(item?.path||'/');
      const operationCase=caseByOperation.get(method+' '+path)||item;
      const head=document.createElement('strong');
      head.textContent=
        method+' '+path+
        ' · priorité '+String(item?.review_priority||operationCase?.review_priority||0)+'/100';
      row.appendChild(head);
      const reasons=Array.isArray(item?.review_priority_reasons)
        ?item.review_priority_reasons.map(openapiCategoryLabel)
        :[];
      if(reasons.length){
        const detail=document.createElement('div');
        detail.className='muted compact';
        detail.textContent=reasons.join(' · ');
        row.appendChild(detail);
      }

      const metadataParts=[];
      if(operationCase?.operation_id){
        metadataParts.push('operationId '+String(operationCase.operation_id));
      }
      const operationTags=Array.isArray(operationCase?.tags)
        ?operationCase.tags.slice(0,6)
        :[];
      if(operationTags.length){
        metadataParts.push('tags '+operationTags.join(', '));
      }
      if(operationCase?.explicitly_public===true){
        metadataParts.push('public explicite');
      }else if(operationCase?.authentication_declared===true){
        metadataParts.push('auth déclarée');
      }
      if(metadataParts.length){
        const metadataDetail=document.createElement('div');
        metadataDetail.className='muted compact';
        metadataDetail.textContent=metadataParts.join(' · ');
        row.appendChild(metadataDetail);
      }

      const requestTypes=Array.isArray(operationCase?.request_content_types)
        ?operationCase.request_content_types.slice(0,8)
        :[];
      if(requestTypes.length||operationCase?.request_body_required===true){
        const requestDetail=document.createElement('div');
        requestDetail.className='muted compact';
        const requestParts=[];
        if(requestTypes.length){
          requestParts.push('Entrée : '+requestTypes.join(', '));
        }
        if(operationCase?.request_body_required===true){
          requestParts.push('body requis');
        }
        requestDetail.textContent=requestParts.join(' · ');
        row.appendChild(requestDetail);
      }

      const responseTypes=Array.isArray(operationCase?.response_content_types)
        ?operationCase.response_content_types.slice(0,8)
        :[];
      const responseCodes=Array.isArray(operationCase?.response_codes)
        ?operationCase.response_codes.slice(0,12)
        :[];
      if(responseTypes.length||responseCodes.length){
        const responseDetail=document.createElement('div');
        responseDetail.className='muted compact';
        const responseParts=[];
        if(responseCodes.length){
          responseParts.push('Codes : '+responseCodes.join(', '));
        }
        if(responseTypes.length){
          responseParts.push('Sortie : '+responseTypes.join(', '));
        }
        responseDetail.textContent=responseParts.join(' · ');
        row.appendChild(responseDetail);
      }
      root.appendChild(row);
    }
  }

  const OPENAPI_FILE_MAX_BYTES=2*1024*1024;

  function formatOpenapiFileSize(bytes){
    const value=Math.max(0,Number(bytes||0));
    if(value<1024)return Math.round(value)+' o';
    if(value<1024*1024)return (value/1024).toFixed(value<10*1024?1:0)+' Kio';
    return (value/(1024*1024)).toFixed(2)+' Mio';
  }

  function validOpenapiDocument(value){
    return Boolean(
      value
      && typeof value==='object'
      && !Array.isArray(value)
      && String(value.openapi||value.swagger||'').trim()
      && value.paths
      && typeof value.paths==='object'
      && !Array.isArray(value.paths)
    );
  }

  function clearOpenapiReview(){
    const file=$('openapiFile');
    const documentInput=$('openapiDocument');
    const fileStatus=$('openapiFileStatus');
    const status=$('openapiStatus');
    if(file)file.value='';
    if(documentInput)documentInput.value='';
    $('openapiSummary')?.replaceChildren();
    if(fileStatus)fileStatus.textContent='Fichier JSON optionnel · 2 Mio maximum · lecture locale uniquement.';
    if(status){
      status.textContent='Aucune spécification analysée.';
      status.className='simple-status muted';
    }
  }

  async function loadOpenapiFile(){
    const input=$('openapiFile');
    const status=$('openapiFileStatus');
    const file=input?.files?.[0];
    if(!file)return;
    const name=String(file.name||'').toLowerCase();
    const type=String(file.type||'').toLowerCase();
    if(!(name.endsWith('.json')||type==='application/json')){
      if(status)status.textContent='Fichier refusé : JSON uniquement.';
      if(input)input.value='';
      return;
    }
    if(Number(file.size||0)>OPENAPI_FILE_MAX_BYTES){
      if(status)status.textContent='Fichier refusé : taille maximale 2 Mio.';
      if(input)input.value='';
      return;
    }
    try{
      const text=await file.text();
      const parsed=JSON.parse(text);
      if(!validOpenapiDocument(parsed)){
        if(status)status.textContent='Fichier refusé : document OpenAPI/Swagger incomplet.';
        if(input)input.value='';
        return;
      }
      const target=$('openapiDocument');
      if(target)target.value=text;
      $('openapiSummary')?.replaceChildren();
      const analysisStatus=$('openapiStatus');
      if(analysisStatus){
        analysisStatus.textContent='Spécification valide · prête à analyser.';
        analysisStatus.className='simple-status ok';
      }
      if(status)status.textContent=
        'Fichier prêt · '+String(file.name||'openapi.json')+
        ' · '+formatOpenapiFileSize(file.size)+'.';
    }catch(_error){
      if(status)status.textContent='Fichier refusé : JSON invalide ou illisible.';
      if(input)input.value='';
    }
  }

  async function analyzeOpenapi(){
    if(!requireToken())return;
    const input=$('openapiDocument');
    const button=$('openapiAnalyze');
    const status=$('openapiStatus');
    const raw=String(input?.value||'').trim();
    if(!raw){
      if(status){
        status.textContent='Colle d’abord une spécification OpenAPI/Swagger JSON.';
        status.className='simple-status err';
      }
      input?.focus();
      return;
    }

    let documentValue;
    try{
      documentValue=JSON.parse(raw);
      if(!validOpenapiDocument(documentValue)){
        if(status){
          status.textContent='Document OpenAPI/Swagger incomplet : version et paths requis.';
          status.className='simple-status err';
        }
        return;
      }
    }catch(_error){
      if(status){
        status.textContent='JSON invalide. Corrige la spécification avant analyse.';
        status.className='simple-status err';
      }
      return;
    }

    if(button)button.disabled=true;
    if(status){
      status.textContent='Analyse passive de la spécification…';
      status.className='simple-status muted';
    }
    try{
      const result=await api('/testing/openapi/preview',{
        method:'POST',
        body:JSON.stringify({document:documentValue})
      });
      renderOpenapiSummary(result);
      const generated=Number(result?.summary?.cases_generated||0);
      if(status){
        status.textContent=
          'Analyse terminée · '+generated+
          ' opération(s) lecture seule · 0 requête envoyée vers la cible.';
        status.className='simple-status ok';
      }
    }catch(error){
      $('openapiSummary')?.replaceChildren();
      if(status){
        status.textContent='Analyse OpenAPI impossible : '+error.message;
        status.className='simple-status err';
      }
    }finally{
      if(button)button.disabled=false;
    }
  }

  function bind(){
    try{$('token').value=localStorage.getItem(TOKEN_KEY)||'';}catch(_error){}
    const versionNode=$('buildVersion');
    if(versionNode)versionNode.textContent='Interface '+UI_VERSION;
    if('serviceWorker' in navigator){
      navigator.serviceWorker.register('/sw.js?v=98',{updateViaCache:'none'})
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
    $('htbStart')?.addEventListener('click',()=>void startHtbLab());
    $('htbLearn')?.addEventListener('click',()=>void saveHtbLearning());
    $('htbCancel')?.addEventListener('click',()=>void cancelHtbLab());
    $('openapiAnalyze')?.addEventListener('click',()=>void analyzeOpenapi());
    $('openapiFile')?.addEventListener('change',()=>void loadOpenapiFile());
    $('openapiClear')?.addEventListener('click',clearOpenapiReview);
    try{
      if(localStorage.getItem(HTB_ACTIVE_KEY))$('htbFeedback')?.classList.remove('hidden');
    }catch(_error){}
    window.addEventListener('unhandledrejection',event=>{
      const message=event?.reason?.message||String(event?.reason||'Erreur JavaScript');
      setStatus('Erreur interface : '+message,'err');
    });
    window.addEventListener('error',event=>{
      if(event?.message)setStatus('Erreur interface : '+event.message,'err');
    });
    void refreshRuntimeReadiness({quiet:true});
    void refreshBrowserReadiness({quiet:true});
    void refreshJournal({quiet:true});
    void refreshHtbBenchmark({quiet:true});
    void refreshHtbFocus({quiet:true});
    void refreshHtbSession({quiet:true});
    timer=setInterval(()=>{
      void refreshRuntimeReadiness({quiet:true});
      void refreshBrowserReadiness({quiet:true});
      void refreshJournal({quiet:true});
      void refreshHtbSession({quiet:true});
    },15000);
  }

  window.addEventListener('beforeunload',()=>{if(timer)clearInterval(timer);});
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',bind,{once:true});
  }else{
    bind();
  }
})();
