import httpx
import pytest
from app.provider_errors import check_response, ProviderError, describe_failure


@pytest.mark.parametrize('status,code,hint', [(404,'ModelNotOpen','尚未开通'),
    (404,'InvalidEndpointOrModel.NotFound','模型或推理接入点'),
    (404,'InvalidEndpointOrModel.ModelIDAccessDisabled','推理接入点 ID'),
    (401,'AuthenticationError','密钥无效'), (429,'RateLimitExceeded','限流')])
def test_provider_error_is_actionable_without_echoing_sensitive_message(status,code,hint):
    r=httpx.Response(status,json={'error':{'code':code,'message':'secret-key data:image/png;base64,private-image'}})
    with pytest.raises(ProviderError) as info:
        check_response(r)
    message,detail=describe_failure(info.value)
    assert hint in message
    assert detail['http_status']==status
    assert detail['code']==code
    assert 'secret-key' not in message and 'private-image' not in message
