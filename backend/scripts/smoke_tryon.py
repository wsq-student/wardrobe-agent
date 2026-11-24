"""Exercise MySQL + private S3 + actual job/graph code with synthetic model responses.

No paid provider calls are made. This is not evidence of real model image quality.
"""
import io
import uuid
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PIL import Image
from sqlalchemy import delete
from app.core import session, User, Item, Recommendation, Job
from app import storage, tryon, tasks

output = io.BytesIO()
Image.new('RGB', (512, 768), '#2f674d').save(output, 'JPEG')
synthetic = output.getvalue()
keys = []
user_id = None
try:
    with session() as db:
        user = User(email=f'harness-{uuid.uuid4()}@test.local', password='not-a-login-hash')
        db.add(user)
        db.commit()
        user_id = user.id
        for _ in range(3):
            keys.append(storage.save_image(user.id, synthetic))
        user.profile = {'photo_key': keys[0]}
        top = Item(user_id=user.id, name='测试上衣', category='tops', image_key=keys[1])
        bottom = Item(user_id=user.id, name='测试裤子', category='bottoms', image_key=keys[2])
        db.add_all([top, bottom])
        db.flush()
        rec = Recommendation(user_id=user.id, data={'item_ids': [top.id, bottom.id], 'reason': '集成测试'})
        db.add(rec)
        db.flush()
        job = Job(id=str(uuid.uuid4()), user_id=user.id, kind='tryon', payload={'recommendation_id': rec.id, 'consent': True})
        db.add(job)
        db.commit()
        passed = tryon.Review(person_preserved=True, body_shape_preserved=True, garments_preserved=True,
                             pose_preserved=True, no_artifacts=True)
        with patch.object(tryon, 'configured', return_value=True), \
             patch.object(tryon, 'plan_prompt', return_value='保持图1人物外观，穿上图2上衣与图3裤子'), \
             patch.object(tryon, 'render_seedream', return_value=synthetic) as renderer, \
             patch.object(tryon, 'review_image', return_value=passed):
            tasks.execute.run(job.id)
            tasks.execute.run(job.id)  # Duplicate delivery cannot render a second time.
            assert renderer.call_count == 1
        db.refresh(job)
        assert job.status == 'completed', job.error
        assert job.result['attempts'] == 1
        assert [t['stage'] for t in job.trace] == ['tryon_plan', 'tryon_render', 'tryon_review']
        keys.append(job.result['image_key'])
        assert len(storage.read(job.result['image_key'])) > 100
    print('PASS: real job + LangGraph + MySQL traces + private S3 output + duplicate delivery guard (synthetic models)')
finally:
    if user_id:
        with session() as db:
            for cls in (Job, Recommendation, Item):
                db.execute(delete(cls).where(cls.user_id == user_id))
            db.execute(delete(User).where(User.id == user_id))
            db.commit()
    for key in keys:
        storage.delete(key)
