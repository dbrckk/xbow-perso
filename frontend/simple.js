(()=>{
  const TOKEN_KEY='xbowApiToken';
  const ACTIVE_KEY='xbow:simple-bounty:active-batch:v1';
  let selection=[];
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
      if(typeof detail==='string')throw new Error(detail);
      if(detail?.message){
        const reason=detail?.reason?' · '+String(detail.reason):'';
        throw new Error(String(detail.message)+reason);
      }
      throw new Error('HTTP '+response.status);
    }
    return data;
  }

  function money(value){
    const amount=Number(value||0);
    return amount>0?' · historique max $'+amount.toLocaleString():'';
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
        row.textContent=String(item?.name||item?.handle||'Programme')+
          ' · '+String(item?.handle||'')+
          (showValue?money(item?.historical_usd_awarded_max):'');
        section.appendChild(row);
      }
      root.appendChild(section);
    }
  }

  async function prepare(){
    if(!requireToken())return;
    const button=$('prepare');
    button.disabled=true;
    $('start').disabled=true;
    setStatus('Sélection automatique de 6 programmes READY déjà revus…');
    try{
      const result=await api('/hackerone/simple-selection');
      selection=Array.isArray(result?.handles)?result.handles.filter(Boolean):[];
      renderSelection(result);
      if(result?.complete!==true||selection.length!==6){
        throw new Error(
          '6 programmes READY déjà revus sont nécessaires. Disponibles : '+selection.length+'.'
        );
      }
      $('start').disabled=false;
      setStatus('Sélection prête : 2 faciles + 2 moyens + 2 fort potentiel.','ok');
    }catch(error){
      selection=[];
      $('selection').textContent='Aucune sélection exploitable.';
      setStatus('Sélection impossible : '+error.message,'err');
    }finally{
      button.disabled=false;
    }
  }

  async function start(){
    if(!requireToken())return;
    if(selection.length!==6){
      setStatus('Sélectionne d’abord les 6 campagnes.','err');
      return;
    }
    const button=$('start');
    button.disabled=true;
    const mode=$('mode').value==='parallel'?'parallel':'sequential';
    setStatus('Pré-vol serveur : scope, profils, runtime et fingerprints…');
    try{
      const preflight=await api('/imports/hackerone/batches/go-no-go',{
        method:'POST',
        body:JSON.stringify({mode,handles:selection})
      });
      if(preflight?.go!==true){
        const blockers=(Array.isArray(preflight?.blockers)?preflight.blockers:[])
          .map(value=>String(value||'')).filter(Boolean);
        throw new Error('Pré-vol bloqué'+(blockers.length?' · '+blockers.join(' · '):''));
      }
      setStatus('GO confirmé. Création du lot côté serveur…');
      const batch=await api('/imports/hackerone/batches/launch-reviewed',{
        method:'POST',
        body:JSON.stringify({mode,handles:selection})
      });
      const id=String(batch?.id||'');
      if(id){
        try{localStorage.setItem(ACTIVE_KEY,id);}catch(_error){}
      }
      setStatus(
        mode==='parallel'
          ?'6 campagnes lancées en parallèle. Tu peux fermer la page.'
          :'6 campagnes mises en file. Elles seront exécutées une après l’autre.',
        'ok'
      );
      await refreshJournal({quiet:true});
    }catch(error){
      setStatus('Lancement bloqué : '+error.message,'err');
      button.disabled=false;
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
      if(active){
        if(!quiet)setStatus('Campagnes en cours côté serveur. Tu peux revenir plus tard.','ok');
      }else if(entries.length&&!quiet){
        setStatus('Derniers résultats chargés.','ok');
      }
    }catch(error){
      setStatus('Journal indisponible : '+error.message,'err');
    }
  }

  function bind(){
    try{$('token').value=localStorage.getItem(TOKEN_KEY)||'';}catch(_error){}
    $('token').addEventListener('input',saveToken);
    $('prepare').addEventListener('click',()=>void prepare());
    $('start').addEventListener('click',()=>void start());
    $('refresh').addEventListener('click',()=>void refreshJournal());
    window.addEventListener('unhandledrejection',event=>{
      const message=event?.reason?.message||String(event?.reason||'Erreur JavaScript');
      setStatus('Erreur interface : '+message,'err');
    });
    window.addEventListener('error',event=>{
      if(event?.message)setStatus('Erreur interface : '+event.message,'err');
    });
    void refreshJournal({quiet:true});
    timer=setInterval(()=>void refreshJournal({quiet:true}),15000);
  }

  window.addEventListener('beforeunload',()=>{if(timer)clearInterval(timer);});
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',bind,{once:true});
  }else{
    bind();
  }
})();
