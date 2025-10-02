import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        tid = request.headers.get('x-trace-id') or str(uuid.uuid4())
        try: 
            uuid.UUID(tid)
        except ValueError: 
            tid = str(uuid.uuid4())
        request.state.trace_id = tid
        request.state.span_id = str(uuid.uuid4())
        resp = await call_next(request)
        resp.headers['x-trace-id']=tid
        resp.headers['x-span-id']=request.state.span_id
        return resp
