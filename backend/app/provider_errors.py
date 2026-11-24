"""Safe provider diagnostics: never include request bodies, keys, or image URLs."""
import re
import httpx


class ProviderError(ValueError):
    def __init__(self, message, provider, status, code):
        super().__init__(message)
        self.diagnostics = {'provider': provider, 'http_status': status, 'code': code}


def check_response(response, provider='豆包'):
    if response.is_success:
        return
    try:
        error = response.json().get('error', {})
        raw_code = error.get('code', '') if isinstance(error, dict) else ''
    except (ValueError, AttributeError):
        raw_code = ''
    code = str(raw_code)[:120]
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', code):
        code = 'Unknown'
    status = response.status_code
    if code == 'ModelNotOpen':
        reason = '当前账号尚未开通该图片模型，请在火山方舟开通，或设置已开通的 ARK_IMAGE_MODEL'
    elif code.endswith('ModelIDAccessDisabled'):
        reason = '账号不允许通过模型 ID 调用，请将 ARK_IMAGE_MODEL 设置为有权限的推理接入点 ID'
    else:
        reason = {400:'请求参数或图片不符合模型要求',401:'密钥无效或已过期',402:'账户余额或额度不足',
                  403:'没有该模型的调用权限，请检查密钥所属项目与授权',
                  404:'模型或推理接入点不可调用，请检查开通状态、密钥权限和 ARK_IMAGE_MODEL',
                  429:'请求达到限流或额度限制，请稍后重试'}.get(status, '服务暂时不可用，请稍后重试')
    raise ProviderError(f'{provider}请求失败（HTTP {status}，{code}）：{reason}', provider, status, code)


def describe_failure(exc):
    if isinstance(exc, ProviderError):
        return str(exc), exc.diagnostics
    if isinstance(exc, httpx.TimeoutException):
        return '外部模型请求超时，请稍后重试', {'code':'ProviderTimeout'}
    if isinstance(exc, httpx.RequestError):
        return '无法连接外部模型，请检查网络后重试', {'code':'ProviderConnectionError'}
    # Pydantic exceptions inherit ValueError and may embed sensitive inputs.
    from pydantic import ValidationError
    if isinstance(exc, ValidationError):
        return '模型输出未通过结构校验，请重试', {'code':'InvalidModelOutput'}
    if isinstance(exc, ValueError):
        return str(exc)[:300], {'code':'ValidationFailed'}
    return '任务执行失败，请查看执行阶段并稍后重试', {'code':type(exc).__name__}
