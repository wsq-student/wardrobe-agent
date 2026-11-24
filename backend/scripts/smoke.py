"""End-to-end API checks without paid provider calls."""
import io
import uuid
import time
import httpx
from PIL import Image

BASE = 'http://api:8000'
output = io.BytesIO()
Image.new('RGB', (80, 100), 'green').save(output, 'JPEG')
image = output.getvalue()
with httpx.Client(base_url=BASE) as a, httpx.Client(base_url=BASE) as b:
    for client in (a, b):
        r = client.post('/api/auth/register', json={'email': f'{uuid.uuid4()}@test.local', 'password': 'SmokeTest123!'})
        assert r.status_code == 200, r.text
    assert a.get('/api/health').status_code == 200
    r = a.post('/api/items', files={'file': ('test.jpg', image, 'image/jpeg')})
    assert r.status_code == 200, r.text
    item = r.json()['item']
    job_id = r.json()['job_id']
    for _ in range(30):
        job = a.get('/api/jobs/' + job_id).json()
        if job['status'] in ('completed', 'failed'):
            break
        time.sleep(0.5)
    assert job['status'] in ('completed', 'failed'), 'Celery worker did not process the upload'
    if not a.get('/api/health').json()['deepseek_configured']:
        assert job['status'] == 'failed' and 'DEEPSEEK_API_KEY' in job['error']
        assert a.post('/api/recommend', json={'prompt':'通勤穿搭'}).status_code == 503
    assert a.get('/api/media/' + item['image_key']).status_code == 200
    assert b.get('/api/media/' + item['image_key']).status_code == 404
    data = dict(name='绿色衬衣', category='tops', color='绿色', season=['春'], status='washing')
    assert a.put(f"/api/items/{item['id']}", json=data).status_code == 200
    assert b.put(f"/api/items/{item['id']}", json=data).status_code == 404
    assert not b.get('/api/items').json()
    assert a.post('/api/profile/photo', files={'file': ('person.jpg', image, 'image/jpeg')}).status_code == 200
    assert a.put('/api/profile', json={'height_cm':170,'size':'M','city':'上海','latitude':31.23,'longitude':121.47}).status_code == 200
    assert a.get('/api/me').json()['profile']['photo_key']
    assert a.delete('/api/profile/photo').status_code == 200
    assert a.post('/api/items', files={'file': ('bad.jpg', b'not an image', 'image/jpeg')}).status_code == 422
    assert a.get('/api/jobs').status_code == 200
    assert a.get('/api/conversations').status_code == 200
    assert a.get('/api/recommendations').status_code == 200
    assert a.delete(f"/api/items/{item['id']}").status_code == 200
    assert a.get('/api/media/' + item['image_key']).status_code == 404
    assert a.post('/api/auth/logout').status_code == 200
    assert a.get('/api/me').status_code == 401
print('PASS: auth, uploads, MySQL persistence, S3 deletion, tenant isolation, profile, Celery execution, history')
