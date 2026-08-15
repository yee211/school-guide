class LLMServiceError(Exception):
    """模型服务基础异常。"""


class LLMAuthenticationError(LLMServiceError):
    """模型服务鉴权失败。"""


class LLMTimeoutError(LLMServiceError):
    """模型请求超时。"""


class LLMConnectionError(LLMServiceError):
    """无法连接模型服务。"""


class LLMEmptyResponseError(LLMServiceError):
    """模型返回空内容。"""


class LLMProviderError(LLMServiceError):
    """模型供应商返回其他错误。"""