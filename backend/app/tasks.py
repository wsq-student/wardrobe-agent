import uuid
from celery import Celery
from sqlalchemy import select, update
from .core import settings, session, Job, Item, User, Conversation, Recommendation, Feedback
from . import storage
from .agent import classify, recommend, validate_outfit
from .tryon import run_harness
from .provider_errors import describe_failure

celery = Celery('wardrobe', broker=settings().redis_url)
celery.conf.update(task_ignore_result=True, broker_connection_retry_on_startup=True,
    timezone='Asia/Shanghai', task_time_limit=1800, worker_prefetch_multiplier=1,
    beat_schedule={'daily-recommendations': {'task': 'app.tasks.daily', 'schedule': 60.0}})


def enqueue(db, user_id, kind, payload):
    job = Job(id=str(uuid.uuid4()), user_id=user_id, kind=kind, payload=payload)
    db.add(job)
    db.commit()
    try:
        execute.delay(job.id)
    except Exception:
        job.status = 'failed'
        job.error = '任务队列不可用，请稍后重试'
        db.commit()
    return job


def item_dict(item):
    return {k: getattr(item, k) for k in ('id', 'name', 'category', 'color', 'season', 'status', 'image_key', 'tags')}


@celery.task(name='app.tasks.execute')
def execute(job_id):
    with session() as db:
        claimed = db.execute(update(Job).where(Job.id == job_id, Job.status == 'queued').values(status='running'))
        db.commit()
        if not claimed.rowcount:
            return
        job = db.get(Job, job_id)
        def trace(event):
            job.trace = [*job.trace, event]
            db.commit()
        try:
            if job.kind == 'classify':
                item = db.get(Item, job.payload['item_id'])
                if not item:
                    raise ValueError('衣物已被删除')
                tags = classify(item.image_key)
                item.name, item.category, item.color, item.season = (tags[k] for k in ('name', 'category', 'color', 'season'))
                item.tags = tags
                job.result = {'item_id': item.id}
            elif job.kind == 'recommend':
                user = db.get(User, job.user_id)
                conversation = db.get(Conversation, job.payload['conversation_id'])
                items = [item_dict(i) for i in db.scalars(select(Item).where(Item.user_id == user.id))]
                feedback = [{'rating': f.rating, 'comment': f.comment} for f in db.scalars(
                    select(Feedback).where(Feedback.user_id == user.id).order_by(Feedback.id.desc()).limit(10))]
                output = recommend(job.payload['prompt'], conversation.messages, items, user.profile, feedback, trace)
                fresh = [item_dict(i) for i in db.scalars(select(Item).where(Item.user_id == user.id).execution_options(populate_existing=True))]
                errors = validate_outfit(output, fresh)
                if errors:
                    output = {'item_ids': [], 'reason': '生成期间衣橱状态发生变化。',
                              'clarification': '请重新生成，系统将使用最新的可穿衣物。', 'warnings': errors}
                rec = Recommendation(user_id=user.id, conversation_id=conversation.id, data=output)
                db.add(rec)
                db.flush()
                conversation.messages = [*conversation.messages, {'role': 'user', 'content': job.payload['prompt']},
                    {'role': 'assistant', 'content': __import__('json').dumps(output, ensure_ascii=False)}][-40:]
                job.result = {'recommendation_id': rec.id, **output}
            elif job.kind == 'tryon':
                user = db.get(User, job.user_id)
                photo = user.profile.get('photo_key')
                if not photo:
                    raise ValueError('请先上传个人全身照')
                rec = db.get(Recommendation, job.payload['recommendation_id'])
                chosen = [db.get(Item, iid) for iid in rec.data['item_ids']]
                if any(i is None or i.user_id != user.id or i.status != 'available' for i in chosen):
                    raise ValueError('衣物已删除或不可穿，请重新推荐')
                garments = [{**item_dict(i), 'image': storage.read(i.image_key)} for i in chosen]
                result = run_harness(storage.read(photo), garments, user.profile, trace)
                db.refresh(user)
                fresh = [item_dict(i) for i in db.scalars(select(Item).where(Item.user_id == user.id).execution_options(populate_existing=True))]
                if user.profile.get('photo_key') != photo or validate_outfit(rec.data, fresh):
                    raise ValueError('生成期间人物照片或衣橱状态已变化，请重新生成')
                key = storage.save_image(user.id, result['image'])
                job.result = {'image_key': key, 'item_ids': rec.data['item_ids'], 'attempts': result['attempts'],
                    'review': result['review'], 'renderer': settings().ark_image_model,
                    'controller': settings().deepseek_model,
                    'warnings': ['AI 生成效果仅供搭配参考；视觉检查也可能漏检，不能判断真实尺码是否合身。']}
            job.status = 'completed'
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job_id)
            job.status = 'failed'
            job.error, diagnostic = describe_failure(exc)
            diagnostic['stage'] = job.trace[-1].get('stage') if job.trace else 'prepare'
            job.result = {'failure': diagnostic}
            db.commit()


@celery.task(name='app.tasks.daily')
def daily():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    current = datetime.now(ZoneInfo('Asia/Shanghai'))
    with session() as db:
        from .core import now
        db.execute(update(Job).where(Job.status.in_(['queued', 'running']),
            Job.updated_at < now() - timedelta(minutes=40)).values(status='failed', error='任务超时或工作进程中断，请重试'))
        db.commit()
        for user in db.scalars(select(User)):
            p = user.profile
            if not p.get('daily_enabled') or current.hour != p.get('daily_hour', 7):
                continue
            import redis
            cache = redis.Redis.from_url(settings().redis_url)
            if not cache.set(f'daily:{user.id}:{current.date()}', '1', nx=True, ex=90000):
                continue
            conv = Conversation(user_id=user.id)
            db.add(conv)
            db.commit()
            enqueue(db, user.id, 'recommend', {'conversation_id': conv.id, 'prompt': '根据今天的天气和我的偏好推荐日常穿搭'})
