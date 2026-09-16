(()=>{
  let approvedPreview=null;

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
    return {
      document:parseScopeDocument(),
      policy:buildPolicy(),
      target:{name,primary_url:primaryUrl}
    };
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
      const result=await api('/imports/hackerone/rules-preview',{
        method:'POST',
        body:JSON.stringify({document:payload.document,policy:payload.policy})
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
      invalidatePreview();
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
  el('h1ScopeFile').addEventListener('change',importScopeFile);
  el('h1Preview').addEventListener('click',preview);
  el('h1Confirm').addEventListener('change',()=>{
    el('h1Launch').disabled=!(approvedPreview&&el('h1Confirm').checked);
  });
  el('h1Launch').addEventListener('click',launch);
})();
