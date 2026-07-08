#!/bin/bash
# Start Redis server in the background
redis-server --daemonize yes

# Start the FastAPI application on the port provided by Render
uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}
