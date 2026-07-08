import time
import uuid
from collections import deque
from typing import Optional
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, generate_latest
import redis
import jwt

import config

START_TIME = time.time()
app = FastAPI()

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
        return res[2] > limit
    except Exception as e:
        print(f"Redis error: {e}", flush=True)
        return False

@app.middleware("http")
async def custom_middleware(request: Request, call_next):
    http_requests_total.inc()
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.req_id = req_id
    logs_queue.append({
        "level": "INFO", "ts": time.time(),
        "path": request.url.path, "request_id": req_id
    })

    path = request.url.path.rstrip("/") or "/"
    start_time = time.time()
    response = None

    # Rate limit ONLY if X-Client-Id header is explicitly sent
    client_id = request.headers.get("X-Client-Id")
    if client_id and request.method not in ("OPTIONS", "HEAD"):
        if path == "/orders":
            if is_rate_limited(client_id, config.Q9_RATE_LIMIT, "q9"):
                response = Response(status_code=429, headers={"Retry-After": "10"})
        elif path == "/ping":
            if is_rate_limited(client_id, config.Q10_RATE_LIMIT, "q10"):
                response = Response(status_code=429, headers={"Retry-After": "10"})

    if not response:
        try:
            response = await call_next(request)
        except Exception as e:
            print(f"Error: {e}", flush=True)
            response = Response(status_code=500, content="Internal Server Error")

    response.headers["X-Request-ID"] = req_id
    response.headers["X-Process-Time"] = f"{time.time() - start_time:.6f}"
    return response

# ---------- ROUTES ----------

@app.get("/")
async def root():
    return {"status": "ok"}

TOTAL_ORDERS = 54  # ⚠️ APNA T VALUE DAALO EXAM PAGE SE
ALL_ORDER_IDS = list(range(1, TOTAL_ORDERS + 1))

@app.get("/orders")
async def get_orders(limit: int = 10, cursor: Optional[str] = None):
    start = 0
    if cursor:
        try:
            start = int(cursor)
        except:
            start = 0
    items = ALL_ORDER_IDS[start : start + limit]
    next_cursor = str(start + limit) if (start + limit) < TOTAL_ORDERS else None
    return {"items": [{"id": i} for i in items], "next_cursor": next_cursor}

@app.post("/orders")
async def create_order(request: Request):
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
            return JSONResponse({"id": existing}, status_code=200)

    order_id = str(uuid.uuid4())
    if key:
        redis_client.set(f"order:idem:{key}", order_id, ex=86400)
    return JSONResponse({"id": order_id}, status_code=201)

@app.get("/stats")
async def get_stats():
    return {"uptime": time.time() - START_TIME,
            "requests": int(http_requests_total._value.get())}

@app.get("/ping")
async def ping():
    return {"ping": "pong"}

@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")

@app.get("/logs")
async def get_logs():
    return list(logs_queue)

@app.post("/analytics")
async def analytics(request: Request):
    api_key = request.headers.get("X-API-Key") or request.headers.get("X-Api-Key")
    if not api_key or api_key != config.Q5_API_KEY:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    events = body.get("events", [])

    total_events = len(events)
    users = set()
    user_revenue = {}
    revenue = 0.0

    for event in events:
        user = event.get("user")
        amount = event.get("amount", 0)
        if user:
            users.add(user)
        if amount > 0:
            revenue += amount
            if user:
                user_revenue[user] = user_revenue.get(user, 0) + amount

    top_user = max(user_revenue, key=user_revenue.get) if user_revenue else None

    return JSONResponse({
        "email": config.EMAIL,
        "total_events": total_events,
        "unique_users": len(users),
        "revenue": round(revenue, 2),
        "top_user": top_user
    })
