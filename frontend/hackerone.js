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

  function reviewField(labelText,control,name){
    const label=document.createElement('label');
    label.className='h1-review-field';
    const caption=document.createElement('span');
    caption.textContent=labelText;
    control.dataset.reviewField=name;
    label.append(caption,control);
    return label;
  }

  function reviewValue(editor,name){
    const control=editor.querySelector('[data-review-field="'+name+'"]');
    return String(control?.value||'').trim();
  }

  async function saveFindingReviewMetadata(findingId,editor){
    if(!runMonitorCampaignId)return false;
    const status=editor.querySelector('[data-review-status]');
    const reviewer=reviewValue(editor,'reviewer');
    const cvss=Number(reviewValue(editor,'cvss'));
    const payload={
      summary:reviewValue(editor,'summary'),
      impact:reviewValue(editor,'impact'),
      reproduction_steps:splitLines(reviewValue(editor,'reproduction_steps')),
      remediation:reviewValue(editor,'remediation'),
      cwe:reviewValue(editor,'cwe').toUpperCase(),
      cvss,
      reviewer
    };
    if(!payload.summary||!payload.impact||!payload.reproduction_steps.length||!payload.remediation||!payload.cwe||!reviewer){
      status.textContent='Tous les champs de revue sont requis avant sauvegarde.';
      status.className='muted compact err-text';
      return false;
    }
    if(!Number.isFinite(cvss)||cvss<0||cvss>10){
      status.textContent='CVSS doit être compris entre 0 et 10.';
      status.className='muted compact err-text';
      return false;
    }
    try{
      status.textContent='Sauvegarde de la revue humaine…';
      status.className='muted compact';
      await api(
        '/campaigns/'+encodeURIComponent(runMonitorCampaignId)+
        '/findings/'+encodeURIComponent(findingId)+'/review-metadata',
        {method:'PUT',body:JSON.stringify(payload)}
      );
      status.textContent='Métadonnées HackerOne sauvegardées. La confirmation reste une action séparée.';
      status.className='muted compact ok-text';
      await refreshRunMonitor(runMonitorCampaignId);
      return true;
    }catch(error){
      status.textContent='Sauvegarde impossible : '+error.message;
      status.className='muted compact err-text';
      return false;
    }
  }

  async function resolveHackerOneFinding(findingId,confirmed,editor){
    if(!runMonitorCampaignId)return;
    const reviewer=reviewValue(editor,'reviewer');
    const status=editor.querySelector('[data-review-status]');
    if(!reviewer){
      status.textContent='Nom ou pseudo du relecteur requis.';
      status.className='muted compact err-text';
      return;
    }
    try{
      const decision=confirmed?'confirmation':'rejet';
      status.textContent='Enregistrement de la '+decision+' humaine…';
      status.className='muted compact';
      await api(
        '/campaigns/'+encodeURIComponent(runMonitorCampaignId)+
        '/findings/'+encodeURIComponent(findingId)+'/validate?confirmed='+
        String(Boolean(confirmed))+'&validator='+encodeURIComponent(reviewer),
        {method:'POST'}
      );
      status.textContent=confirmed?'Finding confirmé par revue humaine.':'Finding rejeté par revue humaine.';
      status.className='muted compact ok-text';
      await refreshRunMonitor(runMonitorCampaignId);
    }catch(error){
      status.textContent='Décision refusée : '+error.message;
      status.className='muted compact err-text';
    }
  }

  function buildFindingReviewEditor(finding,readiness){
    const details=document.createElement('details');
    details.className='h1-review-editor';
    const summary=document.createElement('summary');
    summary.textContent='Revue humaine et métadonnées HackerOne';
    details.appendChild(summary);

    const grid=document.createElement('div');
    grid.className='h1-review-grid';

    const reviewer=document.createElement('input');
    reviewer.type='text';
    reviewer.maxLength=120;
    reviewer.value=String(finding.validated_by||el('h1ReviewedBy').value||'');
    grid.appendChild(reviewField('Relecteur',reviewer,'reviewer'));

    const summaryInput=document.createElement('textarea');
    summaryInput.rows=3;
    summaryInput.maxLength=8000;
    summaryInput.value=String(finding.summary||'');
    grid.appendChild(reviewField('Résumé',summaryInput,'summary'));

    const impact=document.createElement('textarea');
    impact.rows=3;
    impact.maxLength=8000;
    impact.value=String(finding.impact||'');
    grid.appendChild(reviewField('Impact',impact,'impact'));

    const reproduction=document.createElement('textarea');
    reproduction.rows=4;
    reproduction.value=Array.isArray(finding.reproduction_steps)?finding.reproduction_steps.join('\n'):'';
    reproduction.placeholder='Une étape par ligne';
    grid.appendChild(reviewField('Étapes de reproduction',reproduction,'reproduction_steps'));

    const remediation=document.createElement('textarea');
    remediation.rows=3;
    remediation.maxLength=8000;
    remediation.value=String(finding.remediation||'');
    grid.appendChild(reviewField('Remédiation',remediation,'remediation'));

    const cwe=document.createElement('input');
    cwe.type='text';
    cwe.placeholder='CWE-200';
    cwe.value=String(finding.cwe||'');
    grid.appendChild(reviewField('CWE',cwe,'cwe'));

    const cvss=document.createElement('input');
    cvss.type='number';
    cvss.min='0';
    cvss.max='10';
    cvss.step='0.1';
    cvss.inputMode='decimal';
    cvss.value=finding.cvss===null||finding.cvss===undefined?'':String(finding.cvss);
    grid.appendChild(reviewField('CVSS',cvss,'cvss'));

    details.appendChild(grid);

    const blockers=document.createElement('p');
    blockers.className='muted compact';
    const metadataBlockers=Array.isArray(readiness?.metadata_blockers)?readiness.metadata_blockers:[];
    blockers.textContent=metadataBlockers.length
      ?'Champs bloquant le brouillon : '+metadataBlockers.join(' · ')
      :'Métadonnées de soumission complètes.';
    details.appendChild(blockers);

    const actions=document.createElement('div');
    actions.className='h1-review-actions';
    const save=document.createElement('button');
    save.type='button';
    save.textContent='Sauvegarder la revue';
    save.addEventListener('click',()=>void saveFindingReviewMetadata(finding.id,details));
    actions.appendChild(save);

    if(!['confirmed','rejected'].includes(String(finding.status||''))){
      const confirm=document.createElement('button');
      confirm.type='button';
      confirm.textContent='Confirmer le finding';
      confirm.addEventListener('click',()=>void resolveHackerOneFinding(finding.id,true,details));
      const reject=document.createElement('button');
      reject.type='button';
      reject.className='danger';
      reject.textContent='Rejeter le finding';
      reject.addEventListener('click',()=>void resolveHackerOneFinding(finding.id,false,details));
      actions.append(confirm,reject);
    }
    details.appendChild(actions);

    const status=document.createElement('p');
    status.dataset.reviewStatus='true';
    status.className='muted compact';
    status.textContent='La sauvegarde des métadonnées ne confirme jamais automatiquement le finding.';
    details.appendChild(status);
    return details;
  }

  function renderHackerOneFindings(campaignData,artifacts,reportReadiness,reportApproval){
    const list=el('h1RunFindingList');
    list.replaceChildren();
    const findings=Array.isArray(campaignData?.findings)?campaignData.findings:[];
    if(!findings.length){
      list.textContent='Aucun finding détecté pour le moment.';
    }else{
      for(const finding of findings){
        const row=document.createElement('div');
        row.className='h1-run-finding';

        const head=document.createElement('div');
        head.className='finding-head';
        const title=document.createElement('strong');
        title.textContent=String(finding.title||finding.id||'Finding');
        const status=document.createElement('span');
        const findingStatus=String(finding.status||'unknown');
        status.className='pill '+(
          findingStatus==='confirmed'?'ok':
          findingStatus==='rejected'?'err':'warn'
        );
        status.textContent=findingStatus.replaceAll('_',' ');
        head.append(title,status);

        const meta=document.createElement('div');
        meta.className='muted';
        const severity=String(finding.severity||'unknown');
        const endpoint=String(finding.endpoint||finding.asset||'—');
        const evidenceCount=(Array.isArray(artifacts)?artifacts:[])
          .filter(item=>String(item.finding_id||'')===String(finding.id||'')).length;
        meta.textContent=severity+' · '+endpoint+' · '+evidenceCount+' preuve(s)';
        row.append(head,meta);
        const readinessItem=Array.isArray(reportReadiness?.findings)
          ?reportReadiness.findings.find(item=>String(item.finding_id||'')===String(finding.id||''))
          :null;
        if(findingStatus!=='rejected'){
          row.appendChild(buildFindingReviewEditor(finding,readinessItem));
        }
        list.appendChild(row);
      }
    }

    const summary=reportReadiness?.summary||{};
    const ready=Number(summary.submission_ready)||0;
    const blocked=Number(summary.submission_blocked)||0;
    const reportArtifact=(Array.isArray(artifacts)?artifacts:[]).find(item=>
      item?.kind==='report'&&String(item?.idempotency_key||'').endsWith(':report:hackerone')
    );
    const button=el('h1ReportDraft');
    const download=el('h1ReportDownload');
    const approve=el('h1ReportApprove');
    const submit=el('h1ReportSubmit');
    const revoke=el('h1ReportRevoke');
    const status=el('h1ReportStatus');
    const approvalStatus=el('h1ReportApprovalStatus');
    if(reportArtifact){
      const artifactId=String(reportArtifact.id||'');
      button.disabled=true;
      download.disabled=false;
      download.classList.remove('hidden');
      download.dataset.artifactId=artifactId;
      approve.dataset.artifactId=artifactId;
      submit.dataset.artifactId=artifactId;
      revoke.dataset.artifactId=artifactId;
      const sha=String(reportArtifact.sha256||'');
      status.textContent='Brouillon HackerOne généré · artifact '+artifactId+
        (sha?' · SHA-256 '+sha.slice(0,12)+'…':'');

      if(reportApproval?.error){
        approve.disabled=true;
        approve.classList.remove('hidden');
        submit.disabled=true;
        submit.classList.add('hidden');
        revoke.disabled=true;
        revoke.classList.add('hidden');
        approvalStatus.className='muted compact err-text';
        approvalStatus.textContent='Statut d’approbation indisponible : '+reportApproval.error;
      }else if(reportApproval?.approved){
        approve.disabled=true;
        approve.classList.add('hidden');
        submit.disabled=false;
        submit.classList.remove('hidden');
        revoke.disabled=false;
        revoke.classList.remove('hidden');
        approvalStatus.className='muted compact ok-text';
        const reviewer=String(reportApproval.reviewer||'relecteur');
        const approvedAt=reportApproval.approved_at
          ?' · '+new Date(reportApproval.approved_at).toLocaleString()
          :'';
        approvalStatus.textContent='Brouillon approuvé par '+reviewer+approvedAt+'.';
      }else{
        approve.disabled=false;
        approve.classList.remove('hidden');
        submit.disabled=true;
        submit.classList.add('hidden');
        revoke.disabled=true;
        revoke.classList.add('hidden');
        approvalStatus.className='muted compact '+(reportApproval?.stale?'err-text':'');
        approvalStatus.textContent=reportApproval?.stale
          ?'Approbation obsolète : le rapport ou l’état des findings a changé. Réapprobation humaine requise.'
          :'Brouillon non approuvé · approbation humaine explicite requise avant toute future soumission.';
      }
    }else if(ready>0){
      button.disabled=false;
      download.disabled=true;
      download.classList.add('hidden');
      approve.disabled=true;
      approve.classList.add('hidden');
      submit.disabled=true;
      submit.classList.add('hidden');
      revoke.disabled=true;
      revoke.classList.add('hidden');
      delete download.dataset.artifactId;
      delete approve.dataset.artifactId;
      delete submit.dataset.artifactId;
      delete revoke.dataset.artifactId;
      approvalStatus.className='muted compact';
      approvalStatus.textContent='Aucun brouillon à approuver.';
      status.textContent=ready+' finding(s) prêt(s) à soumettre · validation humaine requise avant envoi.';
    }else{
      button.disabled=true;
      download.disabled=true;
      download.classList.add('hidden');
      approve.disabled=true;
      approve.classList.add('hidden');
      submit.disabled=true;
      submit.classList.add('hidden');
      revoke.disabled=true;
      revoke.classList.add('hidden');
      delete download.dataset.artifactId;
      delete approve.dataset.artifactId;
      delete submit.dataset.artifactId;
      delete revoke.dataset.artifactId;
      approvalStatus.className='muted compact';
      approvalStatus.textContent='Aucun brouillon à approuver.';
      status.textContent='Brouillon bloqué · '+blocked+' finding(s) incomplet(s) ou non validé(s).';
    }
  }

  async function downloadHackerOneReport(){
    if(!runMonitorCampaignId)return;
    const button=el('h1ReportDownload');
    const artifactId=String(button.dataset.artifactId||'');
    if(!artifactId)return;
    button.disabled=true;
    el('h1ReportStatus').textContent='Téléchargement du brouillon HackerOne…';
    try{
      const headers={};
      const token=String(el('token')?.value||'').trim();
      if(token)headers.authorization='Bearer '+token;
      const response=await fetch(
        '/api/campaigns/'+encodeURIComponent(runMonitorCampaignId)+
        '/artifacts/'+encodeURIComponent(artifactId),
        {headers}
      );
      if(!response.ok){
        let detail='HTTP '+response.status;
        try{
          const body=await response.json();
          detail=body?.detail
            ?(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail))
            :detail;
        }catch{}
        throw new Error(detail);
      }
      const blob=await response.blob();
      const objectUrl=URL.createObjectURL(blob);
      const link=document.createElement('a');
      link.href=objectUrl;
      link.download='hackerone-report-'+artifactId+'.md';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(()=>URL.revokeObjectURL(objectUrl),0);
      const sha=String(response.headers.get('x-content-sha256')||'');
      el('h1ReportStatus').textContent='Brouillon HackerOne téléchargé'+
        (sha?' · SHA-256 '+sha.slice(0,12)+'…':'')+'.';
    }catch(error){
      el('h1ReportStatus').textContent='Téléchargement impossible : '+error.message;
    }finally{
      button.disabled=false;
    }
  }

  function hackerOneReportReviewer(){
    return String(el('h1ReviewedBy')?.value||'').trim();
  }

  async function approveHackerOneReport(){
    if(!runMonitorCampaignId)return;
    const button=el('h1ReportApprove');
    const artifactId=String(button.dataset.artifactId||'');
    const reviewer=hackerOneReportReviewer();
    if(!artifactId)return;
    if(!reviewer){
      el('h1ReportApprovalStatus').className='muted compact err-text';
      el('h1ReportApprovalStatus').textContent='Relecteur requis avant approbation du brouillon.';
      return;
    }
    button.disabled=true;
    el('h1ReportApprovalStatus').className='muted compact';
    el('h1ReportApprovalStatus').textContent='Enregistrement de l’approbation humaine…';
    try{
      await api(
        '/campaigns/'+encodeURIComponent(runMonitorCampaignId)+
        '/reports/'+encodeURIComponent(artifactId)+'/approval',
        {method:'POST',body:JSON.stringify({reviewer})}
      );
      await refreshRunMonitor(runMonitorCampaignId);
    }catch(error){
      el('h1ReportApprovalStatus').className='muted compact err-text';
      el('h1ReportApprovalStatus').textContent='Approbation refusée : '+error.message;
      button.disabled=false;
    }
  }

  async function submitHackerOneReport(){
    if(!runMonitorCampaignId)return;
    const button=el('h1ReportSubmit');
    const artifactId=String(button.dataset.artifactId||'');
    const actor=hackerOneReportReviewer();
    if(!artifactId)return;
    if(!actor){
      el('h1ReportApprovalStatus').className='muted compact err-text';
      el('h1ReportApprovalStatus').textContent='Identité opérateur requise avant soumission.';
      return;
    }
    if(!window.confirm(
      'Soumettre ce rapport approuvé à HackerOne ? Cette action crée un rapport externe.'
    ))return;
    button.disabled=true;
    el('h1ReportApprovalStatus').className='muted compact';
    el('h1ReportApprovalStatus').textContent='Soumission explicite à HackerOne…';
    try{
      const result=await api(
        '/campaigns/'+encodeURIComponent(runMonitorCampaignId)+
        '/reports/'+encodeURIComponent(artifactId)+'/submit-to-hackerone',
        {
          method:'POST',
          body:JSON.stringify({actor,confirm_submission:true})
        }
      );
      button.disabled=true;
      button.classList.add('hidden');
      const remoteId=String(result?.remote_report_id||'');
      el('h1ReportApprovalStatus').className='muted compact ok-text';
      el('h1ReportApprovalStatus').textContent='Rapport soumis à HackerOne'+
        (remoteId?' · report '+remoteId:'')+'.';
    }catch(error){
      el('h1ReportApprovalStatus').className='muted compact err-text';
      el('h1ReportApprovalStatus').textContent='Soumission HackerOne refusée : '+error.message;
      button.disabled=false;
    }
  }

  async function revokeHackerOneReportApproval(){
    if(!runMonitorCampaignId)return;
    const button=el('h1ReportRevoke');
    const artifactId=String(button.dataset.artifactId||'');
    const reviewer=hackerOneReportReviewer();
    if(!artifactId)return;
    if(!reviewer){
      el('h1ReportApprovalStatus').className='muted compact err-text';
      el('h1ReportApprovalStatus').textContent='Relecteur requis pour révoquer l’approbation.';
      return;
    }
    button.disabled=true;
    try{
      await api(
        '/campaigns/'+encodeURIComponent(runMonitorCampaignId)+
        '/reports/'+encodeURIComponent(artifactId)+'/approval/revoke',
        {method:'POST',body:JSON.stringify({reviewer})}
      );
      await refreshRunMonitor(runMonitorCampaignId);
    }catch(error){
      el('h1ReportApprovalStatus').className='muted compact err-text';
      el('h1ReportApprovalStatus').textContent='Révocation refusée : '+error.message;
      button.disabled=false;
    }
  }

  async function queueHackerOneReport(){
    if(!runMonitorCampaignId)return;
    const button=el('h1ReportDraft');
    button.disabled=true;
    el('h1ReportStatus').textContent='Mise en file du brouillon HackerOne…';
    try{
      const encoded=encodeURIComponent(runMonitorCampaignId);
      await api('/campaigns/'+encoded+'/reports?platform=hackerone',{method:'POST'});
      el('h1ReportStatus').textContent='Brouillon HackerOne en file de génération.';
      await refreshRunMonitor(runMonitorCampaignId);
    }catch(error){
      el('h1ReportStatus').textContent='Brouillon non généré : '+error.message;
      await refreshRunMonitor(runMonitorCampaignId);
    }
  }

  function renderRunMonitor(campaignData,control,artifacts,reportReadiness,reportApproval){
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
    renderHackerOneFindings(campaignData,artifacts,reportReadiness,reportApproval);
    el('h1RunUpdated').textContent='Actualisé à '+new Date().toLocaleTimeString();
  }

  async function refreshRunMonitor(campaignId){
    if(runMonitorBusy||!campaignId)return;
    runMonitorBusy=true;
    try{
      const encoded=encodeURIComponent(campaignId);
      const [campaignData,control,artifacts,reportReadiness]=await Promise.all([
        api('/campaigns/'+encodeURIComponent(campaignId)),
        api('/campaigns/'+encodeURIComponent(campaignId)+'/control-status'),
        api('/campaigns/'+encodeURIComponent(campaignId)+'/artifacts'),
        api('/campaigns/'+encodeURIComponent(campaignId)+'/report-readiness')
      ]);
      const reportArtifact=(Array.isArray(artifacts)?artifacts:[]).find(item=>
        item?.kind==='report'&&String(item?.idempotency_key||'').endsWith(':report:hackerone')
      );
      let reportApproval=null;
      if(reportArtifact?.id){
        try{
          reportApproval=await api(
            '/campaigns/'+encoded+
            '/reports/'+encodeURIComponent(reportArtifact.id)+'/approval'
          );
        }catch(error){
          reportApproval={error:error.message};
        }
      }
      renderRunMonitor(campaignData,control,artifacts,reportReadiness,reportApproval);
      if(typeof refreshDashboard==='function'&&campaign?.id===campaignId){
        await refreshDashboard();
      }
      if(['completed','cancelled','failed'].includes(String(campaignData?.state||''))){
        stopRunMonitor();
      }
      return {campaign:campaignData,control,artifacts,reportReadiness,reportApproval,encoded};
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
  el('h1ReportDraft').addEventListener('click',()=>void queueHackerOneReport());
  el('h1ReportDownload').addEventListener('click',()=>void downloadHackerOneReport());
  el('h1ReportApprove').addEventListener('click',()=>void approveHackerOneReport());
  el('h1ReportSubmit').addEventListener('click',()=>void submitHackerOneReport());
  el('h1ReportRevoke').addEventListener('click',()=>void revokeHackerOneReportApproval());
  el('token').addEventListener('change',initRemoteControlCenter);
  initRemoteControlCenter();
})();
