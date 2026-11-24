"""Exercise the real graph with deterministic model/provider substitutes."""
import base64
import io
from types import SimpleNamespace
import pytest
import httpx
from PIL import Image
from app import tryon


def review(passed):
    return tryon.Review(person_preserved=passed, body_shape_preserved=True, garments_preserved=True,
        pose_preserved=True, no_artifacts=True, issues=[] if passed else ['人物外观漂移'],
        repair_instructions='' if passed else '保持图1人物外观')


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(tryon, 'configured', lambda: True)
    monkeypatch.setattr(tryon, 'settings', lambda: SimpleNamespace(tryon_max_attempts=2))
    monkeypatch.setattr(tryon, 'plan_prompt', lambda *args: '图1人物穿图2上衣与图3裤子')
    references = []
    def render(prompt, images):
        references.append(list(images))
        return b'candidate'
    monkeypatch.setattr(tryon, 'render_seedream', render)
    return references


def test_review_failure_repairs_and_reuses_original_references(harness, monkeypatch):
    checks = iter([review(False), review(True)])
    monkeypatch.setattr(tryon, 'review_image', lambda *args: next(checks))
    trace = []
    result = tryon.run_harness(b'person', [{'id': 1, 'image': b'shirt'}], {}, trace.append)
    assert result['attempts'] == 2
    assert result['image'] == b'candidate'
    assert harness == [[b'person', b'shirt'], [b'person', b'shirt']]
    assert [t['stage'] for t in trace] == ['tryon_plan','tryon_render','tryon_review','tryon_repair','tryon_render','tryon_review']


def test_failed_images_never_pass_as_success(harness, monkeypatch):
    monkeypatch.setattr(tryon, 'review_image', lambda *args: review(False))
    with pytest.raises(ValueError, match='2 次生成预算'):
        tryon.run_harness(b'person', [{'id':1,'image':b'shirt'}], {}, lambda _: None)
    assert len(harness) == 2


def test_provider_errors_are_not_implicitly_retried(harness, monkeypatch):
    calls = []
    def fail(*args):
        calls.append(1)
        raise TimeoutError('provider timeout')
    monkeypatch.setattr(tryon, 'render_seedream', fail)
    with pytest.raises(TimeoutError):
        tryon.run_harness(b'person', [{'id':1,'image':b'shirt'}], {}, lambda _: None)
    assert len(calls) == 1


def test_seedream_adapter_sends_multireference_and_decodes_png(monkeypatch):
    output = io.BytesIO()
    Image.new('RGB', (512,768)).save(output, 'PNG')
    image = output.getvalue()
    s = SimpleNamespace(ark_api_key='test-only',ark_base_url='https://ark.test/api/v3',ark_image_model='model-test',ark_response_format='b64_json')
    monkeypatch.setattr(tryon, 'settings', lambda: s)
    requests = []
    def respond(request):
        import json
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'data':[{'b64_json':base64.b64encode(image).decode()}]})
    original_client = httpx.Client
    monkeypatch.setattr(tryon.httpx, 'Client', lambda **kwargs: original_client(transport=httpx.MockTransport(respond)))
    assert tryon.render_seedream('试衣', [b'person', b'shirt']) == image
    assert len(requests[0]['image']) == 2
    assert requests[0]['response_format'] == 'b64_json'
    assert requests[0]['watermark'] is True
    assert requests[0]['stream'] is False


def test_seedream_url_response_downloads_without_forwarding_key(monkeypatch):
    output = io.BytesIO()
    Image.new('RGB',(512,768)).save(output,'PNG')
    image=output.getvalue()
    s=SimpleNamespace(ark_api_key='private-test-key',ark_base_url='https://ark.test/api/v3',
        ark_image_model='doubao-seedream-5-0-flash-260915',ark_response_format='url')
    monkeypatch.setattr(tryon,'settings',lambda:s)
    def respond(request):
        import json
        if request.method=='POST':
            payload=json.loads(request.content)
            assert payload['model']==s.ark_image_model
            assert payload['response_format']=='url' and payload['stream'] is False
            assert len(payload['image'])==2
            return httpx.Response(200,json={'data':[{'url':'https://example.tos-cn-beijing.volces.com/image.png?signature=test'}]})
        assert 'authorization' not in request.headers
        return httpx.Response(200,content=image)
    original_client=httpx.Client
    monkeypatch.setattr(tryon.httpx,'Client',lambda **kwargs: original_client(transport=httpx.MockTransport(respond)))
    assert tryon.render_seedream('试衣',[b'person',b'shirt'])==image


def test_configured_requires_both_models(monkeypatch):
    monkeypatch.setattr(tryon, 'settings', lambda: SimpleNamespace(deepseek_api_key='test', ark_api_key=''))
    assert not tryon.configured()
