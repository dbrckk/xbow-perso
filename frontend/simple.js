(()=>{
  const $=id=>document.getElementById(id);
  const TOKEN_KEY='xbowApiToken';
  const ACTIVE_KEY='xbow:simple-bounty:active-batch:v1';
  let selection=[];
  let activeBatch='';
  let timer=null;

  function token(){
    return String($('token').value||'').trim();
  }
  function saveToken(){
    try{localStorage.setItem(TOKEN_KEY,$('token').value||'');}catch(_error){}
  }
  async function api(path,options={}){
    const headers={'content-type':'application/json',...(options.headers||{})};
    if(token())headers.authorization='Bearer '+token();
    const response=await fetch('/api'+path,{...options,headers,cache:'no-store'});
    let data={};
    try{data=await response.json();}catch(_error){}
    if(!response.ok){
      const detail=data?.detail;
      throw new Error(typeof detail==='string'?detail:JSON.stringify(detail||data||{status:response.status}));
    }
    return data;
  }
  function status(message,kind=''){
    $('status').textContent=message;
    $('status').className='simple-status '+kind;
  }
  function label(item,group){
    const value=Number(item?.historical_usd_awarded_max||0);
    const extra=group==='high_value'&&value>0?' · historique max $'+value.toLocaleString():'';
    return String(item?.name||item?.handle||'Programme')+' · '+String(item?.handle||'')+extra;
  }
  function renderSelection(result){
    const groups=result?.groups||{};
    const rows=[
      ['Facile',groups.easy||[],'easy'],
      ['Moyen',groups.medium||[],'medium'],
      ['Fort potentiel',groups.high_value||[],'high_value']
    ];
    const root=$('selection');
    root.replaceChildren();
    for(const [title,items,key] of rows){
      const section=document.createElement('div');
      section.className='simple-group';
      const h=document.createElement('strong');
      h.textContent=title;
      section.appendChild(h);
      for(const item of items){
        const p=document.createElement('div');
        p.className='simple-program';
        p.textContent=label(item,key);
        section.appendChild(p);
      }
      root.appendChild(section);
    }
  }
  async function prepare(){
    $('prepare').disabled=true;
    $('start').disabled=true;
    status('Sélection des programmes READY et vérification du catalogue…');
    try{
      const result=await api('/hackerone/simple-selection');
      selection=Array.isArray(result?.handles)?result.handles:[];
      renderSelection(result);
      if(!result?.complete||selection.length!==6){
        throw new Error('Il faut 6 programmes READY déjà revus. '+selection.length+' seulement sont disponibles.');
      }
      $('start').disabled=false;
      status('6 programmes prêts : 2 faciles, 2 moyens, 2 à fort potentiel.','ok');
    }catch(error){
      selection=[];
      status('Sélection impossible : '+error.message,'err');
    }finally{
      $('prepare').disabled=false;
    }
  }
  async function start(){
    if(selection.length!==6)return;
    $('start').disabled=true;
    status('Pré-vol final puis lancement du lot…');
    try{
      const mode=$('mode').value==='parallel'?'parallel':'sequential';
      const batch=await api('/imports/hackerone/batches/launch-reviewed',{
        method:'POST',
        body:JSON.stringify({mode,handles:selection})
      });
      activeBatch=String(batch?.id||'');
      if(activeBatch){
        try{localStorage.setItem(ACTIVE_KEY,activeBatch);}catch(_error){}
      }
      status('Lot lancé côté serveur. Tu peux fermer cette page.','ok');
      await refreshJournal();
    }catch(error){
      status('Lancement bloqué : '+error.message,'err');
      $('start').disabled=false;
    }
  }
  function memberText(member){
    const findings=Number(member?.finding_count||0);
    const confirmed=Number(member?.confirmed_findings||0);
    const reason=member?.reason?' · '+String(member.reason):'';
    return String(member?.handle||'campagne')+' — '+String(member?.status||member?.campaign_state||'—')+
      ' · '+findings+' finding(s), '+confirmed+' confirmé(s)'+reason;
  }
  function renderJournal(payload){
    const entries=Array.isArray(payload?.journal)?payload.journal:[];
    const root=$('journal');
    root.replaceChildren();
    if(!entries.length){
      root.textContent='Aucune campagne enregistrée.';
      return;
    }
    for(const entry of entries.slice(0,30)){
      const card=document.createElement('article');
      card.className='simple-log';
      const head=document.createElement('strong');
      const when=entry?.created_at?new Date(entry.created_at).toLocaleString():'';
      head.textContent=(when?when+' · ':'')+String(entry?.mode||'')+' · '+String(entry?.state||'');
      card.appendChild(head);
      for(const member of (entry?.members||[])){
        const line=document.createElement('div');
        line.textContent=memberText(member);
        card.appendChild(line);
        for(const finding of (member?.finding_brief||[]).slice(0,5)){
          const f=document.createElement('div');
          f.className='simple-finding';
          f.textContent='↳ '+String(finding.severity||'')+' · '+String(finding.title||'')+' · '+String(finding.status||'');
          card.appendChild(f);
        }
      }
      root.appendChild(card);
    }
    const digest=payload?.learning_digest||{};
    $('learning').textContent=
      'Mémoire locale : '+String(digest.campaign_count||0)+' campagne(s), '+
      String(digest.confirmed_findings||0)+' finding(s) confirmé(s). '+
      'Digest détaillé prêt pour synchronisation repo.';
  }
  async function refreshJournal(){
    try{
      const payload=await api('/hackerone/journal?limit=50');
      renderJournal(payload);
      const entries=Array.isArray(payload?.journal)?payload.journal:[];
      const active=entries.find(item=>!['completed','cancelled'].includes(String(item?.state||'')));
      if(active){
        activeBatch=String(active.batch_id||'');
        status('Campagnes en cours côté serveur. Tu peux revenir plus tard.','ok');
      }else if(entries.length){
        status('Aucune campagne en cours. Derniers résultats chargés.','ok');
      }
    }catch(error){
      status('Journal indisponible : '+error.message,'err');
    }
  }
  async function init(){
    try{$('token').value=localStorage.getItem(TOKEN_KEY)||'';}catch(_error){}
    $('token').addEventListener('input',saveToken);
    $('prepare').addEventListener('click',()=>void prepare());
    $('start').addEventListener('click',()=>void start());
    $('refresh').addEventListener('click',()=>void refreshJournal());
    try{activeBatch=localStorage.getItem(ACTIVE_KEY)||'';}catch(_error){}
    await refreshJournal();
    timer=setInterval(()=>void refreshJournal(),15000);
  }
  window.addEventListener('beforeunload',()=>{if(timer)clearInterval(timer);});
  void init();
})();
