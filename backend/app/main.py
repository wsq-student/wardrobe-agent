from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import io
import jwt
from pwdlib import PasswordHash
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from .core import settings, session, User, Item, Conversation, Recommendation, Job, Feedback
from . import storage
from .tasks import enqueue, item_dict
from .agent import CATEGORIES
from .tryon import configured as tryon_configured

passwords = PasswordHash.recommended()


@asynccontextmanager
async def lifespan(app):
    storage.init_bucket()
    yield


app = FastAPI(title='智慧衣橱 Agent', lifespan=lifespan, docs_url='/api/docs', openapi_url='/api/openapi.json')


def db_session():
    with session() as db:
        yield db


def current_user(request: Request, db=Depends(db_session)):
    token = request.cookies.get('session', '')
    try:
        payload = jwt.decode(token, settings().jwt_secret, algorithms=['HS256'])
        user = db.get(User, int(payload['sub']))
        if not user:
            raise ValueError()
        return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, '请先登录')


def owned(db, cls, ident, user):
    row = db.get(cls, ident)
    if not row or row.user_id != user.id:
        raise HTTPException(404, '记录不存在')
    return row


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=8, max_length=128)


def login_response(response, user):
    token = jwt.encode({'sub': str(user.id), 'exp': datetime.now(timezone.utc) + timedelta(days=7)},
                       settings().jwt_secret, algorithm='HS256')
    response.set_cookie('session', token, httponly=True, secure=settings().cookie_secure,
                        samesite='strict', max_age=604800)
    return {'id': user.id, 'email': user.email, 'profile': user.profile}


@app.post('/api/auth/register')
def register(data: Credentials, response: Response, db=Depends(db_session)):
    user = User(email=data.email.lower(), password=passwords.hash(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '邮箱已注册')
    return login_response(response, user)


@app.post('/api/auth/login')
def login(data: Credentials, response: Response, db=Depends(db_session)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not passwords.verify(data.password, user.password):
        raise HTTPException(401, '邮箱或密码错误')
    return login_response(response, user)


@app.post('/api/auth/logout')
def logout(response: Response):
    response.delete_cookie('session')
    return {'ok': True}


@app.get('/api/me')
def me(user=Depends(current_user)):
    return {'id': user.id, 'email': user.email, 'profile': user.profile}


class Profile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    height_cm: float | None = Field(None, ge=80, le=250)
    size: str = Field('', max_length=30)
    preferences: str = Field('', max_length=1000)
    city: str = Field('', max_length=100)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    daily_enabled: bool = False
    daily_hour: int = Field(7, ge=0, le=23)


@app.put('/api/profile')
def profile(data: Profile, user=Depends(current_user), db=Depends(db_session)):
    user.profile = {**data.model_dump(), 'photo_key': user.profile.get('photo_key')}
    db.commit()
    return user.profile


@app.get('/api/locations')
def locations(q: str, user=Depends(current_user)):
    import httpx
    if not 2 <= len(q) <= 100:
        raise HTTPException(422, '请输入 2–100 个字符的城市名称')
    try:
        response = httpx.get('https://geocoding-api.open-meteo.com/v1/search',
            params={'name': q, 'count': 8, 'language': 'zh', 'format': 'json'}, timeout=12)
        response.raise_for_status()
        return [{k: r.get(k) for k in ('name', 'country', 'admin1', 'latitude', 'longitude')}
                for r in response.json().get('results', [])]
    except httpx.HTTPError:
        raise HTTPException(503, '城市查询暂不可用，可手动填写坐标')


def upload(user_id, file):
    try:
        return storage.save_image(user_id, file.file.read(12 * 1024 * 1024 + 1))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post('/api/profile/photo')
def profile_photo(file: UploadFile = File(...), user=Depends(current_user), db=Depends(db_session)):
    key = upload(user.id, file)
    old = user.profile.get('photo_key')
    user.profile = {**user.profile, 'photo_key': key}
    db.commit()
    storage.delete(old)
    return user.profile


@app.delete('/api/profile/photo')
def remove_photo(user=Depends(current_user), db=Depends(db_session)):
    key = user.profile.get('photo_key')
    user.profile = {**user.profile, 'photo_key': None}
    db.commit()
    storage.delete(key)
    return {'ok': True}


@app.get('/api/media/{key:path}')
def media(key: str, user=Depends(current_user)):
    if not key.startswith(f'{user.id}/'):
        raise HTTPException(404)
    try:
        data = storage.read(key)
    except Exception:
        raise HTTPException(404, '图片不存在')
    return StreamingResponse(io.BytesIO(data), media_type='image/jpeg', headers={'Cache-Control': 'private, no-store'})


@app.get('/api/items')
def items(user=Depends(current_user), db=Depends(db_session)):
    return [item_dict(i) for i in db.scalars(select(Item).where(Item.user_id == user.id).order_by(Item.id.desc()))]


@app.post('/api/items')
def create_item(file: UploadFile = File(...), user=Depends(current_user), db=Depends(db_session)):
    key = upload(user.id, file)
    item = Item(user_id=user.id, name='新衣物', image_key=key)
    db.add(item)
    db.commit()
    job = enqueue(db, user.id, 'classify', {'item_id': item.id})
    return {'item': item_dict(item), 'job_id': job.id}


class ItemUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str
    color: str = Field('', max_length=80)
    season: list[str] = Field(default_factory=list, max_length=4)
    status: str


@app.put('/api/items/{item_id}')
def update_item(item_id: int, data: ItemUpdate, user=Depends(current_user), db=Depends(db_session)):
    item = owned(db, Item, item_id, user)
    if data.category not in CATEGORIES or data.status not in ('available', 'washing', 'unavailable'):
        raise HTTPException(422, '衣物分类或状态不合法')
    for k, v in data.model_dump().items():
        setattr(item, k, v)
    db.commit()
    return item_dict(item)


@app.post('/api/items/{item_id}/classify')
def reclassify(item_id: int, user=Depends(current_user), db=Depends(db_session)):
    owned(db, Item, item_id, user)
    return {'job_id': enqueue(db, user.id, 'classify', {'item_id': item_id}).id}


@app.delete('/api/items/{item_id}')
def remove_item(item_id: int, user=Depends(current_user), db=Depends(db_session)):
    item = owned(db, Item, item_id, user)
    key = item.image_key
    db.delete(item)
    db.commit()
    storage.delete(key)
    return {'ok': True}


@app.get('/api/conversations')
def conversations(user=Depends(current_user), db=Depends(db_session)):
    return [{'id': c.id, 'messages': c.messages} for c in db.scalars(select(Conversation).where(
        Conversation.user_id == user.id).order_by(Conversation.id.desc()).limit(30))]


class Prompt(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None


@app.post('/api/recommend')
def create_recommendation(data: Prompt, user=Depends(current_user), db=Depends(db_session)):
    if not settings().deepseek_api_key:
        raise HTTPException(503, '请配置 DEEPSEEK_API_KEY 后启用智能推荐')
    if data.conversation_id:
        conv = owned(db, Conversation, data.conversation_id, user)
    else:
        conv = Conversation(user_id=user.id)
        db.add(conv)
        db.commit()
    running = list(db.scalars(select(Job).where(Job.user_id == user.id, Job.status.in_(['queued', 'running']), Job.kind == 'recommend')))
    if any(j.payload.get('conversation_id') == conv.id for j in running):
        raise HTTPException(409, '本会话的上一个推荐任务正在运行')
    job = enqueue(db, user.id, 'recommend', {'conversation_id': conv.id, 'prompt': data.prompt})
    return {'job_id': job.id, 'conversation_id': conv.id}


@app.get('/api/recommendations')
def recommendations(user=Depends(current_user), db=Depends(db_session)):
    return [{'id': r.id, 'conversation_id': r.conversation_id, 'created_at': r.created_at, **r.data}
            for r in db.scalars(select(Recommendation).where(Recommendation.user_id == user.id).order_by(Recommendation.id.desc()).limit(30))]


class Tryon(BaseModel):
    recommendation_id: int
    consent: bool


@app.post('/api/tryon')
def tryon(data: Tryon, user=Depends(current_user), db=Depends(db_session)):
    owned(db, Recommendation, data.recommendation_id, user)
    if not data.consent:
        raise HTTPException(422, '请确认使用个人照片生成试衣预览')
    if not user.profile.get('photo_key'):
        raise HTTPException(422, '请先上传全身照')
    if not tryon_configured():
        raise HTTPException(503, '请配置 DEEPSEEK_API_KEY 与 ARK_API_KEY，开通 Seedream 图片模型后启用试衣')
    return {'job_id': enqueue(db, user.id, 'tryon', data.model_dump()).id}


class Rating(BaseModel):
    recommendation_id: int
    rating: int = Field(ge=1, le=5)
    comment: str = Field('', max_length=500)


@app.post('/api/feedback')
def feedback(data: Rating, user=Depends(current_user), db=Depends(db_session)):
    owned(db, Recommendation, data.recommendation_id, user)
    db.add(Feedback(user_id=user.id, **data.model_dump()))
    db.commit()
    return {'ok': True}


@app.get('/api/jobs')
def jobs(user=Depends(current_user), db=Depends(db_session)):
    return [job_data(j) for j in db.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc()).limit(30))]


def job_data(j):
    return {**{k: getattr(j, k) for k in ('id', 'kind', 'status', 'result', 'error', 'trace', 'created_at')},
            'conversation_id': j.payload.get('conversation_id'),
            'recommendation_id': j.payload.get('recommendation_id'),
            'request_text': j.payload.get('prompt') if j.kind == 'recommend' else None}


@app.get('/api/jobs/{job_id}')
def job(job_id: str, user=Depends(current_user), db=Depends(db_session)):
    return job_data(owned(db, Job, job_id, user))


@app.delete('/api/jobs/{job_id}')
def delete_job(job_id: str, user=Depends(current_user), db=Depends(db_session)):
    j = owned(db, Job, job_id, user)
    if j.status in ('queued', 'running'):
        raise HTTPException(409, '请等待任务结束后删除')
    key = j.result.get('image_key')
    db.delete(j)
    db.commit()
    storage.delete(key)
    return {'ok': True}


@app.post('/api/jobs/{job_id}/retry')
def retry_job(job_id: str, user=Depends(current_user), db=Depends(db_session)):
    j = owned(db, Job, job_id, user)
    if j.status != 'failed':
        raise HTTPException(409, '仅失败任务可以重试')
    if j.kind == 'classify':
        owned(db, Item, j.payload['item_id'], user)
    if j.kind == 'tryon':
        owned(db, Recommendation, j.payload['recommendation_id'], user)
        if not tryon_configured():
            raise HTTPException(503, '请先配置 DeepSeek 与火山方舟密钥')
    return {'job_id': enqueue(db, user.id, j.kind, j.payload).id}


@app.get('/api/health')
def health(db=Depends(db_session)):
    import redis
    db.execute(text('SELECT 1'))
    redis.Redis.from_url(settings().redis_url).ping()
    storage.client().head_bucket(Bucket=settings().s3_bucket)
    return {'status': 'ok', 'deepseek_configured': bool(settings().deepseek_api_key),
            'tryon_configured': tryon_configured(), 'tryon_status': 'ready' if tryon_configured() else 'credentials_required',
            'tryon_max_attempts': settings().tryon_max_attempts}
