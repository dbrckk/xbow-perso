(()=>{
  let approvedPreview=null;
  let remoteBinding=null;
  let hackerOnePrograms=[];
  let hackerOneCatalogMeta={};
  let serverReviewProfiles={};
  let runMonitorTimer=null;
  let runMonitorCampaignId=null;
  let runMonitorBusy=false;
  let attentionTimer=null;
  let latestAttentionPayload=null;
  let attentionSeenMemory={version:1,initialized:false,seen:{}};
  let attentionFilterMemory=null;
  let attentionFiltersRestored=false;
  let attentionCustomViewsMemory={version:1,views:[]};
  let batchSelectedHandles=new Set();
  let activeBatchId=null;
  let batchTimer=null;

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

  const ATTENTION_SEEN_STORAGE_KEY='xbow:hackerone:attention-seen:v1';
  const ATTENTION_FILTER_STORAGE_KEY='xbow:hackerone:attention-filters:v1';
  const ATTENTION_CUSTOM_VIEWS_STORAGE_KEY='xbow:hackerone:attention-custom-views:v1';
  const ATTENTION_CUSTOM_VIEW_LIMIT=20;
  const ATTENTION_CUSTOM_VIEW_NAME_LIMIT=60;
  const QUICK_PROFILE_STORAGE_KEY='xbow:hackerone:quick-profiles:v1';
  const QUICK_REVIEWER_STORAGE_KEY='xbow:hackerone:quick-reviewer:v1';
  const QUICK_PROFILE_LIMIT=30;
  const QUICK_LAST_PROGRAM_STORAGE_KEY='xbow:hackerone:last-program:v1';
  const QUICK_PREFS_STORAGE_KEY='xbow:hackerone:quick-prefs:v1';
  const H1_ACTIVE_BATCH_STORAGE_KEY='xbow:hackerone:active-batch:v1';



  function hackerOneAttentionLabel(item){
    const bucket=String(item?.bucket||'other');
    if(bucket==='action-required')return 'Action requise';
    if(bucket==='active')return 'Actif';
    if(bucket==='awaiting-sync')return 'En attente de synchro';
    if(bucket==='resolved')return 'Resolved';
    if(bucket==='duplicate')return 'Duplicate';
    if(bucket==='informative')return 'Informative';
    if(bucket==='closed-other')return 'Fermé';
    return String(item?.state||'Autre');
  }

  function hackerOneNotificationLabel(item){
    const kind=String(item?.notification_kind||'');
    if(kind==='needs-more-info')return 'Nouvelle demande d’informations';
    if(kind==='activity-comment')return 'Nouveau commentaire';
    if(kind==='activity-bounty-awarded')return 'Nouvelle bounty';
    if(kind==='activity-bug-duplicate')return 'Nouveau classement duplicate';
    if(kind==='activity-bug-informative')return 'Nouveau classement informative';
    if(kind==='activity-bug-resolved')return 'Report résolu';
    if(kind==='status')return 'État mis à jour';
    if(kind==='submitted')return 'Report soumis';
    return 'Nouvelle activité';
  }

  function attentionSeenKey(item){
    return [
      String(item?.campaign_id||''),
      String(item?.artifact_id||''),
      String(item?.remote_report_id||'')
    ].join(':');
  }

  function loadAttentionSeen(){
    try{
      const parsed=JSON.parse(localStorage.getItem(ATTENTION_SEEN_STORAGE_KEY)||'null');
      if(parsed&&parsed.version===1&&parsed.seen&&typeof parsed.seen==='object'){
        return {
          version:1,
          initialized:Boolean(parsed.initialized),
          seen:{...parsed.seen}
        };
      }
    }catch(_error){}
    return {
      version:1,
      initialized:Boolean(attentionSeenMemory.initialized),
      seen:{...attentionSeenMemory.seen}
    };
  }

  function saveAttentionSeen(state){
    const entries=Object.entries(state?.seen||{}).slice(-1000);
    const normalized={
      version:1,
      initialized:Boolean(state?.initialized),
      seen:Object.fromEntries(entries)
    };
    attentionSeenMemory=normalized;
    try{
      localStorage.setItem(ATTENTION_SEEN_STORAGE_KEY,JSON.stringify(normalized));
    }catch(_error){}
    return normalized;
  }

  function ensureAttentionBaseline(items){
    let state=loadAttentionSeen();
    if(state.initialized)return state;
    for(const item of items){
      const cursor=String(item?.notification_cursor||'');
      if(cursor)state.seen[attentionSeenKey(item)]=cursor;
    }
    state.initialized=true;
    return saveAttentionSeen(state);
  }

  function isAttentionUnread(item,state){
    const cursor=String(item?.notification_cursor||'');
    if(!cursor)return false;
    return String(state?.seen?.[attentionSeenKey(item)]||'')!==cursor;
  }

  function markHackerOneAttentionSeen(item){
    if(!item)return;
    const cursor=String(item?.notification_cursor||'');
    if(!cursor)return;
    const state=loadAttentionSeen();
    state.initialized=true;
    state.seen[attentionSeenKey(item)]=cursor;
    saveAttentionSeen(state);
    if(latestAttentionPayload)renderHackerOneAttention(latestAttentionPayload);
  }

  function markAllHackerOneAttentionSeen(){
    const items=Array.isArray(latestAttentionPayload?.items)?latestAttentionPayload.items:[];
    const state=loadAttentionSeen();
    state.initialized=true;
    for(const item of items){
      const cursor=String(item?.notification_cursor||'');
      if(cursor)state.seen[attentionSeenKey(item)]=cursor;
    }
    saveAttentionSeen(state);
    if(latestAttentionPayload)renderHackerOneAttention(latestAttentionPayload);
  }

  async function focusHackerOneAttentionCampaign(item){
    const id=String(item?.campaign_id||'');
    if(!id)return;
    markHackerOneAttentionSeen(item);
    try{
      const campaign=await api('/campaigns/'+encodeURIComponent(id));
      await activateCampaign(campaign);
      startRunMonitor(id);
    }catch(error){
      el('h1AttentionUpdated').textContent='Ouverture impossible : '+error.message;
    }
  }

  function attentionText(value){
    return String(value??'').normalize('NFKD').toLowerCase();
  }

  function updateAttentionSelectOptions(id,values,allLabel){
    const select=el(id);
    const current=String(select.value||'all');
    const unique=[...new Set(values.filter(Boolean).map(value=>String(value)))].sort((a,b)=>
      a.localeCompare(b,undefined,{sensitivity:'base'})
    );
    select.replaceChildren();
    const all=document.createElement('option');
    all.value='all';
    all.textContent=allLabel;
    select.appendChild(all);
    for(const value of unique){
      const option=document.createElement('option');
      option.value=value;
      option.textContent=value;
      select.appendChild(option);
    }
    select.value=unique.includes(current)?current:'all';
  }

  function syncHackerOneAttentionFilterOptions(items){
    updateAttentionSelectOptions(
      'h1AttentionProgramFilter',
      items.map(item=>item?.team_handle),
      'Tous les programmes'
    );
    updateAttentionSelectOptions(
      'h1AttentionStateFilter',
      items.map(item=>item?.state||'awaiting-sync'),
      'Tous les états'
    );
  }

  function currentHackerOneAttentionFilters(){
    return {
      version:1,
      search:String(el('h1AttentionSearch').value||''),
      read:String(el('h1AttentionReadFilter').value||'all'),
      bucket:String(el('h1AttentionBucketFilter').value||'all'),
      program:String(el('h1AttentionProgramFilter').value||'all'),
      state:String(el('h1AttentionStateFilter').value||'all'),
      bounty:String(el('h1AttentionBountyFilter').value||'all'),
      recent:String(el('h1AttentionRecentFilter').value||'all'),
      sort:String(el('h1AttentionSort').value||'priority')
    };
  }

  function loadHackerOneAttentionFilters(){
    try{
      const parsed=JSON.parse(localStorage.getItem(ATTENTION_FILTER_STORAGE_KEY)||'null');
      if(parsed&&parsed.version===1)return parsed;
    }catch(_error){}
    return attentionFilterMemory&&attentionFilterMemory.version===1
      ?{...attentionFilterMemory}
      :null;
  }

  function saveHackerOneAttentionFilters(){
    const state=currentHackerOneAttentionFilters();
    attentionFilterMemory={...state};
    try{
      localStorage.setItem(ATTENTION_FILTER_STORAGE_KEY,JSON.stringify(state));
    }catch(_error){}
    return state;
  }

  function setSelectValueIfAvailable(id,value,fallback='all'){
    const select=el(id);
    const desired=String(value||fallback);
    const exists=[...select.options].some(option=>option.value===desired);
    select.value=exists?desired:fallback;
  }

  function applyHackerOneAttentionFilters(state,{persist=true}={}){
    const value=state&&state.version===1?state:{version:1};
    el('h1AttentionSearch').value=String(value.search||'');
    setSelectValueIfAvailable('h1AttentionReadFilter',value.read);
    setSelectValueIfAvailable('h1AttentionBucketFilter',value.bucket);
    setSelectValueIfAvailable('h1AttentionProgramFilter',value.program);
    setSelectValueIfAvailable('h1AttentionStateFilter',value.state);
    setSelectValueIfAvailable('h1AttentionBountyFilter',value.bounty);
    setSelectValueIfAvailable('h1AttentionRecentFilter',value.recent);
    setSelectValueIfAvailable('h1AttentionSort',value.sort,'priority');
    if(persist)saveHackerOneAttentionFilters();
  }

  function restoreHackerOneAttentionFilters(){
    if(attentionFiltersRestored)return;
    attentionFiltersRestored=true;
    const saved=loadHackerOneAttentionFilters();
    if(saved)applyHackerOneAttentionFilters(saved,{persist:false});
  }

  const ATTENTION_SAVED_VIEWS={
    action:{
      label:'À traiter',
      filters:{version:1,search:'',read:'all',bucket:'action-required',program:'all',state:'all',bounty:'all',recent:'all',sort:'priority'}
    },
    today:{
      label:'Nouveaux aujourd’hui',
      filters:{version:1,search:'',read:'all',bucket:'all',program:'all',state:'all',bounty:'all',recent:'today',sort:'newest'}
    },
    bounty:{
      label:'Avec bounty',
      filters:{version:1,search:'',read:'all',bucket:'all',program:'all',state:'all',bounty:'with',recent:'all',sort:'newest'}
    },
    nmi:{
      label:'NMI',
      filters:{version:1,search:'',read:'all',bucket:'action-required',program:'all',state:'needs-more-info',bounty:'all',recent:'all',sort:'newest'}
    },
    unread:{
      label:'Non lus',
      filters:{version:1,search:'',read:'unread',bucket:'all',program:'all',state:'all',bounty:'all',recent:'all',sort:'newest'}
    }
  };

  function sameAttentionFilters(left,right){
    return ['search','read','bucket','program','state','bounty','recent','sort']
      .every(key=>String(left?.[key]||'')===String(right?.[key]||''));
  }

  function renderHackerOneAttentionViewState(){
    const current=currentHackerOneAttentionFilters();
    const builtIn=Object.values(ATTENTION_SAVED_VIEWS)
      .find(view=>sameAttentionFilters(current,view.filters));
    if(builtIn){
      el('h1AttentionViewState').textContent=builtIn.label;
      return;
    }
    const custom=loadHackerOneAttentionCustomViews().views
      .find(view=>sameAttentionFilters(current,view.filters));
    el('h1AttentionViewState').textContent=custom?custom.name:'Vue personnalisée';
  }

  function applyHackerOneAttentionSavedView(name){
    const view=ATTENTION_SAVED_VIEWS[String(name||'')];
    if(!view)return;
    applyHackerOneAttentionFilters(view.filters);
    renderHackerOneAttentionViewState();
    if(latestAttentionPayload)renderHackerOneAttention(latestAttentionPayload);
  }

  function normalizeAttentionCustomViewName(value){
    return String(value||'').replace(/\s+/g,' ').trim().slice(0,ATTENTION_CUSTOM_VIEW_NAME_LIMIT);
  }

  function sanitizeAttentionCustomViewFilters(value){
    if(!value||value.version!==1)return null;
    const allowed={
      read:['all','unread','read'],
      bucket:['all','action-required','active','awaiting-sync','resolved','duplicate','informative','closed-other','other'],
      bounty:['all','with','without'],
      recent:['all','today','24h','7d','30d'],
      sort:['priority','newest','oldest','program','state']
    };
    const filter={
      version:1,
      search:String(value.search||'').slice(0,500),
      read:String(value.read||'all'),
      bucket:String(value.bucket||'all'),
      program:String(value.program||'all').slice(0,160),
      state:String(value.state||'all').slice(0,80),
      bounty:String(value.bounty||'all'),
      recent:String(value.recent||'all'),
      sort:String(value.sort||'priority')
    };
    for(const key of ['read','bucket','bounty','recent','sort']){
      if(!allowed[key].includes(filter[key]))return null;
    }
    return filter;
  }

  function loadHackerOneAttentionCustomViews(){
    let parsed=null;
    try{
      parsed=JSON.parse(localStorage.getItem(ATTENTION_CUSTOM_VIEWS_STORAGE_KEY)||'null');
    }catch(_error){}
    const source=parsed&&parsed.version===1?parsed:attentionCustomViewsMemory;
    const views=[];
    for(const raw of Array.isArray(source?.views)?source.views:[]){
      const name=normalizeAttentionCustomViewName(raw?.name);
      const filters=sanitizeAttentionCustomViewFilters(raw?.filters);
      if(!name||!filters)continue;
      views.push({name,filters});
      if(views.length>=ATTENTION_CUSTOM_VIEW_LIMIT)break;
    }
    return {version:1,views};
  }

  function saveHackerOneAttentionCustomViews(state){
    const normalized=loadHackerOneAttentionCustomViewsFromValue(state);
    attentionCustomViewsMemory=normalized;
    try{
      localStorage.setItem(ATTENTION_CUSTOM_VIEWS_STORAGE_KEY,JSON.stringify(normalized));
    }catch(_error){}
    return normalized;
  }

  function loadHackerOneAttentionCustomViewsFromValue(state){
    const views=[];
    for(const raw of Array.isArray(state?.views)?state.views:[]){
      const name=normalizeAttentionCustomViewName(raw?.name);
      const filters=sanitizeAttentionCustomViewFilters(raw?.filters);
      if(!name||!filters)continue;
      views.push({name,filters});
      if(views.length>=ATTENTION_CUSTOM_VIEW_LIMIT)break;
    }
    return {version:1,views};
  }

  function renderHackerOneAttentionCustomViews(){
    const select=el('h1AttentionCustomView');
    const current=String(select.value||'');
    const state=loadHackerOneAttentionCustomViews();
    select.replaceChildren();
    const placeholder=document.createElement('option');
    placeholder.value='';
    placeholder.textContent='Vues personnalisées enregistrées';
    select.appendChild(placeholder);
    state.views.forEach((view,index)=>{
      const option=document.createElement('option');
      option.value=String(index);
      option.textContent=view.name;
      select.appendChild(option);
    });
    if(current&&Number(current)<state.views.length)select.value=current;
    el('h1AttentionDeleteCustomView').disabled=!select.value;
  }

  function selectedHackerOneAttentionCustomView(){
    const state=loadHackerOneAttentionCustomViews();
    const index=Number(el('h1AttentionCustomView').value);
    return Number.isInteger(index)&&index>=0&&index<state.views.length
      ?{...state.views[index],index}
      :null;
  }

  function saveCurrentHackerOneAttentionCustomView(){
    const name=normalizeAttentionCustomViewName(el('h1AttentionCustomViewName').value);
    if(!name){
      el('h1AttentionUpdated').textContent='Nom de vue requis.';
      return;
    }
    const filters=sanitizeAttentionCustomViewFilters(currentHackerOneAttentionFilters());
    if(!filters)return;
    const state=loadHackerOneAttentionCustomViews();
    const existing=state.views.findIndex(view=>
      view.name.localeCompare(name,undefined,{sensitivity:'accent'})===0
    );
    if(existing>=0){
      state.views[existing]={name,filters};
    }else{
      if(state.views.length>=ATTENTION_CUSTOM_VIEW_LIMIT){
        el('h1AttentionUpdated').textContent='Maximum de 20 vues personnalisées atteint.';
        return;
      }
      state.views.push({name,filters});
    }
    saveHackerOneAttentionCustomViews(state);
    renderHackerOneAttentionCustomViews();
    const updated=loadHackerOneAttentionCustomViews();
    const index=updated.views.findIndex(view=>view.name===name);
    if(index>=0)el('h1AttentionCustomView').value=String(index);
    el('h1AttentionCustomViewName').value='';
    el('h1AttentionDeleteCustomView').disabled=false;
    renderHackerOneAttentionViewState();
    el('h1AttentionUpdated').textContent='Vue personnalisée enregistrée : '+name;
  }

  function applySelectedHackerOneAttentionCustomView(){
    const selected=selectedHackerOneAttentionCustomView();
    el('h1AttentionDeleteCustomView').disabled=!selected;
    if(!selected)return;
    applyHackerOneAttentionFilters(selected.filters);
    renderHackerOneAttentionViewState();
    if(latestAttentionPayload)renderHackerOneAttention(latestAttentionPayload);
  }

  function deleteSelectedHackerOneAttentionCustomView(){
    const selected=selectedHackerOneAttentionCustomView();
    if(!selected)return;
    const state=loadHackerOneAttentionCustomViews();
    state.views.splice(selected.index,1);
    saveHackerOneAttentionCustomViews(state);
    el('h1AttentionCustomView').value='';
    renderHackerOneAttentionCustomViews();
    renderHackerOneAttentionViewState();
    el('h1AttentionUpdated').textContent='Vue personnalisée supprimée : '+selected.name;
  }

  function hackerOneAttentionMatchesRecent(item,filterValue){
    if(filterValue==='all')return true;
    const timestamp=Date.parse(String(item?.last_observed_at||''));
    if(!Number.isFinite(timestamp))return false;
    if(filterValue==='today'){
      const observed=new Date(timestamp);
      const now=new Date();
      return observed.getFullYear()===now.getFullYear()&&
        observed.getMonth()===now.getMonth()&&
        observed.getDate()===now.getDate();
    }
    const windows={
      '24h':24*60*60*1000,
      '7d':7*24*60*60*1000,
      '30d':30*24*60*60*1000
    };
    const windowMs=windows[filterValue];
    return Number.isFinite(windowMs)&&timestamp>=Date.now()-windowMs;
  }

  function filterAndSortHackerOneAttention(items,seen){
    const query=attentionText(el('h1AttentionSearch').value.trim());
    const readFilter=el('h1AttentionReadFilter').value;
    const bucketFilter=el('h1AttentionBucketFilter').value;
    const programFilter=el('h1AttentionProgramFilter').value;
    const stateFilter=el('h1AttentionStateFilter').value;
    const bountyFilter=el('h1AttentionBountyFilter').value;
    const recentFilter=el('h1AttentionRecentFilter').value;
    const sort=el('h1AttentionSort').value;

    const source=items.map((item,index)=>({item,index}));
    const filtered=source.filter(({item})=>{
      const unread=isAttentionUnread(item,seen);
      if(readFilter==='unread'&&!unread)return false;
      if(readFilter==='read'&&unread)return false;
      if(bucketFilter!=='all'&&String(item?.bucket||'')!==bucketFilter)return false;
      if(programFilter!=='all'&&String(item?.team_handle||'')!==programFilter)return false;
      const state=String(item?.state||'awaiting-sync');
      if(stateFilter!=='all'&&state!==stateFilter)return false;
      const hasBounty=Boolean(item?.bounty);
      if(bountyFilter==='with'&&!hasBounty)return false;
      if(bountyFilter==='without'&&hasBounty)return false;
      if(!hackerOneAttentionMatchesRecent(item,recentFilter))return false;
      if(query){
        const haystack=attentionText([
          item?.campaign_name,
          item?.campaign_id,
          item?.team_handle,
          item?.remote_report_id,
          item?.state,
          item?.bucket,
          item?.needs_more_info?.message,
          item?.latest_public_activity?.message,
          item?.latest_public_activity?.activity_type
        ].filter(Boolean).join(' '));
        if(!haystack.includes(query))return false;
      }
      return true;
    });

    const compareDate=(left,right)=>{
      const a=Date.parse(String(left.item?.last_observed_at||''))||0;
      const b=Date.parse(String(right.item?.last_observed_at||''))||0;
      return a-b;
    };
    if(sort==='newest')filtered.sort((a,b)=>compareDate(b,a));
    else if(sort==='oldest')filtered.sort(compareDate);
    else if(sort==='program'){
      filtered.sort((a,b)=>String(a.item?.team_handle||'').localeCompare(
        String(b.item?.team_handle||''),undefined,{sensitivity:'base'}
      ));
    }else if(sort==='state'){
      filtered.sort((a,b)=>String(a.item?.state||'').localeCompare(
        String(b.item?.state||''),undefined,{sensitivity:'base'}
      ));
    }else{
      filtered.sort((a,b)=>a.index-b.index);
    }
    return filtered.map(entry=>entry.item);
  }

  function visibleHackerOneAttentionItems(){
    const items=Array.isArray(latestAttentionPayload?.items)?latestAttentionPayload.items:[];
    const seen=ensureAttentionBaseline(items);
    return filterAndSortHackerOneAttention(items,seen);
  }

  function markVisibleHackerOneAttentionSeen(){
    const visible=visibleHackerOneAttentionItems();
    if(!visible.length)return;
    const state=loadAttentionSeen();
    state.initialized=true;
    for(const item of visible){
      const cursor=String(item?.notification_cursor||'');
      if(cursor)state.seen[attentionSeenKey(item)]=cursor;
    }
    saveAttentionSeen(state);
    if(latestAttentionPayload)renderHackerOneAttention(latestAttentionPayload);
  }

  function attentionExportRows(){
    const seen=loadAttentionSeen();
    return visibleHackerOneAttentionItems().map(item=>({
      campaign_id:String(item?.campaign_id||''),
      campaign_name:String(item?.campaign_name||''),
      program:String(item?.team_handle||''),
      remote_report_id:String(item?.remote_report_id||''),
      state:item?.state===null?null:String(item?.state||''),
      bucket:String(item?.bucket||''),
      action_required:Boolean(item?.action_required),
      bounty_amount:item?.bounty?.amount==null?null:String(item.bounty.amount),
      bounty_bonus_amount:item?.bounty?.bonus_amount==null?null:String(item.bounty.bonus_amount),
      last_observed_at:item?.last_observed_at||null,
      unread:isAttentionUnread(item,seen),
      notification_kind:String(item?.notification_kind||'')
    }));
  }

  function downloadAttentionExport(filename,mimeType,content){
    const blob=new Blob([content],{type:mimeType});
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download=filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function exportHackerOneAttentionJson(){
    const rows=attentionExportRows();
    if(!rows.length)return;
    const payload={
      exported_at:new Date().toISOString(),
      filters:currentHackerOneAttentionFilters(),
      count:rows.length,
      rows
    };
    downloadAttentionExport(
      'hackerone-attention-'+new Date().toISOString().slice(0,10)+'.json',
      'application/json;charset=utf-8',
      JSON.stringify(payload,null,2)
    );
  }

  function csvCell(value){
    const text=value==null?'':String(value);
    return '"'+text.replaceAll('"','""')+'"';
  }

  function exportHackerOneAttentionCsv(){
    const rows=attentionExportRows();
    if(!rows.length)return;
    const columns=[
      'campaign_id','campaign_name','program','remote_report_id','state','bucket',
      'action_required','bounty_amount','bounty_bonus_amount','last_observed_at',
      'unread','notification_kind'
    ];
    const csv=[
      columns.join(','),
      ...rows.map(row=>columns.map(column=>csvCell(row[column])).join(','))
    ].join('\n');
    downloadAttentionExport(
      'hackerone-attention-'+new Date().toISOString().slice(0,10)+'.csv',
      'text/csv;charset=utf-8',
      '\uFEFF'+csv
    );
  }

  async function openNextHackerOneActionRequired(){
    const visible=visibleHackerOneAttentionItems()
      .filter(item=>String(item?.bucket||'')==='action-required');
    if(!visible.length)return;
    const currentIndex=visible.findIndex(
      item=>String(item?.campaign_id||'')===String(runMonitorCampaignId||'')
    );
    const next=visible[(currentIndex+1)%visible.length];
    await focusHackerOneAttentionCampaign(next);
  }

  function resetHackerOneAttentionFilters(){
    applyHackerOneAttentionFilters({
      version:1,
      search:'',
      read:'all',
      bucket:'all',
      program:'all',
      state:'all',
      bounty:'all',
      recent:'all',
      sort:'priority'
    });
    renderHackerOneAttentionViewState();
    if(latestAttentionPayload)renderHackerOneAttention(latestAttentionPayload);
  }

  function renderHackerOneAttention(payload){
    latestAttentionPayload=payload;
    const summary=payload?.summary||{};
    el('h1AttentionAction').textContent=String(Number(summary.action_required)||0);
    el('h1AttentionActive').textContent=String(Number(summary.active)||0);
    el('h1AttentionBounty').textContent=String(Number(summary.with_bounty)||0);
    el('h1AttentionResolved').textContent=String(Number(summary.resolved)||0);
    el('h1AttentionDuplicate').textContent=String(Number(summary.duplicate)||0);
    el('h1AttentionInformative').textContent=String(Number(summary.informative)||0);

    const list=el('h1AttentionList');
    list.replaceChildren();
    const items=Array.isArray(payload?.items)?payload.items:[];
    syncHackerOneAttentionFilterOptions(items);
    renderHackerOneAttentionCustomViews();
    restoreHackerOneAttentionFilters();
    renderHackerOneAttentionViewState();
    const seen=ensureAttentionBaseline(items);
    const unreadCount=items.filter(item=>isAttentionUnread(item,seen)).length;
    const unread=el('h1AttentionUnread');
    unread.textContent=unreadCount+' non lu'+(unreadCount>1?'s':'');
    unread.className='pill '+(unreadCount?'warn':'ok');
    el('h1AttentionMarkAll').disabled=unreadCount===0;

    const visible=filterAndSortHackerOneAttention(items,seen);
    const visibleUnread=visible.filter(item=>isAttentionUnread(item,seen)).length;
    el('h1AttentionMarkVisible').disabled=visibleUnread===0;
    el('h1AttentionOpenNextAction').disabled=
      !visible.some(item=>String(item?.bucket||'')==='action-required');
    el('h1AttentionExportJson').disabled=visible.length===0;
    el('h1AttentionExportCsv').disabled=visible.length===0;
    el('h1AttentionResults').textContent=
      visible.length+' / '+items.length+' report'+(items.length>1?'s':'')+' affiché'+
      (visible.length>1?'s':'');

    if(!visible.length){
      list.textContent=items.length
        ?'Aucun report ne correspond aux filtres.'
        :'Aucun report HackerOne local.';
      return;
    }
    for(const item of visible){
      const row=document.createElement('div');
      row.className='scope-asset-row';
      const itemUnread=isAttentionUnread(item,seen);

      const info=document.createElement('div');
      const title=document.createElement('strong');
      title.textContent=String(item.campaign_name||item.campaign_id||'Campagne');
      const meta=document.createElement('div');
      meta.className='muted compact';
      const parts=[
        String(item.team_handle||'programme'),
        'report #'+String(item.remote_report_id||'—'),
        hackerOneAttentionLabel(item)
      ];
      if(item.bounty?.amount)parts.push('bounty '+String(item.bounty.amount));
      if(item.needs_more_info?.message){
        parts.push('NMI: '+String(item.needs_more_info.message));
      }
      if(item.last_observed_at){
        const date=new Date(item.last_observed_at);
        if(!Number.isNaN(date.getTime()))parts.push(date.toLocaleString());
      }
      meta.textContent=parts.join(' · ');
      info.append(title,meta);

      if(itemUnread){
        const notice=document.createElement('div');
        notice.className='compact warn-text';
        notice.textContent=hackerOneNotificationLabel(item);
        info.appendChild(notice);
      }

      const actions=document.createElement('div');
      actions.className='button-row';
      if(itemUnread){
        const seenButton=document.createElement('button');
        seenButton.type='button';
        seenButton.className='secondary';
        seenButton.textContent='Marquer vu';
        seenButton.addEventListener('click',()=>markHackerOneAttentionSeen(item));
        actions.appendChild(seenButton);
      }

      const open=document.createElement('button');
      open.type='button';
      open.className='secondary';
      open.textContent='Ouvrir';
      open.addEventListener('click',()=>void focusHackerOneAttentionCampaign(item));
      actions.appendChild(open);

      row.append(info,actions);
      list.appendChild(row);
    }
  }

  async function refreshHackerOneAttention(){
    const button=el('h1AttentionRefresh');
    if(button)button.disabled=true;
    try{
      const payload=await api('/hackerone/attention?limit=200');
      renderHackerOneAttention(payload);
      el('h1AttentionUpdated').textContent='Actualisé à '+new Date().toLocaleTimeString()+
        ' · données locales auditées';
    }catch(error){
      el('h1AttentionUpdated').textContent='Centre d’attention indisponible : '+error.message;
    }finally{
      if(button)button.disabled=false;
    }
  }

  function startHackerOneAttentionMonitor(){
    if(attentionTimer!==null)clearInterval(attentionTimer);
    void refreshHackerOneAttention();
    attentionTimer=setInterval(()=>void refreshHackerOneAttention(),15000);
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
      await refreshRunMonitor(runMonitorCampaignId);
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

  function hackerOneActivityLabel(event){
    const type=String(event?.activity_type||'');
    if(type==='activity-comment')return 'Commentaire public';
    if(type==='activity-bounty-awarded')return 'Bounty attribuée';
    if(type==='activity-bug-duplicate')return 'Classé duplicate';
    if(type==='activity-bug-informative')return 'Classé informative';
    if(type==='activity-bug-resolved')return 'Résolu';
    return type||'Activité HackerOne';
  }

  function renderHackerOneReportTimeline(campaignData,artifactId){
    const timeline=el('h1ReportTimeline');
    const summary=el('h1ActivitySummary');
    const all=(Array.isArray(campaignData?.events)?campaignData.events:[])
      .filter(event=>String(event?.artifact_id||'')===String(artifactId||''));
    const activities=all.filter(event=>event?.type==='hackerone_public_activity_observed');
    const statusEvents=all.filter(event=>event?.type==='hackerone_report_status_synced');
    const needsInfo=all.filter(event=>event?.type==='hackerone_needs_more_info_observed');

    if(!activities.length){
      summary.className='muted compact';
      summary.textContent='Aucune activité publique HackerOne synchronisée.';
    }else{
      const bounty=activities.filter(event=>event?.activity_type==='activity-bounty-awarded');
      const comments=activities.filter(event=>event?.activity_type==='activity-comment');
      const classifications=activities.filter(event=>
        ['activity-bug-duplicate','activity-bug-informative','activity-bug-resolved']
          .includes(String(event?.activity_type||''))
      );
      summary.className='muted compact ok-text';
      summary.textContent=activities.length+' activité(s) publique(s) · '+
        comments.length+' commentaire(s) · '+bounty.length+' bounty · '+
        classifications.length+' changement(s) de classification';
    }

    const events=[...statusEvents,...needsInfo,...activities]
      .sort((a,b)=>{
        const left=Date.parse(String(a?.observed_at||a?.created_at||''))||0;
        const right=Date.parse(String(b?.observed_at||b?.created_at||''))||0;
        return left-right;
      })
      .slice(-12);
    if(!events.length){
      timeline.className='muted compact';
      timeline.textContent='Aucun historique HackerOne synchronisé.';
      return;
    }

    timeline.className='muted compact';
    timeline.replaceChildren();
    const list=document.createElement('ol');
    list.className='compact';
    for(const event of events){
      const item=document.createElement('li');
      const observed=event?.observed_at
        ?new Date(event.observed_at).toLocaleString()
        :'heure inconnue';
      if(event?.type==='hackerone_report_status_synced'){
        item.textContent='État : '+String(event?.state||'unknown')+' · '+observed;
      }else if(event?.type==='hackerone_needs_more_info_observed'){
        item.textContent='Informations demandées · '+observed;
      }else{
        let detail=hackerOneActivityLabel(event);
        const message=String(event?.message||'').trim();
        if(event?.activity_type==='activity-bounty-awarded'){
          const amount=String(event?.bounty_amount||'').trim();
          const bonus=String(event?.bonus_amount||'').trim();
          if(amount)detail+=' · $'+amount;
          if(bonus&&bonus!=='0')detail+=' + bonus $'+bonus;
        }else if(event?.activity_type==='activity-bug-duplicate'){
          const original=String(event?.original_report_id||'').trim();
          if(original)detail+=' · report #'+original;
        }
        if(message)detail+=' · '+message;
        item.textContent=detail+' · '+observed;
      }
      list.appendChild(item);
    }
    timeline.appendChild(list);
  }

  function renderHackerOneRemoteReportStatus(remoteStatus){
    const node=el('h1ReportRemoteStatus');
    if(!remoteStatus){
      node.className='muted compact';
      node.textContent='Aucun rapport HackerOne distant suivi.';
      return;
    }
    if(remoteStatus.error){
      node.className='muted compact err-text';
      node.textContent='Statut HackerOne distant indisponible : '+remoteStatus.error;
      return;
    }
    const remoteId=String(remoteStatus.remote_report_id||'');
    const state=String(remoteStatus.state||'unknown');
    const activity=remoteStatus.last_activity_at
      ?' · activité '+new Date(remoteStatus.last_activity_at).toLocaleString()
      :'';
    node.className='muted compact ok-text';
    node.textContent='HackerOne report '+remoteId+' · '+state+activity;
  }

  function renderHackerOneNeedsInfo(remoteStatus,needsInfoDraft){
    const panel=el('h1NeedsInfoPanel');
    const request=remoteStatus?.needs_more_info;
    if(!request){
      panel.classList.add('hidden');
      el('h1NeedsInfoRequest').textContent='';
      el('h1NeedsInfoDraft').textContent='';
      el('h1NeedsInfoCopy').disabled=true;
      delete el('h1NeedsInfoCopy').dataset.draft;
      return;
    }
    panel.classList.remove('hidden');
    el('h1NeedsInfoRequest').textContent='Demande HackerOne : '+String(request.message||'');
    if(needsInfoDraft?.error){
      el('h1NeedsInfoDraft').textContent='Brouillon indisponible : '+needsInfoDraft.error;
      el('h1NeedsInfoCopy').disabled=true;
      delete el('h1NeedsInfoCopy').dataset.draft;
      return;
    }
    const draft=String(needsInfoDraft?.draft_markdown||'');
    el('h1NeedsInfoDraft').textContent=draft;
    el('h1NeedsInfoCopy').dataset.draft=draft;
    el('h1NeedsInfoCopy').disabled=!draft;
  }

  async function copyHackerOneNeedsInfoDraft(){
    const button=el('h1NeedsInfoCopy');
    const draft=String(button.dataset.draft||'');
    if(!draft)return;
    try{
      await navigator.clipboard.writeText(draft);
      button.textContent='Brouillon copié';
      setTimeout(()=>{button.textContent='Copier le brouillon de réponse';},1500);
    }catch(error){
      el('h1NeedsInfoDraft').textContent='Copie impossible : '+error.message+'\n\n'+draft;
    }
  }

  function renderRunMonitor(campaignData,control,artifacts,reportReadiness,reportApproval,remoteReportStatus,needsInfoDraft){
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
    renderHackerOneRemoteReportStatus(remoteReportStatus);
    renderHackerOneNeedsInfo(remoteReportStatus,needsInfoDraft);
    const reportArtifact=(Array.isArray(artifacts)?artifacts:[]).find(item=>
      item?.kind==='report'&&String(item?.idempotency_key||'').endsWith(':report:hackerone')
    );
    renderHackerOneReportTimeline(campaignData,reportArtifact?.id||'');
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
      let remoteReportStatus=null;
      let needsInfoDraft=null;
      if(reportArtifact?.id){
        try{
          reportApproval=await api(
            '/campaigns/'+encoded+
            '/reports/'+encodeURIComponent(reportArtifact.id)+'/approval'
          );
        }catch(error){
          reportApproval={error:error.message};
        }
        const submitted=(Array.isArray(campaignData?.events)?campaignData.events:[]).some(event=>
          event?.type==='hackerone_report_submitted'&&
          String(event?.artifact_id||'')===String(reportArtifact.id)
        );
        if(submitted){
          try{
            remoteReportStatus=await api(
              '/campaigns/'+encoded+
              '/reports/'+encodeURIComponent(reportArtifact.id)+'/hackerone-status'
            );
            if(remoteReportStatus?.needs_more_info){
              try{
                needsInfoDraft=await api(
                  '/campaigns/'+encoded+
                  '/reports/'+encodeURIComponent(reportArtifact.id)+
                  '/hackerone-needs-info-draft'
                );
              }catch(error){
                needsInfoDraft={error:error.message};
              }
            }
          }catch(error){
            remoteReportStatus={error:error.message};
          }
        }
      }
      renderRunMonitor(
        campaignData,
        control,
        artifacts,
        reportReadiness,
        reportApproval,
        remoteReportStatus,
        needsInfoDraft
      );
      if(typeof refreshDashboard==='function'&&campaign?.id===campaignId){
        await refreshDashboard();
      }
      if(['completed','cancelled','failed'].includes(String(campaignData?.state||''))){
        stopRunMonitor();
      }
      return {
        campaign:campaignData,
        control,
        artifacts,
        reportReadiness,
        reportApproval,
        remoteReportStatus,
        needsInfoDraft,
        encoded
      };
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

  function loadQuickPrefs(){
    try{
      const parsed=JSON.parse(localStorage.getItem(QUICK_PREFS_STORAGE_KEY)||'null');
      if(parsed&&parsed.version===1){
        return {
          version:1,
          auto_resume:parsed.auto_resume!==false,
          auto_preview:parsed.auto_preview!==false,
          batch_auto_limit:[3,5,10,20].includes(Number(parsed.batch_auto_limit))
            ?Number(parsed.batch_auto_limit):5,
          batch_auto_min_score:[0,25,50,75].includes(Number(parsed.batch_auto_min_score))
            ?Number(parsed.batch_auto_min_score):50,
          batch_mode:['sequential','parallel'].includes(String(parsed.batch_mode))
            ?String(parsed.batch_mode):'sequential'
        };
      }
    }catch(_error){}
    return {
      version:1,
      auto_resume:true,
      auto_preview:true,
      batch_auto_limit:5,
      batch_auto_min_score:50,
      batch_mode:'sequential'
    };
  }

  function applyQuickPrefs(){
    const prefs=loadQuickPrefs();
    if(el('h1QuickAutoResume'))el('h1QuickAutoResume').checked=prefs.auto_resume;
    if(el('h1QuickAutoPreview'))el('h1QuickAutoPreview').checked=prefs.auto_preview;
    if(el('h1BatchAutoLimit'))el('h1BatchAutoLimit').value=String(prefs.batch_auto_limit);
    if(el('h1BatchAutoMinScore'))el('h1BatchAutoMinScore').value=String(prefs.batch_auto_min_score);
    if(el('h1BatchMode'))el('h1BatchMode').value=prefs.batch_mode;
    return prefs;
  }

  function saveQuickPrefs(){
    const prefs={
      version:1,
      auto_resume:Boolean(el('h1QuickAutoResume')?.checked),
      auto_preview:Boolean(el('h1QuickAutoPreview')?.checked),
      batch_auto_limit:Number(el('h1BatchAutoLimit')?.value||5),
      batch_auto_min_score:Number(el('h1BatchAutoMinScore')?.value||50),
      batch_mode:String(el('h1BatchMode')?.value||'sequential')
    };
    try{localStorage.setItem(QUICK_PREFS_STORAGE_KEY,JSON.stringify(prefs));}catch(_error){}
    return prefs;
  }

  function rememberLastProgram(handle){
    if(!handle)return;
    try{localStorage.setItem(QUICK_LAST_PROGRAM_STORAGE_KEY,String(handle));}catch(_error){}
  }

  function lastProgramHandle(){
    try{return String(localStorage.getItem(QUICK_LAST_PROGRAM_STORAGE_KEY)||'');}
    catch(_error){return '';}
  }

  function normalizeServerReviewProfile(profile){
    if(!profile||typeof profile!=='object')return null;
    const policy=profile.policy&&typeof profile.policy==='object'?profile.policy:{};
    return {
      authorization_reference:String(policy.authorization_reference||''),
      policy_version:String(policy.policy_version||''),
      reviewed_at:String(policy.reviewed_at||profile.saved_at||''),
      reviewed_by:String(policy.reviewed_by||''),
      max_requests_per_second:Number(policy.max_requests_per_second)||0,
      safe_harbor_confirmed:Boolean(policy.safe_harbor_confirmed),
      automated_scanning:Boolean(policy.automated_scanning),
      test_account_required:Boolean(policy.test_account_required),
      test_account_constraints:String(policy.test_account_constraints||''),
      additional_restrictions:Array.isArray(policy.additional_restrictions)
        ?policy.additional_restrictions:[],
      program_notes:String(policy.program_notes||''),
      primary_url:String(profile.preferred_primary_url||''),
      saved_at:String(profile.saved_at||''),
      source:'server'
    };
  }

  function exactQuickProfile(key){
    if(!key)return null;
    const local=quickProfiles()[key];
    if(local)return local;
    return normalizeServerReviewProfile(serverReviewProfiles[key]);
  }

  async function loadServerReviewProfiles(){
    try{
      const result=await api('/imports/hackerone/review-profiles');
      const profiles=Array.isArray(result?.profiles)?result.profiles:[];
      serverReviewProfiles=Object.fromEntries(
        profiles
          .filter(profile=>profile?.id)
          .map(profile=>[String(profile.id),profile])
      );
    }catch(_error){
      serverReviewProfiles={};
    }
    return serverReviewProfiles;
  }

  function quickProfiles(){
    try{
      const parsed=JSON.parse(localStorage.getItem(QUICK_PROFILE_STORAGE_KEY)||'{}');
      return parsed&&typeof parsed==='object'&&!Array.isArray(parsed)?parsed:{};
    }catch(_error){return {};}
  }

  function quickProfileKey(binding=remoteBinding){
    if(!binding?.handle||!binding?.snapshot_sha256)return '';
    return String(binding.handle)+'@'+String(binding.snapshot_sha256);
  }

  function saveQuickProfiles(profiles){
    const entries=Object.entries(profiles||{}).slice(-QUICK_PROFILE_LIMIT);
    try{localStorage.setItem(QUICK_PROFILE_STORAGE_KEY,JSON.stringify(Object.fromEntries(entries)));}catch(_error){}
  }

  function localDateTimeValue(date=new Date()){
    const offset=date.getTimezoneOffset()*60000;
    return new Date(date.getTime()-offset).toISOString().slice(0,16);
  }

  function quickTargetSuggestions(snapshot){
    const list=el('h1TargetSuggestions');
    if(!list)return;
    list.replaceChildren();
    const assets=Array.isArray(snapshot?.preview?.assets)?snapshot.preview.assets:[];
    const values=[];
    for(const asset of assets){
      if(!asset?.eligible_for_submission||!asset?.compatible)continue;
      const type=String(asset.asset_type||'').toLowerCase();
      const identifier=String(asset.identifier||'').trim();
      let value='';
      if(type==='domain'&&identifier&&!identifier.includes('*'))value='https://'+identifier.replace(/\.$/,'');
      else if(type==='url'&&/^https?:\/\//i.test(identifier))value=identifier;
      if(value&&!values.includes(value))values.push(value);
    }
    for(const value of values.slice(0,100)){
      const option=document.createElement('option');
      option.value=value;
      list.appendChild(option);
    }
    return values;
  }

  function setQuickState(label,type=''){
    const state=el('h1QuickState');
    if(!state)return;
    state.textContent=label;
    state.className='pill'+(type?' '+type:'');
  }

  function restoreQuickProfile(snapshot){
    const key=quickProfileKey();
    const profile=exactQuickProfile(key);
    const reviewer=localStorage.getItem(QUICK_REVIEWER_STORAGE_KEY)||'';
    const targets=quickTargetSuggestions(snapshot)||[];

    if(profile){
      el('h1Auth').value=String(profile.authorization_reference||'');
      el('h1PolicyVersion').value=String(profile.policy_version||'');
      const storedReviewAt=String(profile.reviewed_at||profile.saved_at||'');
      const storedReviewDate=storedReviewAt?new Date(storedReviewAt):new Date();
      el('h1ReviewedAt').value=localDateTimeValue(
        Number.isNaN(storedReviewDate.getTime())?new Date():storedReviewDate
      );
      el('h1ReviewedBy').value=String(profile.reviewed_by||reviewer||'');
      el('h1Rps').value=String(profile.max_requests_per_second||'');
      el('h1SafeHarbor').checked=Boolean(profile.safe_harbor_confirmed);
      el('h1Automation').checked=Boolean(profile.automated_scanning);
      el('h1TestAccountRequired').checked=Boolean(profile.test_account_required);
      el('h1TestAccountConstraints').value=String(profile.test_account_constraints||'');
      el('h1AdditionalRestrictions').value=Array.isArray(profile.additional_restrictions)
        ?profile.additional_restrictions.join('\n'):'';
      el('h1Notes').value=String(profile.program_notes||'');
      if(profile.primary_url)el('h1Url').value=String(profile.primary_url);
      setQuickState('profil réutilisé','ok');
      el('h1QuickSummary').textContent='Profil validé retrouvé pour ce fingerprint exact. La prévisualisation peut être relancée automatiquement; seule la confirmation finale reste manuelle.';
      if(el('h1AdvancedSettings'))el('h1AdvancedSettings').open=false;
      return true;
    }

    if(!el('h1Auth').value.trim()&&remoteBinding?.handle){
      el('h1Auth').value='https://hackerone.com/'+encodeURIComponent(remoteBinding.handle)+'?type=team';
    }
    if(!el('h1PolicyVersion').value.trim())el('h1PolicyVersion').value=new Date().toISOString().slice(0,10);
    if(!el('h1ReviewedAt').value.trim())el('h1ReviewedAt').value=localDateTimeValue();
    if(!el('h1ReviewedBy').value.trim()&&reviewer)el('h1ReviewedBy').value=reviewer;
    if(!el('h1Url').value.trim()&&targets.length===1)el('h1Url').value=targets[0];

    el('h1SafeHarbor').checked=false;
    el('h1Automation').checked=false;
    setQuickState('1re revue requise','warn');
    el('h1QuickSummary').textContent='Première revue pour ce fingerprint : choisis la cible, indique le débit réellement autorisé et confirme Safe Harbor + automatisation après lecture des règles.';
    if(el('h1AdvancedSettings'))el('h1AdvancedSettings').open=true;
    return false;
  }

  function rememberQuickProfile(payload){
    if(!el('h1QuickRemember')?.checked||!remoteBinding)return;
    const key=quickProfileKey();
    if(!key)return;
    const policy=payload?.policy||{};
    const profiles=quickProfiles();
    profiles[key]={
      authorization_reference:String(policy.authorization_reference||''),
      policy_version:String(policy.policy_version||''),
      reviewed_at:String(policy.reviewed_at||new Date().toISOString()),
      reviewed_by:String(policy.reviewed_by||''),
      max_requests_per_second:Number(policy.max_requests_per_second)||0,
      safe_harbor_confirmed:Boolean(policy.safe_harbor_confirmed),
      automated_scanning:Boolean(policy.automated_scanning),
      test_account_required:Boolean(policy.test_account_required),
      test_account_constraints:String(policy.test_account_constraints||''),
      additional_restrictions:Array.isArray(policy.additional_restrictions)?policy.additional_restrictions:[],
      program_notes:String(policy.program_notes||''),
      primary_url:String(payload?.target?.primary_url||''),
      saved_at:new Date().toISOString()
    };
    saveQuickProfiles(profiles);
    if(policy.reviewed_by){
      try{localStorage.setItem(QUICK_REVIEWER_STORAGE_KEY,String(policy.reviewed_by));}catch(_error){}
    }
    setQuickState('profil mémorisé','ok');
  }

  function serverProgramHasSavedProfile(handle){
    const prefix=String(handle||'')+'@';
    return Object.keys(serverReviewProfiles).some(key=>key.startsWith(prefix));
  }

  function localProgramHasSavedProfile(handle){
    const prefix=String(handle||'')+'@';
    return Object.keys(quickProfiles()).some(key=>key.startsWith(prefix));
  }

  function batchProgramHasSavedProfile(handle){
    return (
      serverProgramHasSavedProfile(handle) ||
      localProgramHasSavedProfile(handle)
    );
  }

  function batchCatalogPrograms(){
    const query=String(el('h1BatchSearch')?.value||'').trim().toLowerCase();
    const bountyOnly=Boolean(el('h1BatchBountyOnly')?.checked);
    const readiness=String(el('h1BatchReadiness')?.value||'all');
    const sort=String(el('h1BatchSort')?.value||'efficiency');
    const programs=hackerOnePrograms.filter(program=>{
      if(bountyOnly&&program?.offers_bounties!==true)return false;
      if(readiness!=='all'&&String(program?.status||'REVIEW')!==readiness)return false;
      const haystack=(String(program?.name||'')+' '+String(program?.handle||'')).toLowerCase();
      return !query||haystack.includes(query);
    });
    programs.sort((left,right)=>{
      if(sort==='name'){
        return String(left?.name||left?.handle||'').localeCompare(
          String(right?.name||right?.handle||''),undefined,{sensitivity:'base'}
        );
      }
      if(sort==='historical_value'){
        return Number(right?.historical_value_score||0)-Number(left?.historical_value_score||0);
      }
      if(sort==='efficiency'){
        return Number(right?.value_efficiency_score||0)-Number(left?.value_efficiency_score||0)
          || Number(right?.opportunity_score||0)-Number(left?.opportunity_score||0)
          || String(left?.name||left?.handle||'').localeCompare(String(right?.name||right?.handle||''));
      }
      if(sort==='opportunity'){
        return Number(right?.opportunity_score||0)-Number(left?.opportunity_score||0)
          || Number(right?.priority_score||0)-Number(left?.priority_score||0)
          || String(left?.name||left?.handle||'').localeCompare(String(right?.name||right?.handle||''));
      }
      const order={READY:0,REVIEW:1,BLOCKED:2};
      return (
        (order[String(left?.status||'REVIEW')]??3)-(order[String(right?.status||'REVIEW')]??3)
        || Number(right?.priority_score||0)-Number(left?.priority_score||0)
        || String(left?.name||left?.handle||'').localeCompare(String(right?.name||right?.handle||''))
      );
    });
    return programs;
  }

  function renderBatchCatalog(){
    const catalog=el('h1BatchCatalog');
    if(!catalog)return;
    catalog.replaceChildren();
    const programs=batchCatalogPrograms();
    if(!programs.length){
      catalog.textContent='Aucun programme ne correspond au filtre.';
    }else{
      for(const program of programs){
        const row=document.createElement('label');
        row.className='h1-batch-program';
        const checkbox=document.createElement('input');
        checkbox.type='checkbox';
        const readiness=String(program.status||'REVIEW');
        checkbox.disabled=readiness!=='READY';
        checkbox.checked=readiness==='READY'&&batchSelectedHandles.has(String(program.handle||''));
        checkbox.addEventListener('change',()=>{
          const handle=String(program.handle||'');
          if(checkbox.checked)batchSelectedHandles.add(handle);
          else batchSelectedHandles.delete(handle);
          renderBatchSelectionState();
        });
        const info=document.createElement('div');
        const titleRow=document.createElement('div');
        titleRow.className='h1-batch-title-row';
        const title=document.createElement('strong');
        title.textContent=String(program.name||program.handle||'Programme');
        titleRow.appendChild(title);
        const readinessBadge=document.createElement('span');
        readinessBadge.className='pill '+(readiness==='READY'?'ok':readiness==='BLOCKED'?'err':'warn');
        readinessBadge.textContent=readiness;
        titleRow.appendChild(readinessBadge);
        const changes=hackerOneCatalogMeta?.changes||{};
        const handle=String(program.handle||'');
        if(Array.isArray(changes.added)&&changes.added.includes(handle)){
          const badge=document.createElement('span');
          badge.className='pill ok h1-catalog-change';
          badge.textContent='nouveau';
          titleRow.appendChild(badge);
        }else if(Array.isArray(changes.changed)&&changes.changed.includes(handle)){
          const badge=document.createElement('span');
          badge.className='pill warn h1-catalog-change';
          badge.textContent='modifié';
          titleRow.appendChild(badge);
        }
        const meta=document.createElement('div');
        meta.className='muted compact';
        const parts=[
          String(program.handle||''),
          'rendement '+String(program.value_efficiency_score??0)+'/100',
          'opportunité '+String(program.opportunity_score??0)+'/100',
          'effort x'+String(program.effort_factor??'—'),
          Number(program.local_confirmed_findings||0)>0
            ?'local '+String(program.local_confirmed_findings)+' confirmé(s)'
            :null,
          Number(program.local_cost_efficiency_score||0)>0
            ?'coût local '+String(program.local_cost_efficiency_score)+'/10'
            :null,
          Number(program.local_average_duration_hours||0)>0
            ?'durée moy. '+String(program.local_average_duration_hours)+' h'
            :null,
          'priorité '+String(program.priority_score??0)+'/100',
          program.offers_bounties===true?'bounty':'sans bounty',
          program.gold_standard_safe_harbor===true?'safe harbor':'safe harbor à vérifier',
          readiness==='READY'
            ?'profil exact vérifié'
            :(readiness==='REVIEW'
              ?'revue nécessaire'
              :'non lançable'),
          Number(program.historical_usd_awarded_max||0)>0
            ?'max public historique USD '+Number(program.historical_usd_awarded_max).toLocaleString()
            :null
        ].filter(Boolean);
        meta.textContent=parts.join(' · ');
        info.append(titleRow,meta);
        row.append(checkbox,info);
        catalog.appendChild(row);
      }
    }
    renderBatchSelectionState();
  }

  function renderBatchSelectionState(){
    const count=batchSelectedHandles.size;
    const state=el('h1BatchState');
    if(state){
      state.textContent=count+' sélectionné'+(count>1?'s':'');
      state.className='pill '+(count?'ok':'');
    }
    if(el('h1BatchLaunch'))el('h1BatchLaunch').disabled=count===0;
  }

  function applyDiscoveryResult(result){
    hackerOnePrograms=Array.isArray(result?.programs)?result.programs:[];
    const summary=result?.summary||{};
    if(el('h1DiscoveryReady'))el('h1DiscoveryReady').textContent=String(summary.ready||0);
    if(el('h1DiscoveryReview'))el('h1DiscoveryReview').textContent=String(summary.review||0);
    if(el('h1DiscoveryBlocked'))el('h1DiscoveryBlocked').textContent=String(summary.blocked||0);
    const readyHandles=new Set(
      hackerOnePrograms
        .filter(program=>String(program?.status||'')==='READY')
        .map(program=>String(program?.handle||''))
    );
    batchSelectedHandles=new Set(
      [...batchSelectedHandles].filter(handle=>readyHandles.has(handle))
    );
  }

  async function refreshBatchCatalog(){
    const button=el('h1BatchRefresh');
    if(button)button.disabled=true;
    try{
      const catalog=await api('/imports/hackerone/programs?refresh=true');
      hackerOneCatalogMeta=catalog?.catalog||{};
      const [discovery]=await Promise.all([
        api('/hackerone/discovery?verify_limit=50'),
        loadServerReviewProfiles()
      ]);
      applyDiscoveryResult(discovery);
      renderProgramOptions();
      renderBatchCatalog();
      const summary=discovery?.summary||{};
      el('h1BatchSummary').textContent=
        String(summary.total||0)+' programme(s) · '+
        String(summary.ready||0)+' READY · '+
        String(summary.review||0)+' REVIEW · '+
        String(summary.blocked||0)+' BLOCKED'+
        (discovery?.catalog_checked_at?' · vérifié '+new Date(discovery.catalog_checked_at).toLocaleString():'');
    }catch(error){
      el('h1BatchSummary').textContent='Catalogue indisponible : '+error.message;
    }finally{
      if(button)button.disabled=false;
    }
  }

  function selectReadyBatchProfiles(){
    batchSelectedHandles=new Set(
      batchCatalogPrograms()
        .filter(program=>String(program?.status||'')==='READY')
        .slice(0,20)
        .map(program=>String(program.handle||''))
    );
    renderBatchCatalog();
  }

  function autoSelectBatchProfiles(){
    const limit=Math.max(1,Math.min(20,Number(el('h1BatchAutoLimit')?.value||5)));
    const minScore=Math.max(0,Math.min(100,Number(el('h1BatchAutoMinScore')?.value||50)));
    const pool=hackerOnePrograms
      .filter(program=>String(program?.status||'')==='READY')
      .filter(program=>program?.offers_bounties===true)
      .filter(program=>Number(program?.value_efficiency_score||0)>=minScore)
      .map(program=>({...program}));
    const candidates=[];
    const focusCounts=new Map();
    while(pool.length&&candidates.length<limit){
      pool.sort((left,right)=>{
        const leftFocus=String(left?.research_focus?.[0]||'other');
        const rightFocus=String(right?.research_focus?.[0]||'other');
        const leftScore=Math.max(0,Number(left?.value_efficiency_score||0)-12*Number(focusCounts.get(leftFocus)||0));
        const rightScore=Math.max(0,Number(right?.value_efficiency_score||0)-12*Number(focusCounts.get(rightFocus)||0));
        return rightScore-leftScore
          || Number(right?.opportunity_score||0)-Number(left?.opportunity_score||0)
          || String(left?.name||left?.handle||'').localeCompare(String(right?.name||right?.handle||''));
      });
      const picked=pool.shift();
      candidates.push(picked);
      const focus=String(picked?.research_focus?.[0]||'other');
      focusCounts.set(focus,Number(focusCounts.get(focus)||0)+1);
    }
    if(limit>=4&&candidates.length){
      const selected=new Set(candidates.map(program=>String(program.handle||'')));
      const exploration=hackerOnePrograms
        .filter(program=>String(program?.status||'')==='READY')
        .filter(program=>program?.offers_bounties===true)
        .filter(program=>Number(program?.value_efficiency_score||0)>=minScore)
        .filter(program=>!selected.has(String(program?.handle||'')))
        .filter(program=>[
          ...(Array.isArray(program?.reasons)?program.reasons:[]),
          ...(Array.isArray(program?.opportunity_reasons)?program.opportunity_reasons:[])
        ].some(reason=>['new_program','catalog_changed','recent_catalog_change'].includes(String(reason))))
        .sort((left,right)=>
          Number(right?.opportunity_score||0)-Number(left?.opportunity_score||0)
          || Number(right?.value_efficiency_score||0)-Number(left?.value_efficiency_score||0)
          || String(left?.handle||'').localeCompare(String(right?.handle||''))
        )[0];
      if(exploration)candidates[candidates.length-1]=exploration;
    }
    batchSelectedHandles=new Set(candidates.map(program=>String(program.handle||'')));
    renderBatchCatalog();
    el('h1BatchSummary').textContent=candidates.length
      ?candidates.length+' programme(s) READY sélectionné(s) par rendement/effort avec diversification · validation serveur requise au lancement'
      :'Aucun programme READY ne correspond aux critères Auto-select.';
  }

  async function autoQueueBatch(){
    const button=el('h1BatchAutoQueue');
    if(button)button.disabled=true;
    try{
      saveQuickPrefs();
      autoSelectBatchProfiles();
      if(!batchSelectedHandles.size)return;
      await launchSelectedBatch();
    }finally{
      if(button)button.disabled=false;
    }
  }

  async function batchPayloadForHandle(handle){
    const snapshot=await api(
      '/imports/hackerone/programs/'+encodeURIComponent(handle)+'/snapshot'
    );
    const key=String(snapshot.handle||handle)+'@'+String(snapshot.snapshot_sha256||'');
    const profile=exactQuickProfile(key);
    if(!profile){
      const error=new Error(String(handle)+': première revue requise ou fingerprint modifié');
      error.code='review_required';
      throw error;
    }
    const primaryUrl=String(profile.primary_url||'').trim();
    if(!primaryUrl)throw new Error(String(handle)+': cible principale mémorisée absente');
    const policy={
      authorization_reference:String(profile.authorization_reference||''),
      policy_version:String(profile.policy_version||''),
      reviewed_at:String(profile.reviewed_at||profile.saved_at||''),
      reviewed_by:String(profile.reviewed_by||''),
      safe_harbor_confirmed:Boolean(profile.safe_harbor_confirmed),
      automated_scanning:Boolean(profile.automated_scanning),
      max_requests_per_second:Number(profile.max_requests_per_second),
      test_account_required:Boolean(profile.test_account_required),
      test_account_constraints:String(profile.test_account_constraints||''),
      additional_restrictions:Array.isArray(profile.additional_restrictions)
        ?profile.additional_restrictions:[],
      program_notes:String(profile.program_notes||'')
    };
    if(!policy.reviewed_at){
      throw new Error(String(handle)+': date de revue mémorisée absente');
    }
    const reviewedAt=new Date(policy.reviewed_at);
    if(Number.isNaN(reviewedAt.getTime())){
      throw new Error(String(handle)+': date de revue mémorisée invalide');
    }
    const blockers=conservativeBlockers(policy);
    if(blockers.length){
      throw new Error(String(handle)+': '+blockers.join(' · '));
    }
    return {
      document:snapshot.document,
      policy,
      target:{
        name:String(snapshot?.program?.name||snapshot.handle||handle).slice(0,120),
        primary_url:primaryUrl
      },
      remote_handle:String(snapshot.handle||handle),
      remote_snapshot_sha256:String(snapshot.snapshot_sha256||'')
    };
  }

  function hackerOneBatchMemberReason(reason){
    const value=String(reason||'');
    const labels={
      remote_snapshot_binding_missing:'binding HackerOne incomplet · revue requise',
      remote_revalidation_unavailable:'HackerOne temporairement indisponible · nouvelle tentative automatique',
      remote_revalidation_retry_exhausted:'revalidation HackerOne impossible après plusieurs tentatives · revue requise',
      remote_hackerone_authorization_failed:'accès API HackerOne refusé · vérifier les credentials avant reprise',
      remote_program_unavailable:'programme HackerOne devenu inaccessible · revue requise',
      remote_snapshot_changed_since_batch_admission:'scope/policy modifié depuis la mise en file · revue requise',
      remote_submissions_no_longer_open:'soumissions HackerOne désormais pausées/fermées · revue requise',
      remote_program_no_longer_open:'programme HackerOne désormais fermé · revue requise'
    };
    return labels[value]||value;
  }

  function renderBatchProgress(batch){
    const members=Array.isArray(batch?.members)?batch.members:[];
    const progress=el('h1BatchProgress');
    if(!progress)return;
    progress.replaceChildren();
    if(!members.length){
      progress.textContent='—';
      return;
    }
    for(const member of members){
      const row=document.createElement('div');
      row.className='scope-asset-row';
      const info=document.createElement('div');
      const title=document.createElement('strong');
      title.textContent=String(member.handle||member.campaign_id||'Programme');
      const detail=document.createElement('div');
      detail.className='muted compact';
      const retryAt=String(member.remote_revalidation_retry_at||'');
      let retryLabel='';
      if(retryAt){
        const retryDate=new Date(retryAt);
        if(!Number.isNaN(retryDate.getTime())){
          retryLabel=' · prochain essai '+retryDate.toLocaleTimeString();
        }
      }
      detail.textContent='campagne '+String(member.campaign_id||'—')+
        (member.reason?' · '+hackerOneBatchMemberReason(member.reason):'')+
        retryLabel;
      info.append(title,detail);
      const badge=document.createElement('span');
      const status=String(member.status||'ready');
      badge.className='pill '+(
        ['done','running'].includes(status)?'ok':
        ['blocked','cancelled'].includes(status)?'err':'warn'
      );
      badge.textContent=status;
      row.append(info,badge);
      progress.appendChild(row);
    }
  }

  function renderBatchStatus(batch){
    if(!batch)return;
    activeBatchId=String(batch.id||activeBatchId||'');
    const summary=batch.summary||{};
    const total=Array.isArray(batch.members)?batch.members.length:0;
    el('h1BatchSummary').textContent=
      'Lot '+String(batch.mode||'—')+' · état '+String(batch.state||'—')+
      ' · '+String(summary.done||0)+' terminé(s) · '+
      String(summary.review||0)+' à revoir · '+
      String(summary.blocked||0)+' bloqué(s) · total '+total+'.';
    renderBatchProgress(batch);
    const cancel=el('h1BatchCancel');
    const terminal=['completed','cancelled'].includes(String(batch.state||''));
    if(cancel){
      cancel.classList.toggle('hidden',terminal||!activeBatchId);
      cancel.disabled=terminal||!activeBatchId;
    }
    if(terminal){
      if(batchTimer!==null){
        clearInterval(batchTimer);
        batchTimer=null;
      }
      activeBatchId='';
      try{localStorage.removeItem(H1_ACTIVE_BATCH_STORAGE_KEY);}catch(_error){}
    }
  }

  async function refreshActiveBatch(){
    if(!activeBatchId)return;
    try{
      const batch=await api(
        '/imports/hackerone/batches/'+encodeURIComponent(activeBatchId)
      );
      renderBatchStatus(batch);
    }catch(error){
      el('h1BatchSummary').textContent='Suivi du lot indisponible : '+error.message;
    }
  }

  function startBatchMonitor(batchId){
    activeBatchId=String(batchId||'');
    if(!activeBatchId)return;
    try{localStorage.setItem(H1_ACTIVE_BATCH_STORAGE_KEY,activeBatchId);}catch(_error){}
    if(batchTimer!==null)clearInterval(batchTimer);
    void refreshActiveBatch();
    batchTimer=setInterval(()=>void refreshActiveBatch(),10000);
  }

  function latestActiveBatch(batches){
    const source=Array.isArray(batches)?batches:[];
    const active=source
      .filter(batch=>!['completed','cancelled'].includes(String(batch?.state||'')))
      .sort((left,right)=>
        String(right?.updated_at||right?.created_at||'')
          .localeCompare(String(left?.updated_at||left?.created_at||''))
      );
    return active[0]||null;
  }

  function latestBatchNeedingReview(batches){
    const source=Array.isArray(batches)?batches:[];
    return source
      .filter(batch=>String(batch?.state||'')==='completed')
      .filter(batch=>
        Number(batch?.summary?.review||0)>0||
        Number(batch?.summary?.blocked||0)>0
      )
      .sort((left,right)=>
        String(right?.updated_at||right?.created_at||'')
          .localeCompare(String(left?.updated_at||left?.created_at||''))
      )[0]||null;
  }

  async function restoreActiveBatch(){
    if(activeBatchId)return;
    let localId='';
    try{localId=String(localStorage.getItem(H1_ACTIVE_BATCH_STORAGE_KEY)||'');}
    catch(_error){localId='';}

    if(localId){
      try{
        const batch=await api('/imports/hackerone/batches/'+encodeURIComponent(localId));
        if(!['completed','cancelled'].includes(String(batch?.state||''))){
          startBatchMonitor(batch.id);
          return;
        }
      }catch(_error){}
      try{localStorage.removeItem(H1_ACTIVE_BATCH_STORAGE_KEY);}catch(_error){}
    }

    try{
      const result=await api('/imports/hackerone/batches?limit=20');
      const batch=latestActiveBatch(result?.batches);
      if(batch?.id){
        startBatchMonitor(batch.id);
        setLauncherStatus('Lot HackerOne actif retrouvé côté serveur et repris automatiquement.','ok');
        return;
      }
      const reviewBatch=latestBatchNeedingReview(result?.batches);
      if(reviewBatch?.id){
        renderBatchStatus(reviewBatch);
        setLauncherStatus(
          'Dernier lot terminé avec des programmes à revoir/bloqués. Les détails restent affichés.',
          'warn'
        );
      }
    }catch(_error){}
  }

  function hackerOneLaunchErrorMessage(error){
    const detail=error?.detail&&typeof error.detail==='object'?error.detail:null;
    const reason=String(detail?.reason||'');
    if(reason==='hackerone_live_scan_not_ready'){
      const failed=Array.isArray(detail?.failed_checks)?detail.failed_checks:[];
      const scanner=Array.isArray(detail?.scanner_block_reasons)?detail.scanner_block_reasons:[];
      const causes=[...failed,...scanner].filter(Boolean);
      return 'Pré-vol scanner non prêt'+(causes.length?' : '+causes.join(' · '):'.');
    }
    if(reason==='hackerone_submissions_not_open'||reason==='hackerone_program_not_open'){
      const handle=String(detail?.handle||'programme');
      return handle+' n’est plus ouvert au lancement. Recharge le catalogue et la revue avant de continuer.';
    }
    if(reason==='stale_hackerone_snapshot'||reason==='hackerone_snapshot_document_mismatch'){
      return 'Le programme HackerOne a changé depuis la revue. Recharge-le puis confirme le nouveau fingerprint.';
    }
    if(reason==='review_profile_required'){
      const handles=Array.isArray(detail?.handles)?detail.handles.filter(Boolean):[];
      return 'Première revue requise'+(handles.length?' : '+handles.join(', '):'.');
    }
    if(['review_profile_invalid','review_profile_incomplete','review_profile_binding_mismatch'].includes(reason)){
      const handles=Array.isArray(detail?.handles)?detail.handles.filter(Boolean):[];
      return 'Profil de revue à actualiser'+(handles.length?' : '+handles.join(', '):'.');
    }
    return String(error?.message||'Lancement HackerOne impossible.');
  }

  async function launchSelectedBatch(){
    const button=el('h1BatchLaunch');
    const handles=[...batchSelectedHandles].slice(0,20);
    if(!handles.length)return;
    button.disabled=true;
    try{
      el('h1BatchSummary').textContent='Pré-vol scanner et runtime…';
      const readiness=await refreshHackerOneLiveReadiness();
      if(!readiness||readiness.live_scan_ready!==true){
        const failed=Array.isArray(readiness?.checks)
          ?readiness.checks
            .filter(item=>item?.required===true&&item?.ok!==true)
            .map(item=>String(item?.id||''))
            .filter(Boolean)
          :[];
        const error=new Error('Pré-vol scanner non prêt.');
        error.detail={
          reason:'hackerone_live_scan_not_ready',
          failed_checks:failed,
          scanner_block_reasons:Array.isArray(readiness?.scanner_block_reasons)
            ?readiness.scanner_block_reasons:[]
        };
        throw error;
      }
      el('h1BatchSummary').textContent=
        'Vérification serveur des fingerprints, profils et état courant des programmes…';
      const batch=await api('/imports/hackerone/batches/launch-reviewed',{
        method:'POST',
        body:JSON.stringify({
          mode:String(el('h1BatchMode').value||'sequential'),
          handles
        })
      });
      renderBatchStatus(batch);
      startBatchMonitor(batch.id);
      setLauncherStatus(
        'Lot HackerOne vérifié et enregistré côté serveur. Il continue même si le dashboard est fermé.',
        'ok'
      );
    }catch(error){
      const message=hackerOneLaunchErrorMessage(error);
      el('h1BatchSummary').textContent=message;
      setLauncherStatus(message,'err');
    }finally{
      button.disabled=batchSelectedHandles.size===0;
    }
  }

  async function cancelActiveBatch(){
    if(!activeBatchId)return;
    const button=el('h1BatchCancel');
    if(button)button.disabled=true;
    try{
      const batch=await api(
        '/imports/hackerone/batches/'+encodeURIComponent(activeBatchId)+'/cancel',
        {method:'POST',body:'{}'}
      );
      renderBatchStatus(batch);
      setLauncherStatus('Lot HackerOne annulé.','ok');
    }catch(error){
      el('h1BatchSummary').textContent='Annulation impossible : '+error.message;
    }finally{
      if(button&&!button.classList.contains('hidden'))button.disabled=false;
    }
  }

  function clearRemoteBinding(){
    remoteBinding=null;
    setQuickState('programme requis');
    if(el('h1AdvancedSettings'))el('h1AdvancedSettings').open=true;
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
      const [snapshot,reviewDraft]=await Promise.all([
        api('/imports/hackerone/programs/'+encodeURIComponent(handle)+'/snapshot'),
        api('/imports/hackerone/programs/'+encodeURIComponent(handle)+'/review-draft')
      ]);
      remoteBinding={
        handle:String(snapshot.handle),
        snapshot_sha256:String(snapshot.snapshot_sha256)
      };
      const prefill=reviewDraft?.prefill||{};
      el('h1ScopeJson').value=JSON.stringify(prefill.scope_document||snapshot.document,null,2);
      if(prefill.name||snapshot.program?.name){
        el('h1Name').value=String(prefill.name||snapshot.program.name).slice(0,120);
      }
      if(prefill.primary_url)el('h1Url').value=String(prefill.primary_url);
      if(prefill.authorization_reference)el('h1Auth').value=String(prefill.authorization_reference);
      if(prefill.policy_version)el('h1PolicyVersion').value=String(prefill.policy_version);
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
      const reused=restoreQuickProfile(snapshot);
      rememberLastProgram(remoteBinding.handle);
      invalidatePreview();
      const manual=Array.isArray(reviewDraft?.manual_required)?reviewDraft.manual_required.length:0;
      setLauncherStatus(
        'Programme HackerOne chargé. Scope, référence, version et cible déductible préremplis · '+
        String(manual)+' élément(s) de policy restent à confirmer manuellement.',
        'ok'
      );
      if(reused&&el('h1QuickAutoPreview')?.checked){
        await preview();
        if(approvedPreview){
          setQuickState('prêt à confirmer','ok');
          el('h1QuickSummary').textContent='Programme inchangé et prévisualisation admise. Confirme la prévisualisation puis lance le bug bounty.';
          el('h1PreviewCard')?.scrollIntoView({behavior:'smooth',block:'center'});
        }
      }
    }catch(error){
      clearRemoteBinding();
      setLauncherStatus(error.message,'err');
    }finally{
      el('h1LoadProgram').disabled=!el('h1ProgramSelect').value;
    }
  }

  function renderHackerOneLiveReadiness(payload){
    const state=el('h1LiveReadinessState');
    const checks=el('h1LiveReadinessChecks');
    checks.replaceChildren();

    const liveReady=payload?.live_scan_ready===true;
    const reviewReady=payload?.program_review_ready===true;
    state.textContent=liveReady?'PRÊT SCAN RÉEL':reviewReady?'PRÊT POUR REVUE':'BLOQUÉ';
    state.className='pill '+(liveReady?'ok':reviewReady?'warn':'err');

    el('h1InterfaceUrl').textContent='Interface : '+String(window.location.origin||'—');
    el('h1LiveReadinessSummary').textContent=liveReady
      ?'Tous les verrous obligatoires du scanner réel sont ouverts. La policy du programme reste à vérifier avant chaque campagne.'
      :reviewReady
        ?'Connexion et dépendances prêtes. Les verrous de scan réel restent volontairement fermés.'
        :'La connexion HackerOne ou une dépendance obligatoire doit être corrigée.';

    const records=Array.isArray(payload?.checks)?payload.checks:[];
    if(!records.length){
      checks.textContent='Aucun diagnostic disponible.';
    }else{
      for(const check of records){
        const row=document.createElement('div');
        row.className='scope-asset-row';
        const info=document.createElement('div');
        const title=document.createElement('strong');
        title.textContent=(check?.ok===true?'✓ ':'✗ ')+String(check?.label||check?.id||'Check');
        const detail=document.createElement('div');
        detail.className='muted compact';
        detail.textContent=check?.ok===true
          ?(check?.required===true?'obligatoire · OK':'optionnel · OK')
          :String(check?.action||'Configuration requise.');
        info.append(title,detail);
        const badge=document.createElement('span');
        badge.className='pill '+(check?.ok===true?'ok':check?.required===true?'err':'warn');
        badge.textContent=check?.ok===true?'OK':check?.required===true?'REQUIS':'OPTIONNEL';
        row.append(info,badge);
        checks.appendChild(row);
      }
    }

    const operatorSteps=el('h1LiveOperatorSteps');
    operatorSteps.replaceChildren();
    const steps=Array.isArray(payload?.operator_steps)?payload.operator_steps:[];
    if(!steps.length){
      operatorSteps.textContent='Aucune étape opérateur disponible.';
    }else{
      for(const step of steps){
        const row=document.createElement('div');
        row.className='scope-asset-row';
        const info=document.createElement('div');
        const title=document.createElement('strong');
        title.textContent=(step?.done===true?'✓ ':'• ')+String(step?.title||step?.id||'Étape');
        const detail=document.createElement('div');
        detail.className='muted compact';
        detail.textContent=String(step?.instruction||'');
        info.append(title,detail);
        const badge=document.createElement('span');
        badge.className='pill '+(step?.done===true?'ok':'warn');
        badge.textContent=step?.done===true?'FAIT':String(step?.when||'À FAIRE').toUpperCase();
        row.append(info,badge);
        operatorSteps.appendChild(row);
      }
    }

    const activation=Array.isArray(payload?.activation_template)
      ?payload.activation_template.filter(Boolean).join('\n'):'';
    const activationTemplate=el('h1LiveActivationTemplate');
    activationTemplate.textContent=activation;
    el('h1LiveCopyActivation').disabled=!activation;
    el('h1LiveCopyActivation').dataset.activation=activation;
    const scannerCommand=String(payload?.scanner_start_command||'');
    el('h1LiveScannerCommand').textContent=scannerCommand
      ?'Commande scanner : '+scannerCommand:'';

    const reasons=Array.isArray(payload?.scanner_block_reasons)
      ?payload.scanner_block_reasons.filter(Boolean):[];
    el('h1LiveReadinessNext').textContent=
      String(payload?.next_operator_step||'')+
      (reasons.length?' · Scanner bloque : '+reasons.join(', '):'');
  }

  async function refreshHackerOneLiveReadiness(){
    const button=el('h1LiveReadinessRefresh');
    if(button)button.disabled=true;
    try{
      const payload=await api('/hackerone/live-readiness');
      renderHackerOneLiveReadiness(payload);
      return payload;
    }catch(error){
      const state=el('h1LiveReadinessState');
      state.textContent='INDISPONIBLE';
      state.className='pill err';
      el('h1InterfaceUrl').textContent='Interface : '+String(window.location.origin||'—');
      el('h1LiveReadinessSummary').textContent='Pré-vol indisponible : '+error.message;
      el('h1LiveReadinessChecks').textContent='—';
      el('h1LiveOperatorSteps').textContent='—';
      el('h1LiveActivationTemplate').textContent='';
      el('h1LiveCopyActivation').disabled=true;
      el('h1LiveCopyActivation').dataset.activation='';
      el('h1LiveScannerCommand').textContent='';
      el('h1LiveReadinessNext').textContent='';
      return null;
    }finally{
      if(button)button.disabled=false;
    }
  }

  async function copyHackerOneLiveActivation(){
    const button=el('h1LiveCopyActivation');
    const value=String(button?.dataset?.activation||'');
    if(!value)return;
    try{
      await navigator.clipboard.writeText(value);
      button.textContent='Configuration copiée';
      setTimeout(()=>{button.textContent='Copier la configuration';},1200);
    }catch(_error){
      button.textContent='Copie impossible';
      setTimeout(()=>{button.textContent='Copier la configuration';},1200);
    }
  }

  async function initRemoteControlCenter(){
    void refreshHackerOneLiveReadiness();
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
      const [result,discovery]=await Promise.all([
        api('/imports/hackerone/programs'),
        api('/hackerone/discovery?verify_limit=50'),
        loadServerReviewProfiles()
      ]);
      hackerOneCatalogMeta=result?.catalog||{};
      applyDiscoveryResult(discovery);
      const prefs=applyQuickPrefs();
      renderProgramOptions();
      renderBatchCatalog();
      void restoreActiveBatch();
      const lastHandle=lastProgramHandle();
      if(
        prefs.auto_resume
        && lastHandle
        && !remoteBinding
        && hackerOnePrograms.some(program=>String(program?.handle||'')===lastHandle)
      ){
        el('h1ProgramSelect').value=lastHandle;
        el('h1LoadProgram').disabled=false;
        setQuickState('reprise automatique','ok');
        await loadRemoteProgram();
      }
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
      rememberQuickProfile(payload);
      if(preview?.review_profile_persisted){
        void loadServerReviewProfiles().then(()=>renderBatchCatalog());
      }
      setLauncherStatus('Scope et policy vérifiés. Profil mémorisé pour ce fingerprint; confirme puis lance.','ok');
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
      const previewPayload={
        document:payload.document,
        policy:payload.policy,
        remember_review_profile:Boolean(el('h1QuickRemember')?.checked),
        preferred_primary_url:payload.target.primary_url
      };
      if(payload.remote_handle){
        previewPayload.remote_handle=payload.remote_handle;
        previewPayload.remote_snapshot_sha256=payload.remote_snapshot_sha256;
      }else{
        previewPayload.remember_review_profile=false;
        delete previewPayload.preferred_primary_url;
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
      if(el('h1AdvancedSettings'))el('h1AdvancedSettings').open=true;
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
  el('h1LiveReadinessRefresh').addEventListener('click',()=>void refreshHackerOneLiveReadiness());
  el('h1LiveCopyActivation').addEventListener('click',()=>void copyHackerOneLiveActivation());
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
  el('h1NeedsInfoCopy').addEventListener('click',()=>void copyHackerOneNeedsInfoDraft());
  el('h1AttentionRefresh').addEventListener('click',()=>void refreshHackerOneAttention());
  el('h1AttentionMarkAll').addEventListener('click',()=>markAllHackerOneAttentionSeen());
  el('h1AttentionMarkVisible').addEventListener('click',()=>markVisibleHackerOneAttentionSeen());
  el('h1AttentionOpenNextAction').addEventListener('click',()=>void openNextHackerOneActionRequired());
  el('h1AttentionExportJson').addEventListener('click',()=>exportHackerOneAttentionJson());
  el('h1AttentionExportCsv').addEventListener('click',()=>exportHackerOneAttentionCsv());
  el('h1AttentionResetFilters').addEventListener('click',()=>resetHackerOneAttentionFilters());
  el('h1AttentionSaveCustomView').addEventListener('click',()=>saveCurrentHackerOneAttentionCustomView());
  el('h1AttentionDeleteCustomView').addEventListener('click',()=>deleteSelectedHackerOneAttentionCustomView());
  el('h1AttentionCustomView').addEventListener('change',()=>applySelectedHackerOneAttentionCustomView());
  for(const button of document.querySelectorAll('[data-h1-attention-view]')){
    button.addEventListener('click',()=>applyHackerOneAttentionSavedView(button.dataset.h1AttentionView));
  }
  el('h1AttentionSearch').addEventListener('input',()=>{
    saveHackerOneAttentionFilters();
    renderHackerOneAttentionViewState();
    if(latestAttentionPayload)renderHackerOneAttention(latestAttentionPayload);
  });
  for(const id of [
    'h1AttentionReadFilter',
    'h1AttentionBucketFilter',
    'h1AttentionProgramFilter',
    'h1AttentionStateFilter',
    'h1AttentionBountyFilter',
    'h1AttentionRecentFilter',
    'h1AttentionSort'
  ]){
    el(id).addEventListener('change',()=>{
      saveHackerOneAttentionFilters();
      renderHackerOneAttentionViewState();
      if(latestAttentionPayload)renderHackerOneAttention(latestAttentionPayload);
    });
  }
  el('h1BatchSearch').addEventListener('input',renderBatchCatalog);
  el('h1BatchBountyOnly').addEventListener('change',renderBatchCatalog);
  el('h1BatchReadiness').addEventListener('change',renderBatchCatalog);
  el('h1BatchSort').addEventListener('change',renderBatchCatalog);
  el('h1BatchRefresh').addEventListener('click',()=>void refreshBatchCatalog());
  el('h1BatchSelectReady').addEventListener('click',selectReadyBatchProfiles);
  el('h1BatchAutoSelect').addEventListener('click',()=>{saveQuickPrefs();autoSelectBatchProfiles();});
  el('h1BatchAutoQueue').addEventListener('click',()=>void autoQueueBatch());
  el('h1BatchAutoLimit').addEventListener('change',saveQuickPrefs);
  el('h1BatchAutoMinScore').addEventListener('change',saveQuickPrefs);
  el('h1BatchMode').addEventListener('change',saveQuickPrefs);
  el('h1BatchLaunch').addEventListener('click',()=>void launchSelectedBatch());
  el('h1BatchCancel').addEventListener('click',()=>void cancelActiveBatch());
  el('h1QuickAutoResume').addEventListener('change',saveQuickPrefs);
  el('h1QuickAutoPreview').addEventListener('change',saveQuickPrefs);
  applyQuickPrefs();
  el('token').addEventListener('change',initRemoteControlCenter);
  initRemoteControlCenter();
  startHackerOneAttentionMonitor();
})();
