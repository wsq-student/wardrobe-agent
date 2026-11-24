"""Build an offline, private evidence document from an existing read-only export."""
import base64
from datetime import datetime,timedelta
import hashlib
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'private-docs/task-flow-20261124'
s=json.loads((OUT/'snapshot.json').read_text(encoding='utf-8-sig'))
j=s['target_job'];r=s['recommendation'];p=s['recommendation_job'];u=s['user_current']
views={}
def esc(v):return html.escape(str(v))
def dump(v):return json.dumps(v,ensure_ascii=False,indent=2)
def block(label,value,kind='record',opened=False):
    ident='data-'+str(len(views)+1);views[ident]={'label':label,'kind':kind,'value':value}
    return '<details class="json-block"'+(' open' if opened else '')+'><summary>'+esc(label)+'<span class="evidence '+kind+'">'+{'record':'持久化记录','current':'当前快照','rebuild':'依据源码重构','missing':'未留存'}[kind]+'</span></summary><div class="json-actions"><button data-download="'+ident+'">下载完整 JSON</button><label><input type="checkbox" data-binary="'+ident+'">显示完整图片编码</label></div><pre data-view="'+ident+'"></pre></details>'
def table(headers,rows):
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
sections=[]
def section(ident,title,body):sections.append((ident,title,'<section id="'+ident+'"><h2>'+esc(title)+'</h2>'+body+'</section>'))
def para(text):return '<p>'+esc(text)+'</p>'
def code(text):return '<pre class="code">'+esc(text)+'</pre>'
def localtime(text):return (datetime.fromisoformat(text)+timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')+' 北京时间'
def data_uri(key):
    a=s['assets'][key];return 'data:'+a['mime']+';base64,'+a['base64']
asset_folder=OUT/'assets';asset_folder.mkdir(exist_ok=True)
for n,(key,a) in enumerate(s['assets'].items()):
    if a['available']:(asset_folder/(str(n+1)+'-'+Path(key).name)).write_bytes(base64.b64decode(a['base64']))

duration=(datetime.fromisoformat(j['updated_at'])-datetime.fromisoformat(j['created_at'])).total_seconds()
section('overview','这份文档对应哪一次真实任务',
    para('我们复盘数据库中最近一次成功试衣任务，并关联它之前的推荐任务、对话、衣物和照片。真实输入是用户在同一会话中要求“今天通勤，帮我搭配一套，用仅存的两件”，经澄清后又说“不用补充了，就选这两件”。系统选中毛衣和下装，随后生成试衣图。')+
    table(['项目','真实值'],[['试衣 Job ID',j['id']],['推荐 Job ID',p['id']],['推荐记录与会话','recommendations.id = '+str(r['id'])+'；conversations.id = '+str(r['conversation_id'])],['执行时间',localtime(j['created_at'])+' → '+localtime(j['updated_at'])],['数据库记录的试衣墙钟时间',str(duration)+' 秒 包括队列等待与执行，不能拆解为各模型耗时'],['实际模型',j['result']['controller']+' 规划和检查；'+j['result']['renderer']+' 生成图片'],['实际次数与结果',str(j['result']['attempts'])+' 次图片生成；五项视觉检查为 true；issues 为空；任务 completed']])+
    '<h3>如何辨认数据来源</h3>'+table(['标记','含义','阅读时要注意'],[['持久化记录','从 MySQL Job、Recommendation、Conversation 读取','是已保存的字段值；不等于完整原始 HTTP 日志'],['当前快照','导出时读取的档案、衣物、Redis 缓存和源代码','这些数据可能在任务之后被编辑；不能全部回填为历史输入'],['依据源码重构','以原始记录和当前实现组装的消息、请求和状态','展示真实实现的形态，明确不是抓包得到的原始报文'],['未留存','原始天气返回、工具参数、模型用量等缺失证据','不会补写或编造这些字段的真实值']])+
    para('安全处理：不导出登录密码及密码哈希、JWT Cookie、API Key、数据库和对象存储密码。本文包含用户本人照片、衣物图、邮箱和档案，只保存在本地私有目录，没有上传到新的外部服务。'))

flow='<div class="flow">'+''.join('<a href="#'+x[0]+'"><b>'+x[1]+'</b><span>'+x[2]+'</span></a>' for x in [('entry','用户与接口','需求文字 / 同意使用照片'),('recommend','推荐 Agent','工具查询 → 结构化搭配 → 校验'),('queue','任务调度','MySQL Job → Redis → Celery'),('plan','试衣规划','DeepSeek 接收人物与衣物图'),('render','图像生成','Seedream Flash 多图编辑'),('review','视觉检查','DeepSeek 对照参考图检查'),('result','保存与展示','S3 私有图片 → 用户页面')])+'</div>'
section('map','先沿着这条数据路径阅读',flow+para('模型负责理解和生成；Python 工具负责读取数据库、获取天气、取图片和保存图片；LangGraph 决定节点顺序与分支；Celery 负责异步执行。MySQL 存业务记录，Redis 既作为任务队列也作为天气缓存，对象存储保存图片文件。')+
    table(['数据载体','在本次链路里承载什么','是否直接传给模型'],[['MySQL Item 行','衣物 ID、标签、可用状态、图片 key','推荐工具会返回标签；图片 key 本身只是字符串'],['S3 对象 bytes','人物照、毛衣图、下装图、已保存结果','试衣规划、图片编辑和视觉检查会接收图片编码'],['JSON messages','系统约束、用户需求、历史消息、工具返回','通过模型接口传输'],['LangGraph State','messages、prompt、attempt、candidate、review 等运行状态','按节点取出其中部分字段；不是整份状态自动发给模型'],['Job.trace','阶段名称、提示词、参考图哈希、检查结果','用于复盘和前端进度；不包含模型隐藏思维过程']]))

section('entry','入口数据与身份如何关联',
    para('本次推荐任务中保存的最新用户输入如下。该输入已经是在同一会话中的第三轮要求，前两轮的澄清记录也保存在后面的完整会话 JSON 中。')+
    block('推荐任务 payload 原值',p['payload'],opened=True)+
    para('用户身份来自已登录会话，后端解码 JWT 后得到 user_id = 5。user_id 由后端绑定，用户或模型不能通过请求体任意指定其他人的衣橱。原始 Cookie 和 HTTP 接入日志没有留存，下面是根据 Pydantic 接口定义与保存的 payload 得到的等效请求形态。')+
    block('等效推荐 HTTP 请求 不是原始抓包',{'method':'POST','path':'/api/recommend','headers':{'Content-Type':'application/json','Cookie':'session=[REDACTED]'},'body':p['payload']},'rebuild')+
    block('试衣任务 payload 原值',j['payload'],opened=True)+
    block('等效试衣 HTTP 请求 不是原始抓包',{'method':'POST','path':'/api/tryon','headers':{'Content-Type':'application/json','Cookie':'session=[REDACTED]'},'body':j['payload']},'rebuild')+
    table(['字段','本次值','在哪里发挥作用'],[['prompt',p['payload']['prompt'],'交给推荐 Agent 理解用户约束'],['conversation_id',r['conversation_id'],'读取同一会话历史'],['recommendation_id',r['id'],'试衣任务据此找到选中的衣物 ID'],['consent',j['payload'].get('consent'),'试衣接口确认用户同意使用照片；不是模型参数'],['user_id',j['user_id'],'数据库查询、图片所属路径与数据隔离']]))

profile=s['user_current']['profile']
section('profile','用户档案中每个字段流向哪里',
    para('下面是导出时的完整用户行，登录密码字段已排除。历史执行没有保存独立的 profile 快照，因此身高、尺码、城市等当前值不自动等于当时的值。人物照的原始字节另有哈希记录，可以单独验证。')+
    block('用户与个人档案 当前值',s['user_current'],'current',True)+
    table(['字段','当前值','实际用途'],[['id',u['id'],'作为所有者 ID，用于限定数据库行和媒体访问'],['email',u['email'],'登录与页面显示；推荐和试衣消息组装没有发送邮箱'],['height_cm',profile.get('height_cm'),'get_preferences 返回给推荐模型的用户自填资料'],['size',profile.get('size'),'推荐参考尺码，不是从照片推算的尺寸'],['preferences',repr(profile.get('preferences','')),'推荐工具返回；试衣规划也在文本中读取此字段'],['city',profile.get('city'),'供用户理解地点；天气调用实际使用经纬度'],['latitude / longitude',str(profile.get('latitude'))+' / '+str(profile.get('longitude')),'传给天气 API 并参与 Redis 缓存 key'],['photo_key',profile.get('photo_key'),'从私有 S3 读取人物图；get_preferences 会排除此字段'],['daily_enabled',profile.get('daily_enabled'),'控制定时推荐，本次手动任务没有靠它触发'],['daily_hour',profile.get('daily_hour'),'定时推荐时间，北京时间；不参与图片渲染']]))

section('wardrobe','模型如何拿到这两件衣物',
    para('推荐 Worker 首先按 user_id 读取用户衣橱。当前衣橱只有两行。推荐工具返回的是 item_dict 形成的 JSON 标签，不会在这一阶段自动把每件原图编码传给模型。')+
    code('SQLAlchemy：select(Item).where(Item.user_id == user.id)\n等价筛选条件：WHERE items.user_id = 5\nsearch_wardrobe：仅返回 status == "available" 的衣物，可再按 category 筛选')+
    block('两件衣物的完整数据库行 当前快照',s['wardrobe_current'],'current',True)+
    table(['字段','含义','模型与程序如何使用'],[['id','衣物主键','推荐输出选择 ID，后端用 ID 查回真实行'],['user_id','所属用户','后端数据隔离，item_dict 不返回这一列'],['name','衣物名称','推荐理由和试衣清单描述'],['category','tops / bottoms 等品类','工具筛选、上下装完整性校验'],['color','颜色标签，可以为空字符串','为空时推荐无法仅从标签判断颜色'],['season','季节字符串数组，可以为空数组','交给模型参考；当前规则并未把天气与季节写成确定性评分'],['status','available / washing / unavailable','available 才能参与推荐和试衣'],['image_key','私有对象存储 key','程序据此读取 bytes，随后转换为多模态图片输入'],['tags','分类模型保存的标签对象','包括原始分类名称、颜色、季节和描述；手动编辑字段可能与 tags 有差异']])+
    para('本次下装 id 4 名称仍为“新衣物”，color 为空、season 为空、tags 为空。推荐结果因此明确提醒下装信息不完整。试衣规划会重新看到下装原图，所以保存的生图提示词能够描述“蓝色牛仔裤”。这是两个阶段读取的数据不同带来的结果。')+
    block('与这两件衣物相关的分类任务 全部现存记录',s['classification_jobs'])+
    para('这些分类任务包含失败与完成记录。原始上传文件和每一次分类 HTTP 响应没有归档；目前保留的是标准化图片、Item 标签以及 Job 的状态和错误。'))

section('recommend','这一次推荐 Agent 实际做了什么',
    para('推荐 Job 的 trace 明确记录了三个工具名，随后进入上下文整理、候选搭配和规则校验。工具参数、tool_call_id、每轮完整模型消息没有保存，因此只能确认这些工具被调用，无法把默认参数冒充当时的实参。')+
    block('推荐 Job 完整原始记录',p,opened=True)+
    block('三个工具的函数定义 取自当前代码',s.get('recommendation_tool_definitions_current'),'rebuild')+
    block('三个工具当前返回值 不能视为历史返回值',s.get('recommendation_tool_results_current'),'current')+
    para('工具返回是字符串形式的 JSON。LangChain 将它装入 ToolMessage；下一轮模型才能依据这些数据决策。即便模型提前结束工具调用，context 节点仍会统一调用三个工具，为后续 plan 节点组装上下文。这个固定补充机制在当前源码中存在，但原任务的完整 context.messages 未留存。')+
    block('推荐第一次模型调用的 messages 按保存的历史与当前源码组装',s.get('recommendation_initial_messages_reconstructed'),'rebuild')+
    block('本次之前的四条消息 从当前会话匹配推导',s['history_before_recommendation_inferred'],'rebuild')+
    block('会话中现存的全部消息 原始 JSON 字符串也完整保留',s['conversation_current'],opened=False)+
    block('当前反馈记录 不是历史时点快照',s['feedback_current'],'current')+
    para('本次最终输出 item_ids = [5, 4]。Pydantic 将模型输出解析为 item_ids、reason、clarification、warnings 四类字段；validate_outfit 检查 ID 是否存在、状态是否可穿、重复 ID 和品类组合。该任务一次校验通过，没有执行 repair 节点。')+
    block('推荐记录 10 完整原值',r,opened=True)+
    para('需要特别理解“通过”的范围：当前确定性规则要求上衣加下装，或一件连衣装，并不强制存在鞋和外套。这个真实案例里，模型提醒当天偏冷且缺少鞋与外套，但后端品类校验仍通过。语义提醒与程序硬规则是两个不同层次。'))

section('weather','天气数据与缓存的真实边界',
    para('推荐 trace 证明调用了 get_weather。保存的推荐理由引用了 5.6°C、体感 1.2°C、最低 -3.4°C；这些数字是模型输出中真实留存的文字，但不是原天气 JSON 的独立证据。原天气响应没有和该 Job 一起归档。')+
    block('导出时 Redis 天气缓存 含全部字段',s['weather_cache_at_export'],'current',True)+
    para('当前缓存的 time 为 14:45，current.temperature_2m 为 5.7°C，apparent_temperature 为 1.3°C；推荐任务发生在 14:19 左右，因此不能把该缓存当作当时的返回值。本次不会重新请求天气，也不会用模型文字拼造一个看似原始的天气响应。')+
    block('天气请求参数形态 按当前坐标与源码重构',{'method':'GET','url':'https://api.open-meteo.com/v1/forecast','params':{'latitude':profile.get('latitude'),'longitude':profile.get('longitude'),'current':'temperature_2m,apparent_temperature,precipitation,weather_code','daily':'temperature_2m_max,temperature_2m_min,precipitation_probability_max','timezone':'Asia/Shanghai','forecast_days':3},'cache_key':s['weather_cache_at_export']['key'] if s['weather_cache_at_export'] else None,'cache_ttl_when_written_seconds':1800},'rebuild')+
    table(['天气字段','含义'],[['latitude / longitude','天气服务实际采用的网格坐标，可能与用户输入坐标略有差异'],['current.time / interval','观测或预报时点与时间粒度'],['temperature_2m / apparent_temperature','气温与体感温度'],['precipitation / weather_code','降水量与天气编码'],['daily.time','未来几天的日期列表'],['temperature_2m_max / min','对应日期的最高与最低气温'],['precipitation_probability_max','对应日期的最大降水概率'],['current_units / daily_units','每一列的单位'],['generationtime_ms / utc_offset_seconds / timezone / elevation','服务元数据、时区偏移、时区和海拔；模型会收到当前实现返回的整个 JSON']]))

section('queue','从推荐 ID 到异步试衣任务',
    para('试衣请求中没有直接携带图片。它只保存 recommendation_id = 10 和 consent = true。Worker 再通过这条推荐记录查得 [5, 4]，按这个顺序读取毛衣与下装，再从 user.profile.photo_key 读取人物图。')+
    block('试衣 Job 完整原始记录',j,opened=True)+
    block('Celery 任务参数的等价结构 原始队列信封未留存',{'task':'app.tasks.execute','args':[j['id']],'kwargs':{},'celery_message_id':'[NOT RECORDED — distinct from Job.id]','broker':'Redis','mysql_job_status_path':['queued','running','completed'],'claim_condition':{'id':j['id'],'status':'queued'},'claim_update':{'status':'running'}},'rebuild')+
    para('Job.id 是业务任务 ID；Celery 还会生成自己的消息 ID，二者不能混为一谈。已消费的队列信封与 Celery 消息 ID 没有在本 Job 中保存。Worker 用带 status = queued 条件的 UPDATE 抢占执行权，重复投递同一个 Job 不会再执行已经运行或完成的任务。'))

refrows=[];figures=[]
for index,entry in enumerate(s['reference_integrity']):
    a=s['assets'][entry['key']]
    title=['图 1 原人物全身照','图 2 毛衣 id 5','图 3 下装 id 4'][index]
    refrows.append([title,entry['key'],str(a['bytes'])+' bytes；'+str(a['width'])+' × '+str(a['height']),entry['recorded_sha256'],'一致' if entry['matches'] else '不一致'])
    figures.append('<figure><img src="'+data_uri(entry['key'])+'" alt="'+title+'" data-enlarge><figcaption>'+title+'</figcaption></figure>')
section('images','三张真实输入图片及完整编码',
    para('三张当前对象的 SHA-256 均等于 tryon_plan.reference_hashes 中的原始记录，证明这里展示的图片字节与本次规划时使用的参考图一致。它们已经过上传时的 JPEG 标准化处理；上传前文件的 EXIF、原始文件名和原始字节没有保留。')+
    '<div class="image-grid">'+''.join(figures)+'</div>'+table(['顺序与身份','S3 key','大小与尺寸','执行时记录的 SHA256','当前复核'],refrows)+
    block('参考图完整性核对 全部原值',s['reference_integrity'],opened=True)+
    para('image 字段传给模型时使用 data:image/jpeg;base64,... 形式。完整编码收纳在本文的数据包中；展开下方 JSON 并勾选“显示完整图片编码”可查看全部字符，下载 JSON 可直接获得全部字节的可还原表示。正文默认折叠编码，只为避免几万行字符淹没机制说明。')+
    block('全部图片对象 元信息和完整 Base64',s['assets'],'current'))

controller_config={'model':j['result']['controller'],'temperature':0.3,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'},'max_tokens':1800}
deep_calls=s['reconstructed_deepseek_calls']
planning_request={'provenance':'RECONSTRUCTED current source, current preferences, hash-matched original reference images; not archived HTTP bytes','method':'POST','url':s['model_transport_configuration_now']['controller_base_url'].rstrip('/')+'/chat/completions','headers':{'Authorization':'Bearer [REDACTED]','Content-Type':'application/json'},'body':{**controller_config,'messages':deep_calls[0]['messages']}}
section('plan','DeepSeek 如何形成试衣提示词',
    para('规划请求把人物照放在图 1，按照推荐 ID [5, 4] 把毛衣和下装放在图 2、图 3。文本只给规划模型传入 id、name、category、color 的单品清单，以及用户自填 preferences。其他档案字段并没有自动全部发送给规划模型。')+
    block('DeepSeek 规划消息与请求体 全图片编码可展开',planning_request,'rebuild')+
    para('model().bind 要求输出 JSON，Plan 用 Pydantic 校验 prompt 长度为 10–1600 字符。DeepSeek 原始响应的包裹字段、request_id、usage 与原始 content 字符串没有记录；解析后的 prompt 可以从已保存的最终提示词扣除固定前缀得到。')+
    block('从 trace.prompt 推导的 Plan.prompt',s['parsed_plan_derived_from_recorded_prompt'],'rebuild',True)+
    '<h3>本次真正保存的最终生图提示词</h3><div class="long-text">'+esc(j['trace'][0]['prompt'])+'</div>'+
    block('plan 节点之后可推导的状态',{'prompt':j['trace'][0]['prompt'],'attempt':0},'rebuild')+
    para('最前面的人物保持要求是程序固定添加的；后半段由 DeepSeek 规划。最终 prompt、参考图哈希、单品 ID、提示词版本和最大次数实际写入 trace，源记录均在上面的试衣 Job JSON 中。'))

seed=s['reconstructed_seedream_request']
section('render','Seedream 真正接收哪些生成数据',
    para('Seedream 接收最终提示词和三个有序参考图。它没有接收 MySQL 连接、完整对话、天气缓存或登录邮箱。接口中的 image 数组由程序将真实图片 bytes 编码形成；下方 $asset_data_uri 指向图片数据包，文档提供单独的完整请求下载，包含真实编码。')+
    block('Seedream 请求头和请求体 模型和提示词取自原记录',seed,'rebuild',True)+
    '<button id="download-render-request">下载含完整参考图编码的 Seedream 请求 JSON</button>'+
    table(['参数','本次或实现中的值','作用'],[['model',j['result']['renderer'],'明确选择 Flash 模型，模型存在不等于账号一定开通'],['prompt','上节展示的完整 trace.prompt','决定人物保持、穿着对象、层次和背景约束'],['image','图 1 人物、图 2 毛衣、图 3 裤子','顺序与规划中的图号对应'],['size','2K','请求的生成分辨率档位，不是已保存 JPEG 的实际宽高'],['response_format','url','先取得临时 CDN 地址，再由后端下载图片'],['stream',False,'以普通 JSON 返回生成结果'],['watermark',True,'保留服务的生成水印配置'],['Authorization','Bearer [REDACTED]','仅发给方舟 API；下载 CDN 图片时不转发密钥']])+
    para('本次 Job 完成证明生成和下载得到了一张有效图片，但原始 Seedream 响应中的临时 URL、request_id、usage、原图字节和响应头没有存下来。本文不会捏造一个下载 URL。数据库中的 image_key 是后续保存到私有 S3 的路径，不是 Seedream 临时 URL。')+
    block('Seedream 原始响应的留存情况',{'data[0].url':'[NOT RECORDED]','request_id':'[NOT RECORDED]','usage':'[NOT RECORDED]','raw_image_before_storage':'[NOT STORED]','logical_render_attempts_recorded':j['result']['attempts']},'missing')+
    block('render 节点状态 仅能部分复原',{'attempt':1,'candidate':{'type':'bytes','historical_raw_bytes':'[NOT STORED]','saved_postprocessed_asset':j['result']['image_key'],'important':'saved JPEG is not byte-identical evidence of original candidate'}},'rebuild'))

review_request={'provenance':'STRUCTURE ONLY: saved JPEG substitutes for lost pre-storage generated bytes; current source; NOT the original review request','method':'POST','url':planning_request['url'],'headers':planning_request['headers'],'body':{**controller_config,'messages':deep_calls[1]['messages']}}
section('review','DeepSeek 检查的输入输出和条件分支',
    para('检查模型按照“原人物 → 毛衣 → 裤子 → 生成结果”的顺序接收四张图片，再输出结构化 Review。本次原始生成图是在检查后才重新压缩为 JPEG；原图已丢失，所以这里的重构请求使用已保存 JPEG 作为替代，只用于说明消息结构，不能宣称复原了当时检查模型看到的每个字节。')+
    block('视觉检查请求结构 使用保存后 JPEG 代替原始生成图',review_request,'rebuild')+
    block('本次真实保存的 Review 原值',j['result']['review'],opened=True)+
    table(['Review 字段','实际值','检查什么'],[['person_preserved',True,'人物外观保持'],['body_shape_preserved',True,'身材比例保持'],['garments_preserved',True,'参考单品保持'],['pose_preserved',True,'姿势保持'],['no_artifacts',True,'明显画面伪影'],['issues','[]','没有列出具体问题'],['repair_instructions',repr(j['result']['review']['repair_instructions']),'不通过时的修正指令，本次为空']])+
    code('passed = 五个布尔检查项全部为 true 且 issues 为空\n本次：passed = true → finish → 保存结果\n本次没有执行 repair，也没有生成第二张图片。\n其他任务若不通过且 attempt < max_attempts，才进入 repair → render。')+
    block('review 节点之后可推导的状态',{'review':j['result']['review'],'passed':True},'rebuild')+
    para('这些 true 是 DeepSeek 的检查结论，不是人工复核结果或真实尺码合身保证。Harness 依据明确的布尔条件控制是否继续，不能把模型判断升级成绝对正确的事实。'))

out=s['assets'][j['result']['image_key']]
api_job={k:j[k] for k in ['id','kind','status','result','error','trace','created_at']}
api_job.update({'conversation_id':j['payload'].get('conversation_id'),'recommendation_id':j['payload'].get('recommendation_id'),'request_text':None})
section('result','图片如何存储并返回到页面',
    '<figure class="output-figure"><img src="'+data_uri(j['result']['image_key'])+'" data-enlarge alt="本次真实试衣任务保存的结果"><figcaption>本次任务实际保存的 JPEG 结果 点击可放大</figcaption></figure>'+
    para('保存前，Worker 再次读取个人照片 key 和最新衣橱状态，确认照片没有被替换，选中衣物仍存在且可穿。随后 save_image 对图片进行 EXIF 方向处理、RGB 转换、最长边不超过 1600 的缩放，并以 JPEG quality=90 写入私有 S3。')+
    table(['输出字段','真实值'],[['bucket',s['infrastructure_now']['s3']['bucket']],['image_key',j['result']['image_key']],['保存后 MIME',out['mime']],['保存后尺寸',str(out['width'])+' × '+str(out['height'])],['保存后长度',str(out['bytes'])+' bytes'],['保存后 SHA256',out['sha256']],['对用户提供的图片路径','/api/media/'+j['result']['image_key']],['任务状态',j['status']],['error',repr(j['error'])]])+
    block('Job.result 完整真实值',j['result'],opened=True)+
    block('当前 /api/jobs 序列化形态 不是历史网络响应',api_job,'rebuild')+
    para('当前前端读取 /api/jobs 或 /api/jobs/{id}，根据 status 展示进度，根据 result.image_key 形成媒体 URL。GET /api/media/{key} 再次验证登录用户与 key 的用户路径匹配，才会返回图片。前端没有收到 S3 密钥，也没有得到外部平台的 Bearer Key。')+
    para('当前前端有活动任务时约每 3 秒刷新，无活动任务时约 12 秒刷新，页面不可见时暂停。本次任务早于最新前端改版，原始轮询次数、间隔和浏览器状态没有归档；这里说明的是当前页面如何展示同一条已有记录。'))

section('harness','Harness 在数据上增加了什么约束',
    table(['约束','对应数据或条件','本次结果'],[['工具范围','推荐阶段只注册 search_wardrobe、get_weather、get_preferences；试衣调用固定 Seedream 适配器','推荐 trace 保存三个工具名'],['结构化输出','Outfit / Plan / Review 的 Pydantic 字段和类型','保存了通过解析的推荐、提示词和 Review'],['真实衣物','user_id、item_ids、status，生成前后复核','选中 [5,4]，均可用'],['图片关联','reference_hashes 与图号顺序','三张参考图全部哈希匹配'],['重试预算','max_attempts = 2；只有视觉检查不通过才重绘','attempts = 1，没有修正分支'],['时间与调用边界','模型 90 秒请求超时，生图 240 秒，阶段预算 900 秒，图递归上限 20','这些是当前实现配置，原任务分阶段耗时未留存'],['异常说明','HTTP 状态与脱敏错误码映射；不记录请求体或 Key','本任务 error 为空；其他任务可显示 ModelNotOpen 等错误'],['过程落库','Job.trace 按阶段追加保存','不是 LangGraph 节点 checkpoint；进程内 candidate 字节没有归档']])+
    block('当前模型传输配置 全部非密钥参数',s['model_transport_configuration_now'],'current')+
    block('当前基础设施与鉴权结构 密码和密钥脱敏',s['infrastructure_now'],'current'))

missing=[['原始浏览器 HTTP 请求、Cookie、响应头','未留存或不导出','可按接口定义展示等效 JSON，不能证明原始请求字节'],['工具调用 args、tool_call_id、每轮模型完整响应','未留存','只能确认三个工具名和阶段顺序'],['执行时完整 profile、衣物元数据快照','未留存','当前行可能被修改；图片另有哈希证明'],['执行时天气完整响应','未随任务归档','当前缓存是更晚时点，只能单独展示'],['DeepSeek 规划原始响应与 usage','未留存','最终 prompt 被保存；原始包裹字段未知'],['Seedream 原始响应、临时 URL、原始图片','未留存','只有后处理后的 S3 JPEG 与生成次数可读'],['DeepSeek 检查原始请求 bytes 与原始响应文本','未留存','保存了 Pydantic 解析后的 Review'],['Celery 消息 ID 与完整 Redis 信封','已消费且未业务归档','Job ID 可读，消息 ID 不能据此推导'],['节点级起止时间、实际 HTTP 重试次数、费用','未记录','只能提供 Job 创建与更新的总时间差'],['模型隐藏思维过程','没有记录，也不属于本文输出','展示的是显式计划、工具数据、结构化输出和校验逻辑']]
section('gaps','哪些真实数据目前无法补回',
    para('本文已展示该任务仍然存在的业务字段、图片和关联记录。由于最初实现没有全量请求审计，无法把“所有历史线上字节”完整恢复。下面逐项列出缺失项，避免把重构模板误认为原始日志。')+
    table(['数据','状态','可以展示到什么程度'],missing)+
    para('后续若需要逐字节回放，应在任务开始时保存脱敏的输入快照，并在模型与工具适配器边界保存请求体、响应体、usage、错误码和节点时间；图片用受控对象 key 与哈希关联。只有启用这类采集后的新任务，才能形成完整的原始调用审计。本次文档没有为了补日志而再次调用模型。'))

section('source','字段检索 原始数据包与源码依据',
    para('每个 JSON 区块都可独立下载。下面的全量数据包同时包含四张真实图片的完整 Base64、关联数据库记录、重构模板及导出时源代码。浏览器中的搜索只显示匹配字段的前 100 条，单击“完整值”可查看不截断的值。')+
    '<div class="download-row"><button id="download-all">下载全部数据 JSON</button><a href="snapshot.json" download>下载本地 snapshot.json</a><a href="manifest.json" download>下载文件校验清单</a><button onclick="window.print()">打印说明正文</button></div>'+
    '<label class="field-search">字段检索<input id="field-query" placeholder="例如 reference_hashes、item_ids、prompt、weather、photo_key"></label><div id="field-results"></div>'+
    block('导出时的源代码 全部文本与 SHA256',s['source_snapshot_current'],'current')+
    para('源代码快照用于说明当前实现，并未作为原任务的版本号存入数据库。本文能基于现存字段验证真实值，但不能宣称已经证明每一行代码与历史执行时完全相同。'))

toc=''.join('<a href="#'+i+'">'+esc(t)+'</a>' for i,t,_ in sections)
review_checks=j['result']['review']
html_head='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>智慧衣橱一次真实任务完整数据流</title><style>
:root{font-family:'Microsoft YaHei','PingFang SC',sans-serif;color:#26332c;background:#f4f6f3;font-size:16px}*{box-sizing:border-box}body{margin:0}a{color:#24634b;text-underline-offset:3px}button{font:inherit;font-size:13px;cursor:pointer;padding:8px 12px;background:#fff;border:1px solid #cbd8cc;border-radius:6px;color:#315e43}button:hover{background:#edf4eb}header{background:#fff;border-bottom:1px solid #dbe3d9;padding:36px max(32px,calc((100vw - 1280px)/2))}header p{margin:9px 0 0;line-height:1.9;color:#69786b;font-size:14px}h1{color:#000;font-size:31px;line-height:1.5;margin:0 0 12px}h2{color:#000;font-size:24px;line-height:1.6;margin:0 0 23px}h3{color:#000;font-size:18px;margin:27px 0 14px}.layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:36px;max-width:1320px;margin:0 auto;padding:30px 20px 70px}nav{position:sticky;top:20px;align-self:start;max-height:94vh;overflow:auto;padding:10px 0}nav strong{font-size:13px;color:#687b67;padding:0 10px;display:block;margin-bottom:12px}nav a{display:block;text-decoration:none;color:#64745e;font-size:13px;line-height:1.7;padding:8px 10px;border-radius:5px}nav a:hover{background:#e6eee1;color:#345c35}main{min-width:0}section{background:#fff;border:1px solid #e0e6db;border-radius:10px;padding:30px;margin-bottom:25px;scroll-margin-top:18px}p{font-size:15px;line-height:1.95;overflow-wrap:anywhere;margin:0 0 19px}.table-wrap{overflow:auto;margin:20px 0 25px}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.85}th,td{border:1px solid #d9dfd6;padding:12px 13px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#edf2e9;color:#000;font-weight:600;min-width:90px}tr:nth-child(even){background:#fafbf8}td:first-child{font-weight:500;min-width:110px}.evidence{font-size:11px;border-radius:4px;padding:3px 7px;white-space:nowrap;margin-left:12px;font-weight:400}.record{background:#e8f2e3;color:#477236}.current{background:#edf0f6;color:#62718b}.rebuild{background:#fcf2df;color:#9b7636}.missing{background:#f7e9e4;color:#9b6552}.json-block{border:1px solid #dfe6db;border-radius:7px;margin:18px 0;overflow:hidden}.json-block summary{cursor:pointer;padding:14px 16px;line-height:1.8;font-size:14px;font-weight:500;list-style-position:inside;background:#f8faf5}.json-actions{display:flex;justify-content:space-between;align-items:center;gap:15px;padding:12px 14px;border-top:1px solid #e8eee0}.json-actions label{font-size:12px;color:#7c8b72}pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;font-family:Consolas,'Microsoft YaHei',monospace;font-size:12px;line-height:1.85;tab-size:2}pre[data-view]{max-height:460px;overflow:auto;margin:0;padding:18px;background:#f4f7f0;border-top:1px solid #e6eddd}.code{background:#f1f5ed;border-radius:7px;padding:18px;font-size:13px}.long-text{font-size:15px;line-height:2.1;padding:0 0 0 18px;border-left:3px solid #c5d7b7;overflow-wrap:anywhere}.flow{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:26px}.flow a{display:block;border:1px solid #d6e2cc;border-radius:6px;padding:14px 16px;text-decoration:none;flex:1;min-width:180px}.flow b{display:block;font-size:14px;font-weight:500;color:#4b7140}.flow span{display:block;font-size:12px;color:#8b9b7d;margin-top:7px}.image-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}figure{margin:0;background:#f4f6ef;border:1px solid #e0e7d8;border-radius:8px;overflow:hidden}figure img{height:290px;width:100%;object-fit:contain;display:block;cursor:zoom-in}figcaption{font-size:12px;line-height:1.8;text-align:center;padding:10px 12px;color:#75856b;background:#fafbf7}.output-figure{max-width:570px;margin:0 auto 28px}.output-figure img{height:600px}.download-row{display:flex;gap:13px;flex-wrap:wrap;align-items:center;margin-bottom:24px}.download-row a{font-size:13px}.field-search{display:flex;align-items:center;gap:15px;font-size:14px;margin:20px 0}.field-search input{flex:1;border:1px solid #ccd9c3;border-radius:6px;padding:12px;font:inherit;font-size:13px}.field-result{padding:13px 0;border-bottom:1px solid #e5ebdf;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px}.field-result code{font:12px Consolas,monospace;color:#4e6c42;overflow-wrap:anywhere}.field-result small{display:block;font-size:12px;color:#7a8b6d;margin-top:7px;line-height:1.8;overflow-wrap:anywhere}.index-count{font-size:12px;color:#98a88a}dialog{max-width:min(1100px,90vw);width:90vw;max-height:90vh;border:0;border-radius:12px;padding:25px;box-shadow:0 20px 90px #0005}dialog::backdrop{background:#142318c9}dialog pre{max-height:70vh;overflow:auto}dialog img{max-width:100%;max-height:78vh;display:block;margin:auto}.modal-head{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:18px}.modal-head h3{margin:0;font-size:16px;overflow-wrap:anywhere}footer{text-align:center;color:#88977b;font-size:12px;padding:20px}.hero-meta{display:flex;gap:12px;flex-wrap:wrap;margin-top:22px}.hero-meta span{font-size:12px;color:#648353;border:1px solid #d7e3cd;border-radius:5px;padding:7px 10px}.skip{position:absolute;left:-10000px}.skip:focus{position:static}@media(max-width:950px){.layout{grid-template-columns:1fr}nav{position:static;max-height:none}nav a{display:inline-block}header{padding:25px}.image-grid{grid-template-columns:1fr}figure img{height:300px}}@media print{body{background:#fff}header{padding:0;border:0}.layout{display:block;padding:0}nav,details,.download-row,.field-search,#field-results,.hero-meta,button,footer{display:none!important}section{border:0;padding:0;margin:30px 0;break-inside:auto}h2,h3{break-after:avoid}tr,figure{break-inside:avoid}.flow a{border:1px solid #ccc}.output-figure img{height:400px}figure img{height:230px}a{color:#000;text-decoration:none}.table-wrap{overflow:visible}table{font-size:11px}th,td{padding:7px}p{font-size:12px;line-height:1.8}}
</style></head><body><a class="skip" href="#overview">跳到正文</a>'''
header='<header><h1>智慧衣橱一次真实任务完整数据流</h1><p>从真实对话和衣橱数据，到 DeepSeek 规划、Seedream 生图、视觉检查与私有图片展示。逐项查看输入、转换、输出和证据边界。</p><p>任务 '+esc(j['id'])+'　执行于 '+localtime(j['created_at'])+'　导出于 '+esc(s['exported_at_utc'])+'</p><div class="hero-meta"><span>真实业务记录</span><span>3 张参考图哈希一致</span><span>1 次实际生图</span><span>未新增模型调用</span></div></header>'
embedded=json.dumps({'snapshot':s,'views':views},ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
script='''<script id="evidence-data" type="application/json">'''+embedded+'''</script><dialog id="detail-modal"><div class="modal-head"><h3 id="modal-title"></h3><button id="close-modal">关闭</button></div><div id="modal-content"></div></dialog><script>
const DATA=JSON.parse(document.getElementById('evidence-data').textContent),modal=document.getElementById('detail-modal');
function compact(value,key=''){if(typeof value==='string'&&(key==='base64'||value.startsWith('data:image/'))){return '[完整图像编码 '+value.length+' 字符；勾选显示完整图片编码或下载 JSON 查看]'}if(Array.isArray(value))return value.map(v=>compact(v));if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,compact(v,k)]));return value}
function json(value){return JSON.stringify(value,null,2)}
function download(value,name){const url=URL.createObjectURL(new Blob([json(value)],{type:'application/json;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),3000)}
document.querySelectorAll('pre[data-view]').forEach(el=>el.textContent=json(compact(DATA.views[el.dataset.view].value)));
document.querySelectorAll('[data-binary]').forEach(input=>input.addEventListener('change',()=>{const record=DATA.views[input.dataset.binary];document.querySelector('pre[data-view="'+input.dataset.binary+'"]').textContent=json(input.checked?record.value:compact(record.value))}));
document.querySelectorAll('[data-download]').forEach(button=>button.addEventListener('click',()=>download(DATA.views[button.dataset.download].value,button.dataset.download+'.json')));
document.getElementById('download-all').onclick=()=>download(DATA.snapshot,'wardrobe-real-task-evidence.json');
document.getElementById('download-render-request').onclick=()=>{const request=structuredClone(DATA.snapshot.reconstructed_seedream_request);request.body.image=request.body.image.map(ref=>{const a=DATA.snapshot.assets[ref.$asset_data_uri];return 'data:'+a.mime+';base64,'+a.base64});download(request,'seedream-request-reconstructed-full-images.json')};
document.getElementById('close-modal').onclick=()=>modal.close();modal.addEventListener('click',e=>{if(e.target===modal)modal.close()});
document.querySelectorAll('[data-enlarge]').forEach(image=>image.addEventListener('click',()=>{document.getElementById('modal-title').textContent=image.alt;const content=document.getElementById('modal-content');content.replaceChildren();const img=document.createElement('img');img.src=image.src;img.alt=image.alt;content.append(img);modal.showModal()}));
const leaves=[];function walk(v,path){if(v&&typeof v==='object'){for(const[k,value]of Object.entries(v))walk(value,path?path+'.'+k:k);if(!Object.keys(v).length)leaves.push({path,value:v})}else leaves.push({path,value:v})}walk(DATA.snapshot,'');
function renderFields(){const query=document.getElementById('field-query').value.trim().toLowerCase(),root=document.getElementById('field-results');root.replaceChildren();const matches=leaves.filter(item=>item.path.toLowerCase().includes(query)||(!item.path.endsWith('.base64')&&typeof item.value==='string'&&item.value.length<5000&&item.value.toLowerCase().includes(query)));const count=document.createElement('p');count.className='index-count';count.textContent='共 '+leaves.length+' 个叶子字段；匹配 '+matches.length+' 个；显示前 '+Math.min(matches.length,100)+' 个。完整数据均在 JSON 中。';root.append(count);if(!query)return;for(const item of matches.slice(0,100)){const row=document.createElement('div');row.className='field-result';const body=document.createElement('div'),path=document.createElement('code'),value=document.createElement('small'),button=document.createElement('button');path.textContent=item.path;const text=json(item.value);value.textContent=text.length>160?text.slice(0,160)+' [预览截断，点完整值]':text;body.append(path,value);button.textContent='完整值';button.onclick=()=>{document.getElementById('modal-title').textContent=item.path;const pre=document.createElement('pre');pre.textContent=json(item.value);document.getElementById('modal-content').replaceChildren(pre);modal.showModal()};row.append(body,button);root.append(row)}}document.getElementById('field-query').addEventListener('input',renderFields);renderFields();
</script></body></html>'''
report=OUT/'智慧衣橱真实任务数据流.html'
report.write_text(html_head+header+'<div class="layout"><nav aria-label="文档目录"><strong>数据流目录</strong>'+toc+'</nav><main>'+''.join(item[2] for item in sections)+'</main></div><footer>本地私有资料　鉴权信息已脱敏　数据来源与缺口均在正文中标注</footer>'+script,encoding='utf-8')
files=[OUT/'snapshot.json',report,*asset_folder.iterdir()]
manifest={'job_id':j['id'],'files':[{'path':str(f.relative_to(OUT)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in files]}
(OUT/'manifest.json').write_text(dump(manifest),encoding='utf-8')
assert len(s['reference_integrity'])==3 and all(e['matches'] for e in s['reference_integrity'])
assert len(views)>=25
assert j['result']['attempts']==1 and all(review_checks[k] for k in ('person_preserved','body_shape_preserved','garments_preserved','pose_preserved','no_artifacts'))
print(dump({'report':str(report),'sections':len(sections),'json_blocks':len(views),'html_bytes':report.stat().st_size,'assets':len(s['assets'])}))
