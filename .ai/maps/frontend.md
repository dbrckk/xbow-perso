This file is a merged representation of a subset of the codebase, containing specifically included files and files not matching ignore patterns, combined into a single document by Repomix.
The content has been processed where content has been compressed (code blocks are separated by ⋮---- delimiter).

# File Summary

## Purpose
This file contains a packed representation of a subset of the repository's contents that is considered the most important context.
It is designed to be easily consumable by AI systems for analysis, code review,
or other automated processes.

## File Format
The content is organized as follows:
1. This summary section
2. Repository information
3. Directory structure
4. Repository files (if enabled)
5. Multiple file entries, each consisting of:
  a. A header with the file path (## File: path/to/file)
  b. The full contents of the file in a code block

## Usage Guidelines
- This file should be treated as read-only. Any changes should be made to the
  original repository files, not this packed version.
- When processing this file, use the file path to distinguish
  between different files in the repository.
- Be aware that this file may contain sensitive information. Handle it with
  the same level of security as you would the original repository.

## Notes
- Some files may have been excluded based on .gitignore rules and Repomix's configuration
- Binary files are not included in this packed representation. Please refer to the Repository Structure section for a complete list of file paths, including binary files
- Only files matching these patterns are included: **/*.{py,js,mjs,cjs,ts,tsx,jsx,java,kt,kts,gd,groovy,gradle,toml,json,yaml,yml,sql,sh}
- Files matching these patterns are excluded: .ai/**, **/node_modules/**, **/.gradle/**, **/build/**, **/dist/**, **/.venv/**, **/__pycache__/**, **/.pytest_cache/**, **/.git/**, **/coverage/**, **/*.lock, **/*.min.js, **/*.map, assets/**, art/**, art_sources/**, marketing/**, colab/**, kaggle/**, discovery-cache.json, health-snapshot.json, history.json
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Content has been compressed - code blocks are separated by ⋮---- delimiter
- Files are sorted by Git change count (files with more changes are at the bottom)

# Directory Structure
```
app.js
hackerone.js
sw.js
```

# Files

## File: app.js
```javascript
const $=id
const lines=id
const clamp=(v,min,max)
const fmtSeconds=value=>{
  const seconds=Math.max(0,Number(value)||0);
⋮----
async function api(path,opts=
⋮----
function setStatus(message,type='muted')
⋮----
function budgetRow(label,used,limit)
⋮----
function renderControl(data)
⋮----
function readinessClass(value)
⋮----
function visibleFindings(data)
⋮----
function renderClusters(data)
⋮----
function renderReviewAndSubmission(reviewQueue, reportReadiness)
⋮----
function renderDecisionTimeline(data)
⋮----
function renderFindingIntelligence(data)
⋮----
function renderTargetMemory(data,diff,temporal,confidence)
⋮----
const renderDeltaList=(id,items,empty)=>
⋮----
async function refreshDashboard()
⋮----
async function activateCampaign(value)
⋮----
$('load').onclick=async()=>
⋮----
$('refresh').onclick=async()=>
⋮----
$('create').onclick=async()=>
⋮----
$('start').onclick=async()=>
⋮----
$('resetBreaker').onclick=async()=>
```

## File: hackerone.js
```javascript
const el=id
const splitLines=value
⋮----
function setLauncherStatus(message,type='muted')
⋮----
function setConnectionState(label,type='')
⋮----
function hackerOneAttentionLabel(item)
⋮----
function hackerOneNotificationLabel(item)
⋮----
function attentionSeenKey(item)
⋮----
function loadAttentionSeen()
⋮----
function saveAttentionSeen(state)
⋮----
function ensureAttentionBaseline(items)
⋮----
function isAttentionUnread(item,state)
⋮----
function markHackerOneAttentionSeen(item)
⋮----
function markAllHackerOneAttentionSeen()
⋮----
async function focusHackerOneAttentionCampaign(item)
⋮----
function attentionText(value)
⋮----
function updateAttentionSelectOptions(id,values,allLabel)
⋮----
function syncHackerOneAttentionFilterOptions(items)
⋮----
function currentHackerOneAttentionFilters()
⋮----
function loadHackerOneAttentionFilters()
⋮----
function saveHackerOneAttentionFilters()
⋮----
function setSelectValueIfAvailable(id,value,fallback='all')
⋮----
function applyHackerOneAttentionFilters(state,
⋮----
function restoreHackerOneAttentionFilters()
⋮----
function sameAttentionFilters(left,right)
⋮----
function renderHackerOneAttentionViewState()
⋮----
function applyHackerOneAttentionSavedView(name)
⋮----
function normalizeAttentionCustomViewName(value)
⋮----
function sanitizeAttentionCustomViewFilters(value)
⋮----
function loadHackerOneAttentionCustomViews()
⋮----
function saveHackerOneAttentionCustomViews(state)
⋮----
function loadHackerOneAttentionCustomViewsFromValue(state)
⋮----
function renderHackerOneAttentionCustomViews()
⋮----
function selectedHackerOneAttentionCustomView()
⋮----
function saveCurrentHackerOneAttentionCustomView()
⋮----
function applySelectedHackerOneAttentionCustomView()
⋮----
function deleteSelectedHackerOneAttentionCustomView()
⋮----
function hackerOneAttentionMatchesRecent(item,filterValue)
⋮----
function filterAndSortHackerOneAttention(items,seen)
⋮----
const compareDate=(left,right)=>
⋮----
function visibleHackerOneAttentionItems()
⋮----
function markVisibleHackerOneAttentionSeen()
⋮----
function attentionExportRows()
⋮----
function downloadAttentionExport(filename,mimeType,content)
⋮----
function exportHackerOneAttentionJson()
⋮----
function csvCell(value)
⋮----
function exportHackerOneAttentionCsv()
⋮----
async function openNextHackerOneActionRequired()
⋮----
function resetHackerOneAttentionFilters()
⋮----
function renderHackerOneAttention(payload)
⋮----
async function refreshHackerOneAttention()
⋮----
function startHackerOneAttentionMonitor()
⋮----
function stopRunMonitor()
⋮----
function reviewField(labelText,control,name)
⋮----
function reviewValue(editor,name)
⋮----
async function saveFindingReviewMetadata(findingId,editor)
⋮----
async function resolveHackerOneFinding(findingId,confirmed,editor)
⋮----
function buildFindingReviewEditor(finding,readiness)
⋮----
function renderHackerOneFindings(campaignData,artifacts,reportReadiness,reportApproval)
⋮----
async function downloadHackerOneReport()
⋮----
function hackerOneReportReviewer()
⋮----
async function approveHackerOneReport()
⋮----
async function submitHackerOneReport()
⋮----
async function revokeHackerOneReportApproval()
⋮----
async function queueHackerOneReport()
⋮----
function hackerOneActivityLabel(event)
⋮----
function renderHackerOneReportTimeline(campaignData,artifactId)
⋮----
function renderHackerOneRemoteReportStatus(remoteStatus)
⋮----
function renderHackerOneNeedsInfo(remoteStatus,needsInfoDraft)
⋮----
async function copyHackerOneNeedsInfoDraft()
⋮----
function renderRunMonitor(campaignData,control,artifacts,reportReadiness,reportApproval,remoteReportStatus,needsInfoDraft)
⋮----
async function refreshRunMonitor(campaignId)
⋮----
function startRunMonitor(campaignId)
⋮----
function loadQuickPrefs()
⋮----
function applyQuickPrefs()
⋮----
function saveQuickPrefs()
⋮----
function rememberLastProgram(handle)
⋮----
function lastProgramHandle()
⋮----
function normalizeServerReviewProfile(profile)
⋮----
function exactQuickProfile(key)
⋮----
async function loadServerReviewProfiles()
⋮----
function quickProfiles()
⋮----
function quickProfileKey(binding=remoteBinding)
⋮----
function saveQuickProfiles(profiles)
⋮----
function localDateTimeValue(date=new Date())
⋮----
function quickTargetSuggestions(snapshot)
⋮----
function setQuickState(label,type='')
⋮----
function restoreQuickProfile(snapshot)
⋮----
function rememberQuickProfile(payload)
⋮----
function serverProgramHasSavedProfile(handle)
⋮----
function localProgramHasSavedProfile(handle)
⋮----
function batchProgramHasSavedProfile(handle)
⋮----
function batchCatalogPrograms()
⋮----
function renderBatchCatalog()
⋮----
function renderBatchSelectionState()
⋮----
function applyDiscoveryResult(result)
⋮----
async function refreshBatchCatalog()
⋮----
function selectReadyBatchProfiles()
⋮----
function autoSelectBatchProfiles()
⋮----
async function autoQueueBatch()
⋮----
async function batchPayloadForHandle(handle)
⋮----
function renderBatchProgress(batch)
⋮----
function renderBatchStatus(batch)
⋮----
async function refreshActiveBatch()
⋮----
function startBatchMonitor(batchId)
⋮----
function latestActiveBatch(batches)
⋮----
async function restoreActiveBatch()
⋮----
async function launchSelectedBatch()
⋮----
async function cancelActiveBatch()
⋮----
function clearRemoteBinding()
⋮----
function renderProgramOptions()
⋮----
function renderRemoteScope(snapshot)
⋮----
async function loadRemoteProgram()
⋮----
function renderHackerOneLiveReadiness(payload)
⋮----
async function refreshHackerOneLiveReadiness()
⋮----
async function copyHackerOneLiveActivation()
⋮----
async function initRemoteControlCenter()
⋮----
function parseScopeDocument()
⋮----
function reviewedAtIso()
⋮----
function buildPolicy()
⋮----
function buildPayload()
⋮----
function conservativeBlockers(policy)
⋮----
function payloadFingerprint(payload)
⋮----
function invalidatePreview()
⋮----
function renderScopeList(targetId,values,emptyLabel)
⋮----
function renderPreview(preview,payload,blockers)
⋮----
async function preview()
⋮----
async function launch()
⋮----
async function importScopeFile()
```

## File: sw.js
```javascript

```
