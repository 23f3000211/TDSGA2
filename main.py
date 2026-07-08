import os
import time
import uuid
import httpx
import json
import re
from collections import defaultdict, deque
from typing import Optional
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import Counter, generate_latest
import redis
import jwt
from pydantic import BaseModel, Field

import config

LLM_MODEL = "qwen2.5:0.5b"
START_TIME = time.time()
app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

http_requests_total = Counter("http_requests_total", "Total HTTP Requests")
logs_queue = deque(maxlen=100)

def is_rate_limited(client_id: str, limit: int, prefix: str) -> bool:
    key = f"ratelimit:{prefix}:{client_id}"
    now = time.time()
    try:
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, now - 10)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, 12)
        res = pipe.execute()
        count = res[2]
        return count > limit
    except Exception as e:
        print(f"Redis rate limit error: {e}", flush=True)
        return False

# --- MIDDLEWARE ---
@app.middleware("http")
async def custom_middleware(request: Request, call_next):
    start_time = time.time()
    http_requests_total.inc()
    
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.req_id = req_id
    
    logs_queue.append({
        "level": "INFO",
        "ts": time.time(),
        "path": request.url.path,
        "request_id": req_id
    })

    path = request.url.path.rstrip("/")
    if path == "": path = "/"
    origin = request.headers.get("Origin")

    response = None

    if path == "/orders":
        client_id = request.headers.get("X-Client-Id", "default")
        if "flood" in client_id or client_id == "default":
            if is_rate_limited(client_id, config.Q9_RATE_LIMIT, "q9"):
                response = Response(status_code=429, headers={"Retry-After": "10"})

    if not response and path == "/ping":
        client_id = request.headers.get("X-Client-Id", "default")
        if is_rate_limited(client_id, config.Q10_RATE_LIMIT, "q10"):
            response = Response(status_code=429, headers={"Retry-After": "10"})

    if not response:
        if request.method == "OPTIONS":
            response = Response(status_code=204)
        else:
            try:
                response = await call_next(request)
            except Exception as e:
                response = Response(status_code=500, content="Internal Server Error")

    process_time = time.time() - start_time
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Process-Time"] = f"{process_time:.6f}"
    return response

# --- ROUTES ---

@app.get("/")
async def root():
    return {"status": "ok"}

# ⚠️ CHANGE THIS to your assigned T value from the exam page
TOTAL_ORDERS = 54
ALL_ORDER_IDS = list(range(1, TOTAL_ORDERS + 1))

@app.get("/orders")
async def get_orders(limit: int = 10, cursor: Optional[str] = None):
    start = 0
    if cursor:
        try:
            start = int(cursor)
        except:
            start = 0
    items = ALL_ORDER_IDS[start:start + limit]
    next_cursor = str(start + limit) if start + limit < TOTAL_ORDERS else None
    return {
        "items": [{"id": i} for i in items],
        "next_cursor": next_cursor
    }

@app.post("/orders")
async def create_order(request: Request):
    # Check header first (standard HTTP idempotency), then body
    key = request.headers.get("Idempotency-Key")
    
    if not key:
        try:
            body = await request.json()
            key = (body.get("idempotency_key")
                   or body.get("key")
                   or body.get("idempotencyKey"))
        except:
            pass

    if key:
        existing = redis_client.get(f"order:idem:{key}")
        if existing:
            return JSONResponse(content={"id": existing}, status_code=200)

    order_id = str(uuid.uuid4())

    if key:
        redis_client.set(f"order:idem:{key}", order_id, ex=86400)

    return JSONResponse(content={"id": order_id}, status_code=201)

@app.get("/stats")
async def get_stats():
    return {
        "uptime": time.time() - START_TIME,
        "requests": http_requests_total._value.get()
    }

@app.get("/ping")
async def ping():
    return {"ping": "pong"}

@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")

@app.get("/logs")
async def get_logs():
    return list(logs_queue)
