(()=>{
  let approvedPreview=null;
  let remoteBinding=null;
  let hackerOnePrograms=[];
  let runMonitorTimer=null;
  let runMonitorCampaignId=null;
  let runMonitorBusy=false;

  const el=id=>document.getElementById(id);
  const splitLines=value=>value.split('\n').map(item=>item.trim()).filter(Boolean);
  const launcherFields=[
    'h1Name','h1Url','h1ScopeJson','h1Auth','h1PolicyVersion','h1ReviewedAt',
    'h1ReviewedBy','h1SafeHarbor','h1Automation','h1Rps','h1TestAccountRequired',
    'h1TestAccountConstraints','h1AdditionalRestrictions','h1Notes'
  ];

  function setLauncherStatus(message,type='muted'){
    if(typeof setStatus==='function')setStatus(message,type);
  }

  function setConnectionState(label,type=''){
    const state=el('h1ConnectionState');
    state.textContent=label;
    state.className='pill'+(type?' '+type:'');
  }

  function stopRunMonitor(){
    if(runMonitorTimer!==null){
      clearInterval(runMonitorTimer);
      runMonitorTimer=null;
    }
    runMonitorCampaignId=null;
    runMonitorBusy=false;
  }

  function renderRunMonitor(campaignData,control,artifacts){
    const panel=el('h1RunPanel');
    panel.classList.remove('hidden');
    const state=String(campaignData?.state||control?.campaign_state||'unknown');
    const pill=el('h1RunState');
    pill.textContent=state;
    pill.className='pill '+(
      state==='completed'?'ok':
      state==='failed'||state==='cancelled'?'err':'warn'
    );

    const jobs=control?.jobs||{};
    const queued=Number(jobs.queued)||0;
    const running=Number(jobs.running)||0;
    const failed=Number(jobs.failed)||0;
    el('h1RunJobs').textContent=queued+' file · '+running+' actif · '+failed+' échec';
    el('h1RunFindings').textContent=String(
      Array.isArray(campaignData?.findings)?campaignData.findings.length:0
    );
    el('h1RunArtifacts').textContent=String(Array.isArray(artifacts)?artifacts.length:0);
    el('h1RunUpdated').textContent='Actualisé à '+new Date().toLocaleTimeString();
  }

  async function refreshRunMonitor(campaignId){
    if(runMonitorBusy||!campaignId)return;
    runMonitorBusy=true;
    try{
      const encoded=encodeURIComponent(campaignId);
      const [campaignData,control,artifacts]=await Promise.all([
        api('/campaigns/'+encodeURIComponent(campaignId)),
        api('/campaigns/'+encodeURIComponent(campaignId)+'/control-status'),
        api('/campaigns/'+encodeURIComponent(campaignId)+'/artifacts')
      ]);
      renderRunMonitor(campaignData,control,artifacts);
      if(typeof refreshDashboard==='function'&&campaign?.id===campaignId){
        await refreshDashboard();
      }
      if(['completed','cancelled','failed'].includes(String(campaignData?.state||''))){
        stopRunMonitor();
      }
      return {campaign:campaignData,control,artifacts,encoded};
    }catch(error){
      el('h1RunPanel').classList.remove('hidden');
      el('h1RunState').textContent='indisponible';
      el('h1RunState').className='pill err';
      el('h1RunUpdated').textContent='Suivi interrompu temporairement : '+error.message;
    }finally{
      runMonitorBusy=false;
    }
  }

  function startRunMonitor(campaignId){
    stopRunMonitor();
    runMonitorCampaignId=String(campaignId||'');
    if(!runMonitorCampaignId)return;
    void refreshRunMonitor(runMonitorCampaignId);
    runMonitorTimer=setInterval(()=>{
      if(runMonitorCampaignId)void refreshRunMonitor(runMonitorCampaignId);
    },5000);
  }

  function clearRemoteBinding(){
    remoteBinding=null;
    el('h1RemoteFingerprint').textContent='Fingerprint distant : —';
    el('h1ProgramMeta').textContent='Snapshot distant détaché. Le formulaire reste utilisable en mode manuel.';
    el('h1ScopeTable').textContent='—';
    el('h1ScopeExclusions').textContent='—';
    invalidatePreview();
  }

  function renderProgramOptions(){
    const select=el('h1ProgramSelect');
    const current=select.value;
    const query=el('h1ProgramSearch').value.trim().toLowerCase();
    select.replaceChildren();
    const manual=document.createElement('option');
    manual.value='';
    manual.textContent='Mode manuel / aucun programme chargé';
    select.appendChild(manual);
    for(const program of hackerOnePrograms){
      const haystack=(String(program.name||'')+' '+String(program.handle||'')).toLowerCase();
      if(query&&!haystack.includes(query))continue;
      const option=document.createElement('option');
      option.value=String(program.handle||'');
      option.textContent=String(program.name||program.handle)+' ('+String(program.handle)+')';
      select.appendChild(option);
    }
    if([...select.options].some(option=>option.value===current))select.value=current;
    el('h1LoadProgram').disabled=!select.value;
  }

  function renderRemoteScope(snapshot){
    const preview=snapshot.preview||{};
    const assets=Array.isArray(preview.assets)?preview.assets:[];
    const table=el('h1ScopeTable');
    table.replaceChildren();
    if(!assets.length){
      table.textContent='Aucun asset retourné.';
    }else{
      for(const asset of assets){
        const row=document.createElement('div');
        row.className='scope-asset-row';
        const identity=document.createElement('code');
        identity.textContent=String(asset.identifier||'—');
        const meta=document.createElement('span');
        const eligibility=asset.eligible_for_submission?'in scope':'out of scope';
        const compatibility=asset.compatible?'compatible':'bloqué';
        meta.textContent=String(asset.asset_type||'asset')+' · '+eligibility+' · '+compatibility;
        row.append(identity,meta);
        table.appendChild(row);
      }
    }

    const exclusions=el('h1ScopeExclusions');
    exclusions.replaceChildren();
    const records=Array.isArray(snapshot.scope_exclusions)?snapshot.scope_exclusions:[];
    if(!records.length){
      exclusions.textContent='Aucune exclusion structurée retournée.';
    }else{
      for(const record of records){
        const item=document.createElement('div');
        item.className='scope-exclusion-row';
        const attrs=record&&typeof record==='object'&&record.attributes&&typeof record.attributes==='object'
          ?record.attributes:{};
        item.textContent=String(attrs.details||attrs.category||record.id||'Exclusion HackerOne');
        exclusions.appendChild(item);
      }
    }
  }

  async function loadRemoteProgram(){
    const handle=el('h1ProgramSelect').value;
    if(!handle){
      clearRemoteBinding();
      return;
    }
    try{
      el('h1LoadProgram').disabled=true;
      setLauncherStatus('Chargement du programme HackerOne…');
      const snapshot=await api('/imports/hackerone/programs/'+encodeURIComponent(handle)+'/snapshot');
      remoteBinding={
        handle:String(snapshot.handle),
        snapshot_sha256:String(snapshot.snapshot_sha256)
      };
      el('h1ScopeJson').value=JSON.stringify(snapshot.document,null,2);
      if(snapshot.program?.name)el('h1Name').value=String(snapshot.program.name).slice(0,120);
      const program=snapshot.program||{};
      const meta=[
        String(program.name||snapshot.handle),
        'soumissions: '+String(program.submission_state||'—'),
        'bounties: '+(program.offers_bounties===true?'oui':program.offers_bounties===false?'non':'—'),
        'Gold Safe Harbor: '+(program.gold_standard_safe_harbor===true?'oui':program.gold_standard_safe_harbor===false?'non':'—')
      ];
      el('h1ProgramMeta').textContent=meta.join(' · ')+(program.policy?' · Policy distante chargée; autorisation de scan à confirmer manuellement.':'');
      el('h1RemoteFingerprint').textContent='Fingerprint distant : '+remoteBinding.snapshot_sha256;
      renderRemoteScope(snapshot);
      invalidatePreview();
      setLauncherStatus('Programme HackerOne chargé. Vérifie la policy, le débit autorisé et la cible principale avant prévisualisation.','ok');
    }catch(error){
      clearRemoteBinding();
      setLauncherStatus(error.message,'err');
    }finally{
      el('h1LoadProgram').disabled=!el('h1ProgramSelect').value;
    }
  }

  async function initRemoteControlCenter(){
    try{
      const connection=await api('/imports/hackerone/connection');
      if(!connection?.configured){
        setConnectionState('non configuré','warn');
        el('h1ProgramSearch').disabled=true;
        el('h1ProgramSelect').disabled=true;
        el('h1LoadProgram').disabled=true;
        return;
      }
      setConnectionState('connecté','ok');
      el('h1ProgramSearch').disabled=false;
      el('h1ProgramSelect').disabled=false;
      const result=await api('/imports/hackerone/programs');
      hackerOnePrograms=Array.isArray(result?.programs)?result.programs:[];
      renderProgramOptions();
    }catch(error){
      setConnectionState('indisponible','err');
      el('h1ProgramSearch').disabled=true;
      el('h1ProgramSelect').disabled=true;
      el('h1LoadProgram').disabled=true;
      setLauncherStatus('HackerOne API indisponible : '+error.message+'. Le mode manuel reste disponible.','err');
    }
  }

  function parseScopeDocument(){
    const raw=el('h1ScopeJson').value.trim();
    if(!raw)throw new Error('StructuredScope JSON requis.');
    let document;
    try{document=JSON.parse(raw)}catch{throw new Error('StructuredScope JSON invalide.');}
    if(!document||Array.isArray(document)||typeof document!=='object'){
      throw new Error('StructuredScope doit être un objet JSON.');
    }
    return document;
  }

  function reviewedAtIso(){
    const raw=el('h1ReviewedAt').value.trim();
    if(!raw)throw new Error('Date de revue de la policy requise.');
    const parsed=new Date(raw);
    if(Number.isNaN(parsed.getTime()))throw new Error('Date de revue de la policy invalide.');
    return parsed.toISOString();
  }

  function buildPolicy(){
    const authorizationReference=el('h1Auth').value.trim();
    const policyVersion=el('h1PolicyVersion').value.trim();
    const reviewedBy=el('h1ReviewedBy').value.trim();
    const rps=Number(el('h1Rps').value);
    if(authorizationReference.length<3)throw new Error("Référence d'autorisation requise.");
    if(!policyVersion)throw new Error('Version ou date de policy requise.');
    if(!reviewedBy)throw new Error('Nom ou pseudo du relecteur requis.');
    if(!Number.isFinite(rps)||rps<=0||rps>20){
      throw new Error('La limite req/s doit être un nombre entre 0 et 20.');
    }
    return {
      authorization_reference:authorizationReference,
      policy_version:policyVersion,
      reviewed_at:reviewedAtIso(),
      reviewed_by:reviewedBy,
      safe_harbor_confirmed:el('h1SafeHarbor').checked,
      automated_scanning:el('h1Automation').checked,
      max_requests_per_second:rps,
      test_account_required:el('h1TestAccountRequired').checked,
      test_account_constraints:el('h1TestAccountConstraints').value.trim(),
      additional_restrictions:splitLines(el('h1AdditionalRestrictions').value),
      program_notes:el('h1Notes').value.trim()
    };
  }

  function buildPayload(){
    const name=el('h1Name').value.trim();
    const primaryUrl=el('h1Url').value.trim();
    if(name.length<2)throw new Error('Nom du programme requis.');
    if(!primaryUrl)throw new Error('URL principale requise.');
    try{new URL(primaryUrl)}catch{throw new Error('URL principale invalide.');}
    const payload={
      document:parseScopeDocument(),
      policy:buildPolicy(),
      target:{name,primary_url:primaryUrl}
    };
    if(remoteBinding){
      payload.remote_handle=remoteBinding.handle;
      payload.remote_snapshot_sha256=remoteBinding.snapshot_sha256;
    }
    return payload;
  }

  function conservativeBlockers(policy){
    const blockers=[];
    if(!policy.safe_harbor_confirmed)blockers.push('Safe Harbor / autorisation non confirmé');
    if(!policy.automated_scanning)blockers.push('automatisation non autorisée explicitement');
    if(policy.test_account_required)blockers.push('workflow de compte de test requis');
    if(policy.test_account_constraints)blockers.push('contraintes de compte nécessitant une application manuelle');
    if(policy.additional_restrictions.length)blockers.push('restrictions additionnelles nécessitant une application manuelle');
    return blockers;
  }

  function payloadFingerprint(payload){
    return JSON.stringify(payload);
  }

  function invalidatePreview(){
    approvedPreview=null;
    el('h1Confirm').checked=false;
    el('h1Confirm').disabled=true;
    el('h1Launch').disabled=true;
    const state=el('h1PreviewState');
    if(state){
      state.textContent='à revérifier';
      state.className='pill warn';
    }
  }

  function renderScopeList(targetId,values,emptyLabel){
    const target=el(targetId);
    target.replaceChildren();
    if(!Array.isArray(values)||!values.length){
      target.textContent=emptyLabel;
      return;
    }
    for(const value of values){
      const item=document.createElement('code');
      item.textContent=value;
      target.appendChild(item);
    }
  }

  function renderPreview(preview,payload,blockers){
    el('h1PreviewCard').classList.remove('hidden');
    const rules=preview.rules||{};
    renderScopeList('h1AllowedPreview',rules.allowed_targets,'Aucune cible autorisée');
    renderScopeList('h1DeniedPreview',rules.denied_targets,'Aucune exclusion explicite');

    const policy=preview.policy_snapshot||payload.policy;
    const message=[
      'Policy '+String(policy.policy_version||'—'),
      'revue par '+String(policy.reviewed_by||'—'),
      String(rules.max_requests_per_second||policy.max_requests_per_second||'—')+' req/s',
      'capacités destructives verrouillées OFF'
    ];
    if(blockers.length)message.push('blocage: '+blockers.join(' · '));
    el('h1PolicyPreview').textContent=message.join(' · ');

    const accepted=Boolean(preview.complete)&&blockers.length===0;
    const state=el('h1PreviewState');
    state.textContent=accepted?'admis':'revue manuelle requise';
    state.className='pill '+(accepted?'ok':'warn');
    el('h1Confirm').disabled=!accepted;
    if(accepted){
      approvedPreview=payloadFingerprint(payload);
      setLauncherStatus('Scope et policy vérifiés. Confirme la prévisualisation puis saisis un nouveau TOTP pour lancer.','ok');
    }else{
      approvedPreview=null;
      el('h1Launch').disabled=true;
      setLauncherStatus('Lancement bloqué : '+(blockers.join(' · ')||'scope incomplet ou incompatible')+'.','err');
    }
  }

  async function preview(){
    try{
      const payload=buildPayload();
      const blockers=conservativeBlockers(payload.policy);
      el('h1Preview').disabled=true;
      setLauncherStatus('Vérification HackerOne en cours…');
      const previewPayload={document:payload.document,policy:payload.policy};
      if(payload.remote_handle){
        previewPayload.remote_handle=payload.remote_handle;
        previewPayload.remote_snapshot_sha256=payload.remote_snapshot_sha256;
      }
      const result=await api('/imports/hackerone/rules-preview',{
        method:'POST',
        body:JSON.stringify(previewPayload)
      });
      renderPreview(result,payload,blockers);
      el('output').textContent=JSON.stringify(result,null,2);
    }catch(error){
      invalidatePreview();
      el('h1PreviewCard').classList.remove('hidden');
      setLauncherStatus(error.message,'err');
    }finally{
      el('h1Preview').disabled=false;
    }
  }

  async function launch(){
    try{
      const payload=buildPayload();
      const current=payloadFingerprint(payload);
      if(!approvedPreview||current!==approvedPreview){
        throw new Error('Le formulaire a changé : relance la vérification du scope et de la policy.');
      }
      if(!el('h1Confirm').checked)throw new Error('Confirmation de la prévisualisation requise.');
      const blockers=conservativeBlockers(payload.policy);
      if(blockers.length)throw new Error('Lancement conservateur bloqué : '+blockers.join(' · '));

      el('h1Launch').disabled=true;
      el('h1Preview').disabled=true;
      setLauncherStatus('Admission et démarrage HackerOne…');
      const result=await api('/imports/hackerone/campaigns/launch',{
        method:'POST',
        body:JSON.stringify(payload)
      });
      approvedPreview=null;
      el('h1Confirm').checked=false;
      el('h1Confirm').disabled=true;
      el('output').textContent=JSON.stringify(result,null,2);
      await activateCampaign(result.campaign);
      startRunMonitor(result.campaign.id);
      setLauncherStatus('Campagne HackerOne admise et démarrée avec policy liée.','ok');
    }catch(error){
      setLauncherStatus(error.message,'err');
      if(approvedPreview&&el('h1Confirm').checked)el('h1Launch').disabled=false;
    }finally{
      el('h1Preview').disabled=false;
    }
  }

  async function importScopeFile(){
    const file=el('h1ScopeFile').files?.[0];
    if(!file)return;
    try{
      if(file.size>2_000_000)throw new Error('Fichier scope trop volumineux (maximum local 2 Mo).');
      const text=await file.text();
      const parsed=JSON.parse(text);
      if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')throw new Error('Export scope invalide.');
      el('h1ScopeJson').value=JSON.stringify(parsed,null,2);
      clearRemoteBinding();
      setLauncherStatus('Export StructuredScope chargé. Vérification requise avant lancement.');
    }catch(error){
      el('h1ScopeFile').value='';
      setLauncherStatus(error.message,'err');
    }
  }

  for(const id of launcherFields){
    const node=el(id);
    node.addEventListener('input',invalidatePreview);
    node.addEventListener('change',invalidatePreview);
  }
  el('h1ScopeJson').addEventListener('input',()=>{
    if(remoteBinding)clearRemoteBinding();
  });
  el('h1ProgramSearch').addEventListener('input',renderProgramOptions);
  el('h1ProgramSelect').addEventListener('change',()=>{
    el('h1LoadProgram').disabled=!el('h1ProgramSelect').value;
  });
  el('h1LoadProgram').addEventListener('click',loadRemoteProgram);
  el('h1ScopeFile').addEventListener('change',importScopeFile);
  el('h1Preview').addEventListener('click',preview);
  el('h1Confirm').addEventListener('change',()=>{
    el('h1Launch').disabled=!(approvedPreview&&el('h1Confirm').checked);
  });
  el('h1Launch').addEventListener('click',launch);
  el('token').addEventListener('change',initRemoteControlCenter);
  initRemoteControlCenter();
})();
