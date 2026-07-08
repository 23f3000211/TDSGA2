EMAIL = "23f3000211@ds.study.iitm.ac.in"

# Q1: CORS Allowed Origin
Q1_ALLOWED_ORIGIN = "https://dash-1c90d5.example.com"
EXAM_PORTAL_ORIGIN = "https://exam.sanand.workers.dev"

# Q2: OAuth JWKS
ISSUER = "https://idp.exam.local"
AUDIENCE = "tds-8bempw6v.apps.exam.local"
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2okOHspNjgA+2rTLbeuY
cxiP/hG8C6Sb9iwg3yiLAA4HCnpITcbWCSelbvbYGuc3EbNy4xFyf5Cbj5DHJMID
EkryOgyd2giIIIBOUBj8S63uGcnRpOBh9NFatfNwheKuzsPuVNldu6A9cNteNpXc
WyJjG2axVfmq7i6SuKr1JoWYG7xTTAvKPujSl4OtsQfO3h5NepzdfXpr28oNnzfW
ed+zclR6BcmNNo/WVfJ4xyCLSf0BCOgdTgW6PdaChd1l9VDetJZVEgC5tkyvXsfI
SI6iyrYbKR0NEBSqq4XkadEjsCs4F1RncsS4LlgniT7GlkL9Mce3b0wGLs9/7ZIX
dQIDAQAB
-----END PUBLIC KEY-----"""

# Q3: 12-Factor Config
Q3_PORT = 8728
Q3_WORKERS = 1
Q3_DEBUG = False
Q3_LOG_LEVEL = "info"

# Q5: Analytics API key
Q5_API_KEY = "ak-placeholder"

# Q9: Rate limit for /orders (requests per 10s)
Q9_RATE_LIMIT = 5

# Q10: Rate limit for /ping and allowed origin
Q10_RATE_LIMIT = 12
Q10_ALLOWED_ORIGIN = "https://exam.sanand.workers.dev"
