"""
FastAPI application main entry point.
"""

import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

from backend.app.api.routes import router

# Load environment variables
load_dotenv()

# Prometheus metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration')
MATCHING_REQUESTS = Counter('matching_requests_total', 'Total matching requests', ['incentive_id'])
MATCHING_DURATION = Histogram('matching_duration_seconds', 'Matching processing duration')
OPENAI_REQUESTS = Counter('openai_requests_total', 'Total OpenAI API requests', ['model', 'type'])
OPENAI_COST = Counter('openai_cost_total', 'Total OpenAI cost in EUR', ['model'])
DATABASE_CONNECTIONS = Gauge('database_connections_active', 'Active database connections')
EMBEDDINGS_GENERATED = Counter('embeddings_generated_total', 'Total embeddings generated', ['type'])

# Create FastAPI app
app = FastAPI(
    title="Public Incentives API",
    description="API for matching companies with public incentives in Portugal",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add metrics middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware to collect HTTP metrics."""
    start_time = time.time()
    
    response = await call_next(request)
    
    # Calculate duration
    duration = time.time() - start_time
    REQUEST_DURATION.observe(duration)
    
    # Count requests
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    return response

# Include API routes
app.include_router(router, prefix="/api/v1", tags=["API"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Public Incentives API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
        "metrics": "/metrics"
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
