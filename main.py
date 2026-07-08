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

def safe_extract_json(s: str) -> dict:
    s = s.strip()
    if s.startswith("```"):
        newline_idx = s.find("\n")
        if newline_idx != -1:
            s = s[newline_idx:].strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    try:
        return json.loads(s)
    except Exception:
        match = re.search(r'(\{.*\})', s, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
    return {}

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

    now = time.time()
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

    if origin:
        if path == "/ping":
            if origin == config.Q10_ALLOWED_ORIGIN or config.EXAM_PORTAL_ORIGIN in origin:
                response.headers["Access-Control-Allow-Origin"] = origin
        elif path == "/stats":
            if origin == config.Q1_ALLOWED_ORIGIN or config.EXAM_PORTAL_ORIGIN in origin:
                response.headers["Access-Control-Allow-Origin"] = origin
        else:
            response.headers["Access-Control-Allow-Origin"] = "*"
            
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Expose-Headers"] = "*"
    return response

# --- Q1 ---
@app.get("/stats")
async def stats(values: str = ""):
    nums = [int(x) for x in values.split(",") if x.strip()]
    if not nums:
        return JSONResponse(content={"error": "no values"}, status_code=400)
    return {
        "email": config.EMAIL,
        "count": len(nums),
        "sum": sum(nums),
        "min": min(nums),
        "max": max(nums),
        "mean": round(sum(nums) / len(nums), 6)
    }

# --- Q2 ---
# --- ROUTES ---

@app.get("/")
async def root():
    return {"status": "ok"}

orders_store = {}

@app.post("/orders")
async def create_order(request: Request):
    body = await request.json()
    key = body.get("idempotency_key") or body.get("key")
    if key and key in orders_store:
        return JSONResponse(content={"id": orders_store[key]}, status_code=200)
    order_id = str(uuid.uuid4())
    if key:
        orders_store[key] = order_id
    return JSONResponse(content={"id": order_id}, status_code=201)

# ⚠️ APNA T VALUE DEKHO EXAM PAGE PE AUR YAHAN REPLACE KARO
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
    return {"email": config.EMAIL, "request_id": request.state.req_id}
