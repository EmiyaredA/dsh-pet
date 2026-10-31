"""Allowlisted submission error evidence, without response/request headers."""
import re
from urllib.parse import urlsplit, urlunsplit


def _safe_text(value, limit=2000):
    text=str(value)
    text=re.sub(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+','Bearer [REDACTED]',text)
    text=re.sub(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|csrf[_-]?token|token|secret|password|authorization|cookie|set-cookie)\b\s*[:=]\s*(?:([\"']).*?\2|[^\s,;]+)",
                lambda m:m.group(1)+'=[REDACTED]',text)
    def clean_url(match):
        parsed=urlsplit(match.group(0))
        return urlunsplit((parsed.scheme,parsed.netloc.rsplit('@',1)[-1],parsed.path,'',''))
    text=re.sub(r'https?://[^\s<>"\']+',clean_url,text)
    return text[:limit]


def safe_submission_error(exc):
    # ApiError uses .status, not httpx's .response.status_code. Never serialize
    # .problem wholesale: it can contain headers, body snapshots, or credentials.
    status=getattr(exc,'status',None) or getattr(exc,'status_code',None)
    if status is None:status=getattr(getattr(exc,'response',None),'status_code',None)
    if type(status) is not int or not 100<=status<=599:status=None
    problem=getattr(exc,'problem',None)
    nested=problem.get('detail') if isinstance(problem,dict) else None
    nested=nested if isinstance(nested,dict) else {}
    code=getattr(exc,'code',None) or (problem.get('code') if isinstance(problem,dict) else None) or nested.get('code')
    message=(problem.get('message') if isinstance(problem,dict) else None) or nested.get('message')
    if message is None and isinstance(problem,dict) and isinstance(problem.get('detail'),str):message=problem['detail']
    return {'exception_type':type(exc).__name__,'http_status':status,
            'code':_safe_text(code,160) if code else None,'message':_safe_text(message or str(exc)),
            'headers_saved':False,'body_or_current_snapshot_saved':False}
