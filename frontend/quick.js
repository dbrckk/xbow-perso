(()=> {
  const $=id=>document.getElementById(id);
  const state={
    handles:[],
    selection:[]
  };

  function token(){
    return ($('token')?.value||'').trim();
  }

  async function api(path,opts={}){
    const headers={'content-type':'application/json',...(opts.headers||{})};
    const value=token();
    if(value)headers.authorization='Bearer '+value;
    const response=await fetch('/api'+path,{...opts,headers});
    let data={};
    try{data=await response.json();}catch(_error){}
    if(!response.ok){
      const detail=data?.detail;
      const message=typeof detail==='string'
        ?detail
        :(detail?.message||detail?.reason||'Erreur serveur');
      throw new Error(message);
    }
    return data;
  }

  function setMessage(message,kind='muted'){
    const target=$('quickMessage');
    if(!target)return;
    target.textContent=message;
    target.className=kind;
  }

  function setBusy(busy,label){
    const statePill=$('quickState');
    if(statePill){
      statePill.textContent=busy?(label||'chargement…'):'prêt';
      statePill.className='pill '+(busy?'warn':'ok');
    }
    if($('quickSelect'))$('quickSelect').disabled=busy;
    if($('quickStart'))$('quickStart').disabled=busy||state.handles.length!==6;
  }

  function bucketLabel(bucket){
    if(bucket==='easy')return 'Simple';
    if(bucket==='medium')return 'Moyen';
    if(bucket==='high_value')return 'Fort potentiel';
    return bucket||'Programme';
  }

  function renderSelection(){
    const root=$('quickSelection');
    if(!root)return;
    root.replaceChildren();
    if(!state.selection.length){
      const p=document.createElement('p');
      p.className='muted';
      p.textContent='Aucune sélection.';
      root.appendChild(p);
      return;
    }
    for(const item of state.selection){
      const row=document.createElement('div');
      row.className='quick-program';

      const meta=document.createElement('div');
      const title=document.createElement('strong');
      title.textContent=item.name||item.handle;
      const sub=document.createElement('div');
      sub.className='muted compact';
      const payout=Number(item.historical_usd_awarded_max||0);
      const payoutText=payout>0?' · historique max $'+Math.round(payout).toLocaleString('fr-FR'):'';
      sub.textContent=bucketLabel(item.quick_bucket)+' · '+String(item.handle||'')+payoutText;
      meta.append(title,sub);

      const score=document.createElement('span');
      score.className='pill';
      score.textContent=String(item.value_efficiency_score??item.opportunity_score??'—');

      row.append(meta,score);
      root.appendChild(row);
    }
  }

  async function selectSix(){
    setBusy(true,'sélection…');
    setMessage('Analyse des programmes READY…');
    try{
      const data=await api('/hackerone/quick/selection');
      state.selection=Array.isArray(data.selection)?data.selection:[];
      state.handles=Array.isArray(data.handles)?data.handles:[];
      renderSelection();
      const shortages=data?.summary?.shortages||{};
      if(state.handles.length!==6){
        setMessage(
          'Seulement '+state.handles.length+' programme(s) READY disponible(s). '+
          'Il faut 6 profils revus avant de pouvoir démarrer.',
          'err'
        );
      }else{
        setMessage('6 programmes sélectionnés. Tu peux démarrer.','ok');
      }
    }catch(error){
      state.selection=[];
      state.handles=[];
      renderSelection();
      setMessage('Sélection impossible : '+error.message,'err');
    }finally{
      setBusy(false);
    }
  }

  async function startBatch(){
    if(state.handles.length!==6){
      setMessage('Sélectionne d’abord les 6 programmes.','err');
      return;
    }
    const mode=document.querySelector('input[name="quickMode"]:checked')?.value||'parallel';
    setBusy(true,'démarrage…');
    setMessage('Revalidation finale des 6 programmes…');
    try{
      const batch=await api('/hackerone/quick/launch',{
        method:'POST',
        body:JSON.stringify({mode,handles:state.handles})
      });
      setMessage(
        'Batch démarré : '+String(batch.id||'')+
        '. Tu peux fermer la page et revenir plus tard.',
        'ok'
      );
      state.selection=[];
      state.handles=[];
      renderSelection();
      await refreshJournal();
    }catch(error){
      setMessage('Démarrage bloqué : '+error.message,'err');
    }finally{
      setBusy(false);
    }
  }

  function campaignSummary(member){
    const c=member?.campaign;
    if(!c)return 'Campagne non disponible';
    const parts=[
      String(c.state||'inconnu'),
      String(c.findings_confirmed||0)+' finding(s) confirmé(s)',
      String(c.events_total||0)+' événement(s)'
    ];
    return parts.join(' · ');
  }

  function renderJournal(data){
    const root=$('quickJournal');
    if(!root)return;
    root.replaceChildren();
    const entries=Array.isArray(data?.journal)?data.journal:[];
    if(!entries.length){
      const p=document.createElement('p');
      p.className='muted';
      p.textContent='Aucune campagne enregistrée pour le moment.';
      root.appendChild(p);
      return;
    }
    for(const entry of entries){
      const card=document.createElement('article');
      card.className='quick-journal-entry';

      const head=document.createElement('div');
      head.className='quick-journal-entry-head';
      const title=document.createElement('strong');
      title.textContent='Batch '+String(entry.batch_id||'').slice(0,8);
      const pill=document.createElement('span');
      pill.className='pill '+(entry.state==='completed'?'ok':entry.state==='running'?'warn':'');
      pill.textContent=String(entry.state||'inconnu');
      head.append(title,pill);

      const meta=document.createElement('div');
      meta.className='muted compact';
      meta.textContent=
        (entry.mode==='parallel'?'Tous à la fois':'À la suite')+
        ' · '+(entry.created_at?new Date(entry.created_at).toLocaleString('fr-FR'):'date inconnue');

      const list=document.createElement('div');
      list.className='quick-journal-members';
      for(const member of Array.isArray(entry.members)?entry.members:[]){
        const row=document.createElement('div');
        row.className='quick-journal-member';
        const name=document.createElement('strong');
        name.textContent=String(member.handle||'programme');
        const brief=document.createElement('div');
        brief.className='muted compact';
        brief.textContent=campaignSummary(member);
        row.append(name,brief);
        if(member.reason){
          const reason=document.createElement('div');
          reason.className='err compact';
          reason.textContent='Blocage : '+String(member.reason);
          row.appendChild(reason);
        }
        list.appendChild(row);
      }

      const details=document.createElement('details');
      const summary=document.createElement('summary');
      summary.textContent='Brief détaillé';
      const pre=document.createElement('pre');
      pre.className='quick-brief';
      pre.textContent=JSON.stringify(entry,null,2);
      details.append(summary,pre);

      card.append(head,meta,list,details);
      root.appendChild(card);
    }
  }

  async function refreshJournal(){
    try{
      const data=await api('/hackerone/quick/journal?limit=30');
      renderJournal(data);
    }catch(error){
      const root=$('quickJournal');
      if(root)root.innerHTML='<p class="err"></p>';
      const p=root?.querySelector('p');
      if(p)p.textContent='Journal indisponible : '+error.message;
    }
  }

  $('quickSelect')?.addEventListener('click',()=>void selectSix());
  $('quickStart')?.addEventListener('click',()=>void startBatch());
  $('quickJournalRefresh')?.addEventListener('click',()=>void refreshJournal());

  renderSelection();
  void refreshJournal();
  setInterval(()=>void refreshJournal(),15000);
})();
