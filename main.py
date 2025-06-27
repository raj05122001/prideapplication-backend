from fastapi import FastAPI, Request
import uvicorn
import logging
import threading
import time
import schedule
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from db.connection import engine
from db import models
import os
import json

from routes.auth import login
from routes.Researcher import researcher
from routes.Plan import CheckPlan
from routes.NewsSubscriptionManager import NewsSubscriptionManager, send_notification
from routes.payment import payments

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Allowed Origins for CORS
origins = [
    "http://localhost:4000",
    "https://pridebuzz.in",
    "wss://pridebuzz.in",
    "https://pridecons.com",
    "https://dev.pridecons.com",
    "https://d22k2bc34hwqer.cloudfront.net",
    "https://pridesphere.in",
    "http://182.70.246.103:777",
    "http://182.70.246.103",
    "http://192.168.0.254",
    "http://localhost:8081",
    "http://192.168.30.227",
    "*"
]

# Initialize FastAPI app
app = FastAPI()

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins= origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    FastAPICache.init(
        backend=InMemoryBackend(),     # or RedisBackend(...) if you prefer
        prefix="fastapi-cache"         # optional; used to namespace your keys
    )


# Root API Endpoint
@app.get("/")
def read_root():
    return {"message": "Welcome to Pride Backend API v1"}


# Registering Routes
app.include_router(payments.router)
app.include_router(login.router)
app.include_router(researcher.router)
app.include_router(CheckPlan.router)
app.include_router(NewsSubscriptionManager.router)
app.include_router(send_notification.router)


# Database Table Creation
try:
    models.Base.metadata.create_all(engine)
    logger.info("Tables created successfully!")
except Exception as e:
    logger.error(f"Error creating tables: {e}", exc_info=True)



# Run FastAPI with Uvicorn
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
