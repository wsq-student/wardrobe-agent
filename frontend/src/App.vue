<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { router } from './router'
import { api, useWardrobe, ApiError } from './store'
import Icon from './components/Icon.vue'

const store = useWardrobe(), route = useRoute()
const navigation = [
  { key:'closet', label:'我的衣橱', icon:'closet', subtitle:'整理与发现' },
  { key:'stylist', label:'穿搭顾问', icon:'sparkles', subtitle:'让灵感照顾日常' },
  { key:'studio', label:'试衣工作室', icon:'image', subtitle:'看见搭配的可能' },
  { key:'profile', label:'个人档案', icon:'user', subtitle:'更了解你' },
]
const tab = computed(() => String(route.name || 'closet'))
const page = computed(() => navigation.find(n => n.key === tab.value) || navigation[0])
const booting = ref(true), registering = ref(false), email = ref(''), password = ref('')
const health = ref<any>({}), connectionError = ref(''), pending = reactive(new Set<string>())
const contentEl = ref<HTMLElement>(), messagesEl = ref<HTMLElement>(), promptInput = ref<any>()
const search = ref(''), category = ref(''), status = ref(''), closetPage = ref(1), studioFilter = ref('all')
const prompt = ref(''), locations = ref<any[]>([]), profile = ref<any>({}), profileBaseline = ref('')
const editOpen = ref(false), edit = ref<any>(null), editBaseline = ref('')
const feedback = ref<any>(null), rating = ref(4), comment = ref('')
const trial = ref<any>(null), consent = ref(false), preview = ref<{urls:string[];index:number}|null>(null)
const stickToBottom = ref(true), newMessages = ref(false), contentScroll = ref(0)
const scrollPositions = new Map<string,number>()
const categories: Record<string,string> = { tops:'上衣', bottoms:'下装', 'one-pieces':'连衣装', outerwear:'外套', shoes:'鞋履', accessories:'配饰', unknown:'待分类' }
const states: Record<string,string> = { available:'可穿', washing:'清洗中', unavailable:'暂不可用' }
const jobNames: Record<string,string> = {classify:'衣物识别',recommend:'穿搭推荐',tryon:'虚拟试衣'}
const jobStates: Record<string,string> = {queued:'排队中',running:'处理中',completed:'已完成',failed:'未完成'}
const stages: Record<string,string> = {tryon_plan:'制定试穿计划',tryon_render:'生成效果图',tryon_review:'检查试穿效果',tryon_repair:'调整搭配细节',tool:'查询衣橱与天气',context:'整理需求',plan:'制定穿搭',validation:'检查搭配',repair:'修正搭配'}
const media = (key:string) => '/api/media/' + key
const isActive = (j:any) => ['queued','running'].includes(j.status)
const conversation = computed(() => { const n = Number(route.query.conversation); return Number.isSafeInteger(n) && n > 0 ? n : null })
const lastConversation = ref<number|null>(null)
watch(conversation,id=>{if(id)lastConversation.value=id},{immediate:true})
function navDestination(key:string) { return key==='stylist' && lastConversation.value ? {path:'/stylist',query:{conversation:String(lastConversation.value)}} : '/'+key }
const activeJobs = computed(() => store.jobs.filter(isActive))
const filtered = computed(() => store.items.filter(i => (!category.value || i.category===category.value) && (!status.value || i.status===status.value) && [i.name,i.color,categories[i.category]].some(s => s?.toLowerCase().includes(search.value.trim().toLowerCase()))))
const shownItems = computed(() => filtered.value.slice((closetPage.value-1)*12,closetPage.value*12))
const closetImages = computed(() => shownItems.value.map(i => media(i.image_key)))
const latest = computed(() => store.recommendations.filter(r => r.conversation_id===conversation.value))
const currentJobs = computed(() => store.jobs.filter(j => j.kind==='recommend' && j.conversation_id===conversation.value))
const currentPending = computed(() => currentJobs.value.find(isActive))
const currentFailure = computed(() => currentJobs.value[0]?.status==='failed' ? currentJobs.value[0] : null)
const activeMessages = computed(() => store.conversations.find(c => c.id===conversation.value)?.messages || [])
const studioJobs = computed(() => store.jobs.filter(j => j.kind==='tryon' && (studioFilter.value==='all' || (studioFilter.value==='active' ? isActive(j) : j.status===studioFilter.value))))
const requestedJob = computed(() => store.jobs.find(j => j.id===route.query.job))
const lastSelectedJob = ref<any>(null)
watch(requestedJob,job=>{if(job)lastSelectedJob.value=job},{immediate:true})
const selectedJob = computed(() => requestedJob.value || (!route.query.job ? lastSelectedJob.value : null))
const selectedConversationId = computed(() => selectedJob.value?.conversation_id || store.recommendations.find(r=>r.id===selectedJob.value?.recommendation_id)?.conversation_id)
const taskOpen = computed({ get:() => tab.value==='studio' && !!route.query.job, set:(open:boolean) => { if (!open) { const query={...route.query};delete query.job;void router.replace({path:route.path,query}) } } })
const profileDirty = computed(() => !!store.user && JSON.stringify(normalizeProfile(profile.value))!==profileBaseline.value)
const returnTarget = computed(() => { const q=route.query.returnTo;return typeof q==='string' && /^\/(stylist|studio)(\?|$)/.test(q) ? q : '' })
const lastStage = (job:any) => stages[job.trace?.at(-1)?.stage] || jobStates[job.status]
const dateLabel = (value:string) => new Date(value.endsWith('Z')?value:value+'Z').toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})
const parseMessage = (message:any) => { if(message.role==='user') return message.content;try { const data=JSON.parse(message.content);return [data.reason,data.clarification,...(data.warnings||[])].filter(Boolean).join('\n') } catch {return message.content} }

function normalizeProfile(p:any) {
  return {height_cm:p.height_cm ?? null,size:p.size||'',preferences:p.preferences||'',city:p.city||'',latitude:p.latitude ?? null,longitude:p.longitude ?? null,daily_enabled:!!p.daily_enabled,daily_hour:p.daily_hour ?? 7}
}
function resetProfile() { profile.value=normalizeProfile(store.user?.profile || {});profileBaseline.value=JSON.stringify(profile.value) }
async function act(key:string, fn:()=>Promise<any>) {
  if(pending.has(key)) return false
  pending.add(key)
  try { await fn();return true } catch(e:any) { ElMessage.error(e.message||'操作未完成，请重试');return false } finally { pending.delete(key) }
}
async function refresh(silent=false) {
  try { await store.refresh(); health.value=await api('/health');connectionError.value='' }
  catch(e:any) { if(e.status!==401) { connectionError.value=e.message;if(!silent) ElMessage.error(e.message) } }
}
async function login() {
  await act('login',async()=>{
    await api('/auth/'+(registering.value?'register':'login'),{method:'POST',body:JSON.stringify({email:email.value,password:password.value})})
    await store.refresh();health.value=await api('/health');resetProfile();password.value='';connectionError.value=''
  })
}
async function saveProfile(notify=true) {
  return act('profile',async()=>{await api('/profile',{method:'PUT',body:JSON.stringify(normalizeProfile(profile.value))});await store.refresh();resetProfile();if(notify)ElMessage.success('个人档案已保存')})
}
async function canLeaveProfile() {
  if(tab.value!=='profile' || !profileDirty.value) return true
  try {
    await ElMessageBox.confirm('个人档案有未保存的修改，是否保存后离开？关闭此窗口可继续编辑。','离开个人档案',{confirmButtonText:'保存并离开',cancelButtonText:'放弃修改',distinguishCancelAndClose:true,type:'warning'})
    return await saveProfile(false)
  } catch(action) { if(action==='cancel'){resetProfile();return true}return false }
}
const removeGuard = router.beforeEach(async(to,from)=>{
  if(to.path!==from.path && !(await canLeaveProfile())) return false
  if(to.path!==from.path && contentEl.value) scrollPositions.set(from.path,contentEl.value.scrollTop)
  return true
})
watch(()=>route.path,async()=>{await nextTick();contentEl.value?.scrollTo({top:scrollPositions.get(route.path)||0});contentScroll.value=contentEl.value?.scrollTop||0})
async function logout() { if(!(await canLeaveProfile()))return;await act('logout',async()=>{await api('/auth/logout',{method:'POST'});store.reset();resetProfile();lastConversation.value=null;lastSelectedJob.value=null;consent.value=false;prompt.value='';preview.value=null;trial.value=null;editOpen.value=false;await router.replace('/closet')}) }
async function go(page:string,query:Record<string,string>={}) { await router.push({path:'/'+page,query}) }
async function newConversation() { await go('stylist');await nextTick();promptInput.value?.focus() }
async function chooseConversation(id:number|null) { await go('stylist',id?{conversation:String(id)}:{}) }
function openJob(job:any) { void go('studio',{job:job.id}) }
function showPreview(urls:string[],index=0) { if(urls.length)preview.value={urls,index} }
function previewOutfit(rec:any,id:number) { const items=rec.item_ids.map((iid:number)=>store.items.find(i=>i.id===iid)).filter(Boolean);showPreview(items.map((i:any)=>media(i.image_key)),items.findIndex((i:any)=>i.id===id)) }
function clearFilters() { search.value='';category.value='';status.value='';closetPage.value=1 }
watch([search,category,status],()=>closetPage.value=1)
watch(()=>filtered.value.length,()=>{closetPage.value=Math.min(closetPage.value,Math.max(1,Math.ceil(filtered.value.length/12)))})

async function upload(event:Event,personal=false) {
  const input=event.target as HTMLInputElement,files=Array.from(input.files||[])
  if(!files.length)return
  if(files.some(f=>!['image/jpeg','image/png','image/webp'].includes(f.type)||f.size>12*1024*1024)){ElMessage.warning('请上传不超过 12 MB 的 JPG、PNG 或 WebP 图片');input.value='';return}
  await act(personal?'photo':'upload',async()=>{
    let completed=0
    try {for(const file of files){const body=new FormData();body.append('file',file);await api(personal?'/profile/photo':'/items',{method:'POST',body});completed++}}
    finally {await store.refresh();if(completed)ElMessage.success(personal?'全身照已更新':'已上传 '+completed+' 件衣物，正在识别')}
  });input.value=''
}
function openEdit(item:any) {edit.value={id:item.id,image_key:item.image_key,name:item.name,category:item.category,color:item.color,season:[...item.season],status:item.status};editBaseline.value=JSON.stringify(edit.value);editOpen.value=true}
async function closeEdit(done:()=>void) {
  if(pending.has('edit'))return
  if(edit.value && JSON.stringify(edit.value)!==editBaseline.value){try{await ElMessageBox.confirm('衣物信息尚未保存，确定放弃修改？','未保存的修改',{confirmButtonText:'放弃修改',cancelButtonText:'继续编辑',type:'warning'})}catch{return}}
  done()
}
async function saveItem() { await act('edit',async()=>{const {id,image_key,...data}=edit.value;await api('/items/'+id,{method:'PUT',body:JSON.stringify(data)});await store.refresh();editOpen.value=false;ElMessage.success('衣物信息已保存')}) }
async function removeItem(item:any) {try{await ElMessageBox.confirm('将删除「'+item.name+'」及其照片，确定继续？','删除衣物',{type:'warning',confirmButtonText:'删除',cancelButtonText:'取消'});await act('delete-'+item.id,async()=>{await api('/items/'+item.id,{method:'DELETE'});await store.refresh();editOpen.value=false;ElMessage.success('衣物已删除')})}catch{}}
async function classify(item:any) {await act('classify-'+item.id,async()=>{const r=await api('/items/'+item.id+'/classify',{method:'POST'});await store.refresh();ElMessage.success('识别任务已提交');void r})}
async function searchCity() {await act('city',async()=>{locations.value=await api('/locations?q='+encodeURIComponent(profile.value.city));if(!locations.value.length)ElMessage.info('未找到城市，可尝试英文名称或手动填写坐标')})}
async function deletePhoto() {try{await ElMessageBox.confirm('删除已保存的个人全身照？','删除照片',{confirmButtonText:'删除',cancelButtonText:'取消',type:'warning'});await act('photo',async()=>{await api('/profile/photo',{method:'DELETE'});await store.refresh()})}catch{}}

async function send() {
  if(!prompt.value.trim() || currentPending.value || pending.has('recommend'))return
  await act('recommend',async()=>{const r=await api('/recommend',{method:'POST',body:JSON.stringify({prompt:prompt.value.trim(),conversation_id:conversation.value})});prompt.value='';stickToBottom.value=true;await chooseConversation(r.conversation_id);await store.refresh();await scrollBottom()})
}
function composerKey(event:KeyboardEvent) {if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();void send()}}
async function scrollBottom(smooth=false) {await nextTick();const el=messagesEl.value;if(el)el.scrollTo({top:el.scrollHeight,behavior:smooth?'smooth':'auto'});newMessages.value=false}
function messageScroll() {const el=messagesEl.value;if(el){stickToBottom.value=el.scrollHeight-el.scrollTop-el.clientHeight<90;if(stickToBottom.value)newMessages.value=false}}
watch(()=>[conversation.value,activeMessages.value.length,currentPending.value?.status].join(':'),async(value,old)=>{
  if(value.split(':')[0]!==old?.split(':')[0]||stickToBottom.value){stickToBottom.value=true;await scrollBottom()}else newMessages.value=true
})
watch(()=>tab.value,async(value)=>{if(value==='stylist')await scrollBottom()})
function openTrial(rec:any) {consent.value=false;trial.value={recommendation:rec}}
function openRetry(job:any) {if(job.kind==='tryon'){consent.value=false;trial.value={job}}else void submitRetry(job)}
async function submitRetry(job:any) {await act('retry-'+job.id,async()=>{const r=await api('/jobs/'+job.id+'/retry',{method:'POST'});await store.refresh();if(job.kind==='recommend'&&job.conversation_id)await chooseConversation(job.conversation_id);else openJob({id:r.job_id});ElMessage.success('任务已重新提交')})}
async function submitTrial() {
  if(!consent.value)return
  const target=trial.value
  await act('tryon',async()=>{const r=target.job?await api('/jobs/'+target.job.id+'/retry',{method:'POST'}):await api('/tryon',{method:'POST',body:JSON.stringify({recommendation_id:target.recommendation.id,consent:true})});trial.value=null;await store.refresh();await go('studio',{job:r.job_id});ElMessage.success('试穿任务已提交')})
}
async function completeProfile() {trial.value=null;await go('profile',{returnTo:route.fullPath})}
async function saveAndReturn() {if(await saveProfile())await router.push(returnTarget.value||'/stylist')}
async function deleteJob(job:any) {try{await ElMessageBox.confirm('删除这条记录及其生成图片？','删除记录',{confirmButtonText:'删除',cancelButtonText:'取消',type:'warning'});await act('delete-job',async()=>{await api('/jobs/'+job.id,{method:'DELETE'});await store.refresh();if(route.query.job===job.id)taskOpen.value=false;ElMessage.success('记录已删除')})}catch{}}
async function rate() {await act('feedback',async()=>{await api('/feedback',{method:'POST',body:JSON.stringify({recommendation_id:feedback.value.id,rating:rating.value,comment:comment.value})});feedback.value=null;comment.value='';ElMessage.success('谢谢反馈，后续推荐会参考你的偏好')})}
function beforeUnload(event:BeforeUnloadEvent) {if(profileDirty.value){event.preventDefault();event.returnValue=''}}
let timer:ReturnType<typeof setTimeout>|undefined, disposed=false
async function poll() {
  if(disposed)return
  if(store.user && !document.hidden)await refresh(true)
  if(!disposed)timer=setTimeout(poll,activeJobs.value.length?3000:12000)
}
function visibilityChanged() {if(!document.hidden && store.user)void refresh(true)}
onMounted(async()=>{try{await store.refresh();health.value=await api('/health');resetProfile()}catch(e:any){if(!(e instanceof ApiError&&e.status===401))connectionError.value=e.message}finally{booting.value=false}timer=setTimeout(poll,3000);window.addEventListener('beforeunload',beforeUnload);document.addEventListener('visibilitychange',visibilityChanged)})
onUnmounted(()=>{disposed=true;clearTimeout(timer);removeGuard();window.removeEventListener('beforeunload',beforeUnload);document.removeEventListener('visibilitychange',visibilityChanged)})
</script>

<template>
  <div v-if="booting" class="boot-screen"><div class="brand">衣序<span>YOUR PERSONAL WARDROBE</span></div><p>正在打开你的衣橱…</p></div>
  <div v-else-if="!store.user" class="login-shell">
    <section class="login-art"><div class="brand">衣序<span>WARDROBE INTELLIGENCE</span></div><div><p class="eyebrow">穿搭，从你的衣橱开始</p><h1>让每一件衣服，<br>都有新的可能。</h1><p>整理衣橱 · 天气推荐 · 个人试穿</p></div><span class="login-caption">LESS GUESSWORK. MORE YOU.</span><div class="art-rings" aria-hidden="true"></div></section>
    <main class="login-form"><p class="eyebrow">YOUR EVERYDAY STYLIST</p><h2>{{registering?'创建你的衣橱':'欢迎回来'}}</h2><p class="muted">从今天开始，穿得更有自己的风格。</p><el-alert v-if="connectionError" :title="connectionError" type="error" :closable="false"/><el-form label-position="top" @submit.prevent="login"><el-form-item label="邮箱"><el-input v-model="email" type="email" autocomplete="username" placeholder="you@example.com" required/></el-form-item><el-form-item label="密码"><el-input v-model="password" type="password" :autocomplete="registering?'new-password':'current-password'" show-password placeholder="至少 8 个字符" required/></el-form-item><el-button type="primary" native-type="submit" :loading="pending.has('login')" class="full">{{registering?'注册并开始':'登录衣橱'}}</el-button></el-form><button class="text-button" @click="registering=!registering">{{registering?'已有账号？登录':'第一次使用？创建账号'}}</button></main>
  </div>
  <div v-else class="app-shell">
    <aside class="sidebar"><div class="brand">衣序<span>YOUR PERSONAL WARDROBE</span></div><div class="sidebar-label">我的空间</div><nav aria-label="主导航"><router-link v-for="n in navigation" :key="n.key" :to="navDestination(n.key)" :class="{selected:tab===n.key}" :aria-current="tab===n.key?'page':undefined"><Icon :name="n.icon"/><span>{{n.label}}</span><span v-if="n.key==='studio'&&activeJobs.length" class="nav-count">{{activeJobs.length}}</span></router-link></nav><div class="sidebar-note"><Icon name="sparkles"/><p>穿你喜欢的，<br>也发现新的自己。</p></div><div class="sidebar-user"><div class="avatar">{{store.user.email[0].toUpperCase()}}</div><span :title="store.user.email">{{store.user.email}}</span><button class="icon-button" aria-label="退出登录" title="退出登录" @click="logout"><Icon name="exit" :size="18"/></button></div></aside>
    <main class="workspace">
      <header class="topbar"><div class="breadcrumb">我的空间 <span>/</span> <strong>{{page.label}}</strong></div><div class="topbar-actions"><button v-if="activeJobs.length" class="task-indicator" @click="openJob(activeJobs[0])"><span class="pulse"></span>{{activeJobs.length}} 个任务处理中</button><span class="date">{{new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'})}}</span><button class="icon-button" :class="{spinning:pending.has('refresh')}" title="刷新数据" aria-label="刷新数据" @click="act('refresh',()=>refresh())"><Icon name="refresh" :size="18"/></button></div></header>
      <div ref="contentEl" class="workspace-body" :class="{'chat-page':tab==='stylist'}" @scroll="contentScroll=contentEl?.scrollTop||0">
        <el-alert v-if="connectionError" :title="connectionError+'，正在尝试重新连接'" type="error" :closable="false" show-icon class="connection-alert"/>
        <el-alert v-if="!health.deepseek_configured" title="智能服务待配置，衣橱整理和个人档案仍可使用。" type="info" :closable="false" show-icon/>
        <section v-if="tab==='closet'" class="page-panel">
          <div class="page-heading"><div><p class="eyebrow">A WARDROBE OF POSSIBILITIES</p><h1>你的衣橱，无限搭配。</h1><p class="muted">好穿搭，始于了解你已经拥有的。</p></div><div class="heading-actions"><el-button @click="go('stylist')"><Icon name="sparkles" :size="17"/>今天怎么穿</el-button><label class="upload-button" :class="{disabled:pending.has('upload')}"><Icon name="plus" :size="18"/>{{pending.has('upload')?'正在上传…':'添加衣物'}}<input type="file" accept="image/jpeg,image/png,image/webp" multiple :disabled="pending.has('upload')" @change="upload($event)"></label></div></div>
          <div class="closet-summary"><span><strong>{{store.items.length}}</strong>件衣物</span><span><strong>{{store.items.filter(i=>i.status==='available').length}}</strong>件随时可穿</span><span><strong>{{store.recommendations.length}}</strong>次穿搭灵感</span><span class="summary-note">让熟悉的衣服，穿出新鲜感。</span></div>
          <div class="closet-toolbar"><el-input v-model="search" clearable placeholder="搜索衣物、颜色或品类" class="search-field"><template #prefix><Icon name="search" :size="17"/></template></el-input><el-select v-model="status" placeholder="全部状态" clearable aria-label="按衣物状态筛选"><el-option v-for="(v,k) in states" :key="k" :label="v" :value="k"/></el-select><span class="muted">{{filtered.length}} 件衣物</span></div>
          <div class="category-tabs" aria-label="衣物品类"><button :class="{active:category===''}" @click="category=''">全部衣物 <small>{{store.items.length}}</small></button><button v-for="(label,key) in categories" :key="key" :class="{active:category===key}" @click="category=String(key)">{{label}}<small>{{store.items.filter(i=>i.category===key).length}}</small></button></div>
          <div v-if="!filtered.length" class="empty-state"><Icon name="closet" :size="46"/><h3>{{store.items.length?'暂时没有符合条件的衣物':'把喜欢的衣服放进来'}}</h3><p>{{store.items.length?'试试更换关键词，或清除筛选条件。':'上传清晰的单件衣物照片，自动整理分类，也能随时手动编辑。'}}</p><el-button v-if="store.items.length" @click="clearFilters">清除筛选</el-button><label v-else class="upload-button"><Icon name="plus" :size="18"/>上传衣物<input type="file" accept="image/jpeg,image/png,image/webp" multiple @change="upload($event)"></label></div>
          <div class="clothes-grid"><article v-for="(item,index) in shownItems" :key="item.id" class="clothing-card"><button class="clothing-image" :aria-label="'放大查看'+item.name" @click="showPreview(closetImages,index)"><el-image :src="media(item.image_key)" fit="contain" lazy><template #error><span class="image-error">图片暂不可用</span></template></el-image><span class="status-badge" :class="item.status">{{states[item.status]}}</span><span class="image-expand"><Icon name="expand" :size="16"/></span></button><div class="card-info"><span class="card-meta">{{categories[item.category]}}<span>·</span>{{item.color||'颜色待识别'}}</span><button class="card-title" @click="openEdit(item)">{{item.name}}</button><div class="card-footer"><span>{{item.season?.join(' / ')||'季节待补充'}}</span><button class="text-button" @click="openEdit(item)">编辑衣物</button></div></div></article></div>
          <div v-if="filtered.length>12" class="pagination"><el-pagination v-model:current-page="closetPage" :page-size="12" :total="filtered.length" layout="prev, pager, next" background @current-change="contentEl?.scrollTo({top:0,behavior:'smooth'})"/></div>
        </section>

        <section v-if="tab==='stylist'" class="stylist-page">
          <div class="page-heading"><div><p class="eyebrow">YOUR EVERYDAY STYLIST</p><h1>今天，想怎么穿？</h1><p class="muted">结合天气、你的衣橱和偏好，找到合适的一套。</p></div><el-button @click="newConversation"><Icon name="plus" :size="17"/>开启新对话</el-button></div>
          <div class="stylist-layout"><section class="chat-panel"><div class="panel-heading"><div class="panel-title"><span class="small-icon"><Icon name="sparkles" :size="18"/></span><div><strong>衣序穿搭顾问</strong><small>从你已有的衣服里，发现搭配</small></div></div><el-select :model-value="conversation" placeholder="历史对话" clearable filterable aria-label="选择历史对话" @update:model-value="chooseConversation($event||null)"><el-option v-for="c in store.conversations" :key="c.id" :label="c.messages[0]?.content||'正在生成的对话'" :value="c.id"/></el-select></div><div class="message-container"><div ref="messagesEl" class="messages" tabindex="0" role="log" aria-label="穿搭对话" @scroll="messageScroll"><div v-if="!activeMessages.length&&!currentPending" class="chat-welcome"><div class="welcome-orbit"><Icon name="sparkles" :size="35"/></div><h2>让灵感照顾日常</h2><p>告诉我今天的安排，或者你想穿的风格。</p><div class="suggestions"><button v-for="s in ['帮我推荐今天的穿搭','明天通勤，舒适又正式一点','周末出游，想要轻松休闲']" :key="s" @click="prompt=s;promptInput?.focus()"><Icon name="sparkles" :size="14"/>{{s}}</button></div></div><div v-for="(m,index) in activeMessages" :key="index" class="message" :class="m.role"><span class="message-avatar"><Icon v-if="m.role!=='user'" name="sparkles" :size="16"/><template v-else>我</template></span><div><small>{{m.role==='user'?'你':'衣序顾问'}}</small><p>{{parseMessage(m)}}</p></div></div><template v-if="currentPending"><div class="message user"><span class="message-avatar">我</span><div><small>你</small><p>{{currentPending.request_text}}</p></div></div><div class="message assistant"><span class="message-avatar"><Icon name="sparkles" :size="16"/></span><div><small>衣序顾问</small><p class="thinking"><span class="pulse"></span>{{lastStage(currentPending)}}…</p></div></div></template><div v-if="currentFailure" class="inline-error"><p>{{currentFailure.error}}</p><el-button size="small" @click="openRetry(currentFailure)">重试这次推荐</el-button></div></div><button v-if="!stickToBottom" class="jump-latest" @click="stickToBottom=true;scrollBottom(true)">{{newMessages?'有新回复 · ':''}}回到最新消息</button></div><form class="composer" @submit.prevent="send"><el-input ref="promptInput" v-model="prompt" type="textarea" :rows="3" resize="none" placeholder="说说场合、风格，或告诉我只替换哪一件…" maxlength="2000" aria-label="穿搭需求" @keydown="composerKey"/><div class="composer-footer"><span>Enter 发送 · Shift + Enter 换行</span><el-button type="primary" native-type="submit" :loading="pending.has('recommend')" :disabled="!prompt.trim()||!!currentPending">{{currentPending?'正在搭配':'生成穿搭'}}<Icon name="sparkles" :size="16"/></el-button></div></form></section>
          <section class="looks-panel"><div class="panel-heading"><strong>本次穿搭</strong><span class="muted">{{latest.length?latest.length+' 套方案':'等待灵感'}}</span></div><div class="looks-scroll"><div v-if="!latest.length" class="looks-empty"><Icon name="closet" :size="38"/><h3>你的搭配会出现在这里</h3><p>与顾问聊聊，查看单品组合，<br>再生成自己的试穿效果。</p></div><article v-for="(rec,index) in latest" :key="rec.id" class="look-card"><div class="look-caption"><span>{{index===0?'最新方案':'历史方案'}}</span><small>{{dateLabel(rec.created_at)}}</small></div><div class="look-items"><button v-for="id in rec.item_ids" :key="id" :disabled="!store.items.find(i=>i.id===id)" @click="previewOutfit(rec,id)"><img v-if="store.items.find(i=>i.id===id)" :src="media(store.items.find(i=>i.id===id).image_key)" :alt="store.items.find(i=>i.id===id).name"><span>{{store.items.find(i=>i.id===id)?.name||'衣物已删除'}}</span></button></div><p>{{rec.reason}}</p><p v-if="rec.clarification" class="clarification">{{rec.clarification}}</p><p v-for="warning in rec.warnings" :key="warning" class="muted">{{warning}}</p><div class="look-actions"><el-button type="primary" @click="openTrial(rec)" :disabled="!rec.item_ids.length"><Icon name="image" :size="16"/>生成试穿图</el-button><el-button @click="feedback=rec;rating=4;comment=''">评价搭配</el-button></div></article></div></section></div>
        </section>

        <section v-if="tab==='studio'" class="page-panel"><div class="page-heading"><div><p class="eyebrow">SEE YOUR NEXT LOOK</p><h1>穿搭，先看见。</h1><p class="muted">收藏搭配灵感，看见属于你的那一套。</p></div><el-button type="primary" @click="go('stylist')"><Icon name="sparkles" :size="17"/>去搭配一套</el-button></div><div class="studio-toolbar"><div class="segmented"><button v-for="(label,key) in {all:'全部试穿',completed:'已完成',active:'进行中',failed:'未完成'}" :key="key" :class="{active:studioFilter===key}" @click="studioFilter=key">{{label}}</button></div><span class="muted">点击卡片查看大图与进度</span></div><div v-if="!studioJobs.length" class="empty-state"><Icon name="image" :size="44"/><h3>{{studioFilter==='all'?'试试，把搭配穿在身上':'暂无这类试穿记录'}}</h3><p>从穿搭顾问选择一套搭配，生成个人试穿效果。</p><el-button @click="go('stylist')">前往穿搭顾问</el-button></div><div class="result-grid"><article v-for="job in studioJobs" :key="job.id" class="result-card" :class="job.status"><button class="result-image" @click="job.result.image_key?showPreview([media(job.result.image_key)]):openJob(job)" :aria-label="job.result.image_key?'放大试穿效果':'查看试穿任务详情'"><img v-if="job.result.image_key" :src="media(job.result.image_key)" alt="个人试穿效果图" loading="lazy"><div v-else class="result-placeholder"><Icon :name="isActive(job)?'sparkles':'image'" :size="36"/><strong>{{isActive(job)?lastStage(job):'这次试穿未完成'}}</strong><span>{{isActive(job)?'可以先继续浏览，完成后会自动更新':'查看详情，了解原因并重试'}}</span></div><span class="status-badge" :class="job.status">{{jobStates[job.status]}}</span><span v-if="job.result.image_key" class="image-expand"><Icon name="expand" :size="17"/></span></button><div class="result-info"><div><strong>我的试穿搭配</strong><small>{{dateLabel(job.created_at)}}</small></div><button class="text-button" @click="openJob(job)">查看详情</button></div><p v-if="job.error" class="result-error" :title="job.error">{{job.error}}</p></article></div><section class="recent-tasks"><div class="section-heading"><h2>最近任务</h2><span class="muted">衣物识别、穿搭推荐与试穿进度</span></div><button v-for="job in store.jobs" :key="job.id" class="task-row" @click="openJob(job)"><span class="task-icon" :class="job.status"><Icon :name="job.kind==='classify'?'closet':job.kind==='recommend'?'sparkles':'image'" :size="19"/></span><div><strong>{{jobNames[job.kind]}}</strong><small>{{isActive(job)?lastStage(job):dateLabel(job.created_at)}}</small></div><span class="status-text" :class="job.status">{{jobStates[job.status]}}</span><span class="task-more">查看</span></button></section></section>

        <section v-if="tab==='profile'" class="page-panel"><div class="page-heading"><div><p class="eyebrow">MADE FOR YOUR EVERYDAY</p><h1>更了解你，穿得更自在。</h1><p class="muted">用你愿意分享的信息，建立专属穿搭档案。</p></div><el-button v-if="returnTarget" @click="router.push(returnTarget)"><Icon name="back" :size="16"/>返回穿搭</el-button></div><div class="profile-layout"><section class="profile-photo"><div class="section-heading"><h2>个人全身照</h2><span v-if="store.user.profile.photo_key" class="saved-indicator"><Icon name="check" :size="14"/>已保存</span></div><button v-if="store.user.profile.photo_key" class="profile-image" @click="showPreview([media(store.user.profile.photo_key)])" aria-label="放大个人全身照"><img :src="media(store.user.profile.photo_key)" alt="个人全身照"><span class="image-expand"><Icon name="expand" :size="18"/></span></button><div v-else class="photo-placeholder"><Icon name="user" :size="55"/><p>上传你的全身照</p><span>用于生成个人试穿效果</span></div><label class="upload-button full" :class="{disabled:pending.has('photo')}"><Icon name="plus" :size="17"/>{{pending.has('photo')?'正在上传…':store.user.profile.photo_key?'更换全身照':'上传全身照'}}<input type="file" accept="image/jpeg,image/png,image/webp" :disabled="pending.has('photo')" @change="upload($event,true)"></label><p class="muted photo-tip">单人正面站立、光线均匀，尽量露出全身。照片单独保存，上传后即可用于试穿。</p><button v-if="store.user.profile.photo_key" class="text-button danger" :disabled="pending.has('photo')" @click="deletePhoto">删除我的照片</button></section><el-form class="profile-form" label-position="top" @submit.prevent="saveProfile()"><div class="section-heading"><h2>身材与穿衣偏好</h2><span v-if="profileDirty" class="unsaved-indicator">有未保存的修改</span></div><div class="form-columns"><el-form-item label="身高（cm，可选）"><el-input-number v-model="profile.height_cm" :min="80" :max="250" placeholder="填写身高"/></el-form-item><el-form-item label="常穿尺码（可选）"><el-input v-model="profile.size" maxlength="30" placeholder="例如 M / 170"/></el-form-item></div><el-form-item label="版型与风格偏好"><el-input v-model="profile.preferences" type="textarea" :rows="3" resize="vertical" maxlength="1000" show-word-limit placeholder="例如偏爱宽松、简洁配色，通勤少穿高跟鞋"/></el-form-item><div class="form-section-heading"><h3>天气与每日推荐</h3><p class="muted">选好城市，让穿搭适应今天的天气。</p></div><el-form-item label="所在城市"><el-input v-model="profile.city" placeholder="例如 上海 / Shanghai" maxlength="100" @keydown.enter.prevent="searchCity"><template #append><el-button :loading="pending.has('city')" @click="searchCity">查询城市</el-button></template></el-input></el-form-item><div v-if="locations.length" class="city-results"><button v-for="(city,index) in locations" :key="index" type="button" @click="profile.city=city.name;profile.latitude=city.latitude;profile.longitude=city.longitude;locations=[]"><strong>{{city.name}}</strong><span>{{city.admin1}} {{city.country}}</span></button></div><el-collapse class="coordinate-options"><el-collapse-item title="查看或手动调整城市坐标" name="coordinates"><div class="form-columns"><el-form-item label="纬度"><el-input-number v-model="profile.latitude" :min="-90" :max="90" :precision="4"/></el-form-item><el-form-item label="经度"><el-input-number v-model="profile.longitude" :min="-180" :max="180" :precision="4"/></el-form-item></div></el-collapse-item></el-collapse><div class="daily-setting"><div><strong>每日自动推荐</strong><p class="muted">每天为你准备一份穿搭灵感。</p></div><el-switch v-model="profile.daily_enabled" aria-label="开启每日推荐"/></div><el-form-item v-if="profile.daily_enabled" label="生成时间（北京时间，整点）"><el-input-number v-model="profile.daily_hour" :min="0" :max="23"/></el-form-item><div class="profile-save"><span class="muted">{{profileDirty?'修改后记得保存':'档案已同步'}}</span><el-button v-if="returnTarget" type="primary" :loading="pending.has('profile')" @click="saveAndReturn">保存并返回穿搭</el-button><el-button v-else type="primary" native-type="submit" :loading="pending.has('profile')">保存个人档案</el-button></div></el-form></div></section>
      </div><button v-if="contentScroll>500 && tab!=='stylist'" class="back-to-top icon-button" aria-label="回到顶部" title="回到顶部" @click="contentEl?.scrollTo({top:0,behavior:'smooth'})"><Icon name="arrow"/></button>
    </main>

    <el-drawer v-model="editOpen" title="编辑衣物" size="460px" :before-close="closeEdit" destroy-on-close @closed="edit=null"><template v-if="edit"><button class="edit-image" aria-label="放大衣物照片" @click="showPreview([media(edit.image_key)])"><img :src="media(edit.image_key)" :alt="edit.name"><Icon name="expand" :size="18"/></button><el-form label-position="top"><el-form-item label="衣物名称"><el-input v-model="edit.name" maxlength="100"/></el-form-item><div class="form-columns"><el-form-item label="分类"><el-select v-model="edit.category"><el-option v-for="(v,k) in categories" :key="k" :label="v" :value="k"/></el-select></el-form-item><el-form-item label="颜色"><el-input v-model="edit.color" maxlength="80"/></el-form-item></div><el-form-item label="适合季节"><el-checkbox-group v-model="edit.season"><el-checkbox v-for="s in ['春','夏','秋','冬']" :key="s" :value="s">{{s}}</el-checkbox></el-checkbox-group></el-form-item><el-form-item label="衣物状态"><el-select v-model="edit.status"><el-option v-for="(v,k) in states" :key="k" :label="v" :value="k"/></el-select></el-form-item></el-form><div class="edit-secondary"><el-button :loading="pending.has('classify-'+edit.id)" @click="classify(edit)">重新识别</el-button><el-button type="danger" plain @click="removeItem(edit)">删除衣物</el-button></div></template><template #footer><el-button @click="closeEdit(()=>editOpen=false)">取消</el-button><el-button type="primary" :loading="pending.has('edit')" @click="saveItem">保存修改</el-button></template></el-drawer>
    <el-drawer v-model="taskOpen" title="任务详情" size="500px" destroy-on-close><template v-if="selectedJob"><div class="task-detail-header"><span class="task-icon" :class="selectedJob.status"><Icon :name="selectedJob.kind==='recommend'?'sparkles':'image'" :size="24"/></span><div><h2>{{jobNames[selectedJob.kind]}}</h2><p>{{dateLabel(selectedJob.created_at)}}</p></div><span class="status-text" :class="selectedJob.status">{{jobStates[selectedJob.status]}}</span></div><button v-if="selectedJob.result.image_key" class="task-detail-image" aria-label="放大试穿效果图" @click="showPreview([media(selectedJob.result.image_key)])"><img :src="media(selectedJob.result.image_key)" alt="试穿效果图"><span>点击查看大图</span></button><el-alert v-if="selectedJob.error" :title="selectedJob.error" type="error" :closable="false" show-icon/><div v-if="selectedJob.result.review" class="quality-checks"><h3>效果检查</h3><div v-for="(label,key) in {person_preserved:'人物外观',body_shape_preserved:'身材比例',garments_preserved:'衣物一致性',pose_preserved:'姿势保持',no_artifacts:'画面完整性'}" :key="key"><span>{{label}}</span><span :class="selectedJob.result.review[key]?'check-pass':'error'"><Icon v-if="selectedJob.result.review[key]" name="check" :size="15"/>{{selectedJob.result.review[key]?'通过':'待调整'}}</span></div></div><section class="task-timeline"><h3>执行进度</h3><div v-if="!selectedJob.trace.length" class="muted">{{isActive(selectedJob)?'任务正在排队，请稍候…':'暂无执行记录'}}</div><div v-for="(step,index) in selectedJob.trace" :key="index" class="timeline-step"><span :class="{live:isActive(selectedJob)&&index===selectedJob.trace.length-1}"></span><div><strong>{{stages[step.stage]||step.stage}}</strong><p>{{Array.isArray(step.detail)?step.detail.join('；'):step.detail}}</p><p v-if="step.checks?.issues?.length" class="error">{{step.checks.issues.join('；')}}</p></div></div></section><p v-for="warning in selectedJob.result.warnings||[]" :key="warning" class="muted">{{warning}}</p></template><div v-else class="empty-state"><Icon name="clock" :size="32"/><p>这条任务不在最近记录中。</p></div><template #footer><template v-if="selectedJob"><el-button v-if="selectedConversationId" @click="chooseConversation(selectedConversationId)">返回这次对话</el-button><el-button v-if="selectedJob.status==='failed'" type="primary" :loading="pending.has('retry-'+selectedJob.id)" @click="openRetry(selectedJob)">重新提交</el-button><el-button v-if="!isActive(selectedJob)" type="danger" plain :loading="pending.has('delete-job')" @click="deleteJob(selectedJob)">删除记录</el-button></template></template></el-drawer>
    <el-dialog :model-value="!!trial" title="生成你的试穿效果" width="510px" align-center :close-on-click-modal="false" @close="trial=null"><p class="dialog-description">将你的全身照与所选衣物组合成一张试穿图，生成后会进行效果检查。</p><el-alert v-if="!store.user.profile.photo_key" title="还没有个人全身照，请先到个人档案上传。" type="warning" :closable="false" show-icon/><el-alert v-else-if="!health.tryon_configured" title="试衣服务暂未配置完成，请检查服务配置。" type="warning" :closable="false" show-icon/><div class="trial-notice"><Icon name="image" :size="23"/><div><strong>最多生成 {{health.tryon_max_attempts||2}} 次</strong><p>DeepSeek 规划与检查，豆包生成图片，按实际调用计费。效果图用于搭配参考。</p></div></div><el-checkbox v-model="consent" class="consent-checkbox">同意将本人全身照与衣物图交由 DeepSeek 和豆包处理</el-checkbox><template #footer><el-button @click="trial=null" :disabled="pending.has('tryon')">取消</el-button><el-button v-if="!store.user.profile.photo_key" type="primary" @click="completeProfile">完善个人档案</el-button><el-button v-else type="primary" :loading="pending.has('tryon')" :disabled="!consent||!health.tryon_configured" @click="submitTrial">确认生成</el-button></template></el-dialog>
    <el-dialog :model-value="!!feedback" title="这套搭配适合你吗？" width="450px" align-center :close-on-click-modal="false" @close="feedback=null"><p class="muted">你的评价将用于后续推荐。</p><el-rate v-model="rating" size="large"/><el-input v-model="comment" type="textarea" :rows="4" placeholder="例如颜色喜欢，但希望下次更休闲" maxlength="500" show-word-limit/><template #footer><el-button @click="feedback=null">取消</el-button><el-button type="primary" :loading="pending.has('feedback')" @click="rate">提交反馈</el-button></template></el-dialog>
    <el-image-viewer v-if="preview" :url-list="preview.urls" :initial-index="Math.min(preview.index,preview.urls.length-1)" teleported hide-on-click-modal @close="preview=null"/>
  </div>
</template>
