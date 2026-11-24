"""Read-only private task evidence export. Never invokes any model or weather API."""
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from sqlalchemy import select
from sqlalchemy.engine import make_url
import redis
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from app.core import session,settings,Job,User,Item,Recommendation,Conversation,Feedback
from app import storage,tryon,agent

TARGET='81fe2758-0edf-46f5-b3db-33055649bb4c'
def row(obj,exclude=()):
    if obj is None:return None
    return {c.name:getattr(obj,c.name) for c in obj.__table__.columns if c.name not in exclude}
def default(obj):
    if isinstance(obj,datetime):return obj.isoformat()
    raise TypeError(type(obj).__name__)
def endpoint(url):
    v=urlsplit(url)
    return v.scheme+'://'+str(v.hostname)+(':'+str(v.port) if v.port else '')+v.path

assets={}
def asset(key):
    if key in assets:return assets[key]
    try:
        data=storage.read(key)
        with Image.open(io.BytesIO(data)) as im:width,height,fmt=im.width,im.height,im.format
        result={'key':key,'available':True,'mime':'image/'+('jpeg' if fmt=='JPEG' else fmt.lower()),'bytes':len(data),'width':width,'height':height,'sha256':hashlib.sha256(data).hexdigest(),'base64':base64.b64encode(data).decode()}
    except Exception as exc:
        result={'key':key,'available':False,'error_type':type(exc).__name__}
    assets[key]=result
    return result

s=settings()
with session() as db:
    task=db.get(Job,TARGET)
    assert task and task.kind=='tryon' and task.status=='completed'
    user=db.get(User,task.user_id)
    rec=db.get(Recommendation,task.payload['recommendation_id'])
    conv=db.get(Conversation,rec.conversation_id)
    items=list(db.scalars(select(Item).where(Item.user_id==user.id).order_by(Item.id)))
    by_id={i.id:i for i in items}
    selected=[by_id[i] for i in rec.data['item_ids'] if i in by_id]
    user_jobs=list(db.scalars(select(Job).where(Job.user_id==user.id).order_by(Job.created_at)))
    parent=next((j for j in user_jobs if j.kind=='recommend' and j.result.get('recommendation_id')==rec.id),None)
    classifications=[j for j in user_jobs if j.kind=='classify' and j.payload.get('item_id') in rec.data['item_ids']]
    feedback=list(db.scalars(select(Feedback).where(Feedback.user_id==user.id).order_by(Feedback.id.desc()).limit(10)))
    plan=next(t for t in task.trace if t['stage']=='tryon_plan')
    for i in items:asset(i.image_key)
    photo=asset(user.profile['photo_key']) if user.profile.get('photo_key') else None
    output=asset(task.result['image_key'])
    reference_keys=([user.profile['photo_key']] if photo else [])+[i.image_key for i in selected]
    expected=plan.get('reference_hashes',[])
    hashes=[{'position':n+1,'key':key,'current_sha256':asset(key).get('sha256'),'recorded_sha256':expected[n] if n<len(expected) else None,'matches':asset(key).get('sha256')==(expected[n] if n<len(expected) else None)} for n,key in enumerate(reference_keys)]
    history=None
    if conv and parent:
        for index,m in enumerate(conv.messages):
            if m.get('role')=='assistant':
                try:matches=json.loads(m['content'])==rec.data
                except (ValueError,TypeError):matches=False
                if matches and index and conv.messages[index-1].get('content')==parent.payload.get('prompt'):
                    history=conv.messages[:index-1]
                    break
    weather_snapshot=None
    if user.profile.get('latitude') is not None and user.profile.get('longitude') is not None:
        key=f"weather:{user.profile['latitude']:.2f}:{user.profile['longitude']:.2f}"
        cache=redis.Redis.from_url(s.redis_url,decode_responses=True)
        value=cache.get(key)
        weather_snapshot={'key':key,'ttl_seconds_at_export':cache.ttl(key),'current_cached_value':json.loads(value) if value else None,'historical_execution_value_proven':False}
    snapshot={'exported_at_utc':datetime.now(timezone.utc).isoformat(),'target_job':row(task),'recommendation_job':row(parent),'recommendation':row(rec),'conversation_current':row(conv),'history_before_recommendation_inferred':history,'user_current':row(user,exclude=('password',)),'wardrobe_current':[row(i) for i in items],'selected_item_ids':rec.data['item_ids'],'classification_jobs':[row(j) for j in classifications],'feedback_current':[row(f) for f in feedback],'reference_integrity':hashes,'weather_cache_at_export':weather_snapshot}
    # Reconstruct message *templates* locally with a recording substitute, never an API call.
    captures=[]
    fixed='使用图1中的同一个人，保持原身材比例、脸部外观、姿势、构图与背景，穿上后续参考图中的全部单品。保留各单品颜色、版型与图案，不新增无关单品。'
    parsed_plan=plan['prompt'][len(fixed):] if plan['prompt'].startswith(fixed) else None
    review=task.result['review']
    class Recorder:
        def bind(self,**kwargs):self.options=kwargs;return self
        def invoke(self,messages):
            captures.append({'bind_options':self.options,'messages':[{'role':{'human':'user','ai':'assistant'}.get(m.type,m.type),'content':m.content} for m in messages]})
            return AIMessage(content=json.dumps({'prompt':parsed_plan} if len(captures)==1 else review,ensure_ascii=False))
    if photo and all(asset(k)['available'] for k in reference_keys) and parsed_plan and len(selected)==len(rec.data['item_ids']):
        person=base64.b64decode(photo['base64'])
        garments=[{**row(i),'image':base64.b64decode(asset(i.image_key)['base64'])} for i in selected]
        with patch.object(tryon,'model',lambda:Recorder()):
            tryon.plan_prompt(person,garments,user.profile)
            if output['available']:tryon.review_image(person,garments,base64.b64decode(output['base64']))
    snapshot['reconstructed_deepseek_calls']=captures
    snapshot['parsed_plan_derived_from_recorded_prompt']={'prompt':parsed_plan}
    class ProbeComplete(Exception):pass
    class RecommendationProbe:
        def bind_tools(self,tools):self.tools=tools;return self
        def invoke(self,messages):
            snapshot['recommendation_initial_messages_reconstructed']=[{'role':{'human':'user','ai':'assistant'}.get(m.type,m.type),'content':m.content} for m in messages]
            snapshot['recommendation_tool_definitions_current']=[convert_to_openai_tool(t) for t in self.tools]
            snapshot['recommendation_tool_results_current']={t.name:t.invoke({}) for t in self.tools}
            raise ProbeComplete()
    if parent and history is not None:
        wardrobe=[{k:getattr(i,k) for k in ('id','name','category','color','season','status','image_key','tags')} for i in items]
        with patch.object(agent,'model',lambda:RecommendationProbe()),patch.object(agent,'weather',lambda *args:weather_snapshot['current_cached_value'] if weather_snapshot and weather_snapshot['current_cached_value'] else {'not_recorded':True}):
            try:agent.recommend(parent.payload['prompt'],history,wardrobe,user.profile,[{'rating':f.rating,'comment':f.comment} for f in feedback],lambda e:None)
            except ProbeComplete:pass
    snapshot['reconstructed_seedream_request']={'method':'POST','url':endpoint(s.ark_base_url).rstrip('/')+'/images/generations','headers':{'Authorization':'Bearer [REDACTED]','Content-Type':'application/json'},'body':{'model':task.result['renderer'],'prompt':plan['prompt'],'image':[{'$asset_data_uri':k} for k in reference_keys],'size':'2K','response_format':'url','stream':False,'watermark':True},'provenance':'Reconstructed from recorded prompt/model/reference hashes and implementation, not an archived HTTP request'}
    snapshot['model_transport_configuration_now']={'controller':s.deepseek_model,'controller_base_url':endpoint(s.deepseek_base_url),'temperature':0.3,'thinking':{'type':'disabled'},'timeout_seconds':90,'sdk_max_retries':2,'structured_max_tokens':1800,'renderer':s.ark_image_model,'renderer_base_url':endpoint(s.ark_base_url),'response_format':s.ark_response_format,'render_timeout_seconds':240,'render_connect_timeout_seconds':15,'download_timeout_seconds':60,'max_attempts':s.tryon_max_attempts,'graph_phase_budget_seconds':900,'graph_recursion_limit':20}
    u=make_url(s.database_url)
    snapshot['infrastructure_now']={'mysql':{'host':u.host,'port':u.port or 3306,'database':u.database,'username':u.username,'password':'[REDACTED]'},'redis':endpoint(s.redis_url),'s3':{'endpoint':endpoint(s.s3_endpoint),'bucket':s.s3_bucket,'access_key':'[REDACTED]','secret_key':'[REDACTED]'},'authentication':{'cookie_name':'session','cookie_value':'[NOT EXPORTED]','jwt_secret':'[REDACTED]','owner_user_id':user.id}}
    snapshot['assets']=assets
    paths=['app/main.py','app/core.py','app/agent.py','app/tryon.py','app/tasks.py','app/storage.py','app/provider_errors.py']
    sources={}
    for path in paths:
        data=Path('/app',path).read_bytes()
        sources[path]={'sha256':hashlib.sha256(data).hexdigest(),'content':data.decode('utf-8-sig')}
    snapshot['source_snapshot_current']=sources
    text=json.dumps(snapshot,ensure_ascii=False,default=default)
    for secret in (s.deepseek_api_key,s.ark_api_key,s.jwt_secret,s.s3_secret_key,u.password):
        if secret and secret in text:raise RuntimeError('Secret export guard failed')
    print(text)
