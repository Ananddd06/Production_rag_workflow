"""
Main FastAPI application for the Production RAG system.

Wires together all pipeline components, monitoring, caching, and storage.
Run with: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import hashlib
import logging
import os
import traceback
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from config import settings
from pipeline.preprocessor import QueryPreprocessor
from pipeline.retriever import HybridRetriever
from pipeline.reranker import CrossEncoderReranker
from pipeline.assembler import ContextAssembler
from pipeline.generator import LLMGenerator
from storage.vector_store import VectorStore
from storage.monitoring_db import MonitoringDB
from cache.cache_manager import CacheManager
from monitoring.metrics import QualityMetrics
from monitoring.alerts import AlertManager
from ingest.document_loader import DocumentLoader
from monitoring.tracker import LatencyTracker, CostTracker



# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rag.main")

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    filters: Optional[dict] = None
    top_k: int = 5


class IngestTextRequest(BaseModel):
    text: str
    metadata: Optional[dict] = None


class IngestDirectoryRequest(BaseModel):
    path: str


class FeedbackRequest(BaseModel):
    query_id: str
    feedback: str  # 'up' or 'down'


# ---------------------------------------------------------------------------
# Global component references (initialised in lifespan)
# ---------------------------------------------------------------------------
components: dict = {}


def _load_sample_docs() -> None:
    """Auto-load sample documents on first startup if the vector store is empty."""
    vector_store = components["vector_store"]
    document_loader = components["document_loader"]
    monitoring_db = components["monitoring_db"]

    try:
        if vector_store.get_stats().get("document_count", 0) > 0:
            logger.info("Vector store already populated — skipping sample doc load.")
            return

        sample_dir = os.path.join(os.path.dirname(__file__), "..", "data", "sample_docs")
        sample_dir = os.path.abspath(sample_dir)

        if not os.path.isdir(sample_dir):
            logger.info(f"No sample docs directory found at {sample_dir}")
            return

        logger.info(f"Loading sample documents from {sample_dir} …")
        chunks = document_loader.load_directory(sample_dir)
        if chunks:
            vector_store.add_documents(chunks)
            monitoring_db.log_event(
                "startup",
                f"Auto-loaded {len(chunks)} sample document chunks",
                {"source": sample_dir, "chunks": len(chunks)},
            )
            logger.info(f"Loaded {len(chunks)} sample chunks into the vector store.")
        else:
            logger.info("No documents found in sample_docs directory.")
    except Exception as exc:
        logger.warning(f"Failed to load sample docs: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise all RAG components on startup and tear down on shutdown."""
    logger.info("Starting RAG pipeline initialisation …")

    try:
        # Core storage
        components["vector_store"] = VectorStore()
        components["monitoring_db"] = MonitoringDB(
            db_path=getattr(settings, "monitoring_db_path", "./monitoring.db")
        )

        # Cache
        components["cache_manager"] = CacheManager(
            max_size=getattr(settings, "cache_max_size", 1000),
            ttl=getattr(settings, "cache_ttl", 3600),
        )

        # Pipeline stages
        components["preprocessor"] = QueryPreprocessor()
        components["retriever"] = HybridRetriever(components["vector_store"])
        components["reranker"] = CrossEncoderReranker()
        components["assembler"] = ContextAssembler()
        components["generator"] = LLMGenerator()

        # Monitoring
        components["quality_metrics"] = QualityMetrics(components["monitoring_db"])
        components["alert_manager"] = AlertManager(components["monitoring_db"])

        # Ingestion
        components["document_loader"] = DocumentLoader(components["vector_store"])

        # Auto-load sample documents disabled by request
        # _load_sample_docs()

        components["monitoring_db"].log_event(
            "startup", "RAG pipeline initialised successfully"
        )
        logger.info("RAG pipeline initialisation complete.")

    except Exception as exc:
        logger.error(f"Startup failed: {exc}\n{traceback.format_exc()}")
        raise

    yield  # ---- application is running ----

    logger.info("Shutting down RAG pipeline …")
    components["monitoring_db"].log_event("shutdown", "RAG pipeline shutting down")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Production RAG API",
    description="A production-grade Retrieval-Augmented Generation system with full observability.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/")
async def redirect_to_dashboard():
    return RedirectResponse(url="/dashboard/")

# Mount the static frontend directory so it can be accessed on the same port
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/dashboard", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    logger.warning("Frontend directory not found at /app/frontend")




@app.post("/api/query")
async def query_endpoint(request: QueryRequest):
    """
    Execute the full RAG pipeline: preprocess → retrieve → rerank → assemble → generate.
    """
    try:
        query_id = str(uuid.uuid4())
        latency_tracker = LatencyTracker()
        cost_tracker = CostTracker()

        cache_manager: CacheManager = components["cache_manager"]
        monitoring_db: MonitoringDB = components["monitoring_db"]
        alert_manager: AlertManager = components["alert_manager"]

        # ---- Check cache ----
        cache_key = hashlib.sha256(
            f"{request.query}:{request.filters}:{request.top_k}".encode()
        ).hexdigest()
        cached = cache_manager.get(cache_key)
        if cached is not None:
            cached["cached"] = True
            cached["query_id"] = query_id
            return cached



        # ---- 1. Preprocessing ----
        with latency_tracker.track("preprocessing"):
            processed_query = components["preprocessor"].preprocess(request.query)

        # ---- 2. Retrieval ----
        with latency_tracker.track("retrieval"):
            raw_results = components["retriever"].retrieve(
                processed_query, top_k=request.top_k, filters=request.filters
            )
            cost_tracker.track_embedding(len(processed_query.get('processed', request.query).split()) * 2)
            cost_tracker.track_vector_db(1)

        # ---- 3. Reranking ----
        with latency_tracker.track("reranking"):
            reranked = components["reranker"].rerank(processed_query.get('processed', request.query), raw_results)

        # ---- 4. Context assembly ----
        with latency_tracker.track("assembly"):
            context = components["assembler"].assemble(processed_query.get('processed', request.query), reranked)

        # ---- 5. Generation ----
        with latency_tracker.track("generation"):
            result = components["generator"].generate(processed_query.get('processed', request.query), context)
            cost_tracker.track_generation(len(result.get("answer", "").split()) * 2)

        # ---- Collect metrics ----
        latency_breakdown = latency_tracker.get_breakdown()
        cost_breakdown = cost_tracker.get_query_cost()
        citations = result.get("citations_used", [])

        # ---- Log to monitoring DB ----
        monitoring_db.log_query({
            "query_id": query_id,
            "query_text": request.query,
            "response_text": result.get("answer", ""),
            "latency_breakdown": latency_breakdown,
            "cost_breakdown": cost_breakdown,
            "citations": citations,
            "model_used": result.get("model", getattr(settings, "HF_MODEL_ID", "unknown")),
        })

        # ---- Log Quality Metrics ----
        quality_metrics: QualityMetrics = components["quality_metrics"]
        citations_provided = len(context.get("citations", []))
        citations_used = len(citations)
        quality_metrics.record_citation_accuracy(query_id, citations_provided, citations_used)
        
        # Simple heuristic: If citations were provided but NONE were used, it might be hallucinating (not grounded).
        is_grounded = citations_used > 0 or citations_provided == 0
        quality_metrics.record_hallucination_check(query_id, is_grounded)

        # ---- Check alerts ----
        total_latency = latency_breakdown.get("total_ms", 0)
        alert_manager.check_latency(total_latency)

        total_cost = cost_breakdown.get("total_cost", 0)
        if total_cost > 0:
            cost_per_1k = total_cost * 1000
            alert_manager.check_cost(cost_per_1k)

        # ---- Build response ----
        response = {
            "query_id": query_id,
            "answer": result.get("answer", ""),
            "citations": context.get("citations", []),
            "citations_used": citations,
            "model": result.get("model", getattr(settings, "HF_MODEL_ID", "unknown")),
            "latency": latency_breakdown,
            "cost": cost_breakdown,
            "cached": False,
        }

        # ---- Cache the response ----
        cache_manager.set(cache_key, response)

        return response

    except Exception as exc:
        logger.error(f"Query failed: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/ingest")
async def ingest_text(
    text: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    """Ingest text or an uploaded file into the vector store."""
    try:
        vector_store: VectorStore = components["vector_store"]
        document_loader: DocumentLoader = components["document_loader"]
        monitoring_db: MonitoringDB = components["monitoring_db"]

        chunks = []

        if file is not None:
            if file.filename.lower().endswith('.pdf'):
                import pypdf
                import io
                content = ""
                reader = pypdf.PdfReader(io.BytesIO(await file.read()))
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        content += text + "\n"
                chunks = document_loader.load_text(
                    content, metadata={"filename": file.filename, "source": file.filename}
                )
            else:
                content = (await file.read()).decode("utf-8", errors="replace")
                chunks = document_loader.load_text(
                    content, metadata={"filename": file.filename, "source": file.filename}
                )
        elif text is not None:
            meta = {}
            if metadata:
                import json
                try:
                    meta = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
            if "source" not in meta:
                meta["source"] = "text_input"
            chunks = document_loader.load_text(text, metadata=meta)
        else:
            raise HTTPException(
                status_code=400, detail="Provide either 'text' or a file upload."
            )

        if chunks:
            vector_store.add_documents(chunks)
            # update BM25 index
            components["retriever"]._build_bm25_index()



        monitoring_db.log_event(
            "ingest",
            f"Ingested {len(chunks)} chunks",
            {"source": file.filename if file else "text_input", "chunks": len(chunks)},
        )

        return {
            "chunks_added": len(chunks),
            "total_documents": vector_store.get_stats().get("document_count", 0),
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Ingest failed: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/documents")
async def list_documents():
    """List all unique document sources in the vector store."""
    try:
        vector_store: VectorStore = components["vector_store"]
        sources = vector_store.get_all_sources()
        return {"documents": [{"source": src} for src in sources]}
    except Exception as e:
        logger.error(f"List documents error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/documents/{source}")
async def delete_document(source: str):
    """Delete a specific document from the vector store."""
    try:
        vector_store: VectorStore = components["vector_store"]
        vector_store.delete_document(source)
        components["monitoring_db"].log_event(
            "delete_doc", f"Deleted document: {source}", {"source": source}
        )
        return {"status": "success", "message": f"Deleted {source}"}
    except Exception as e:
        logger.error(f"Delete document error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ingest/directory")
async def ingest_directory(request: IngestDirectoryRequest):
    """Ingest all documents from a local directory."""
    try:
        vector_store: VectorStore = components["vector_store"]
        document_loader: DocumentLoader = components["document_loader"]
        monitoring_db: MonitoringDB = components["monitoring_db"]

        if not os.path.isdir(request.path):
            raise HTTPException(status_code=400, detail=f"Directory not found: {request.path}")

        chunks = document_loader.load_directory(request.path)
        if chunks:
            vector_store.add_documents(chunks)
            # update BM25 index
            components["retriever"]._build_bm25_index()

        monitoring_db.log_event(
            "ingest",
            f"Ingested {len(chunks)} chunks from directory",
            {"source": request.path, "chunks": len(chunks)},
        )

        return {
            "chunks_added": len(chunks),
            "total_documents": vector_store.get_stats().get("document_count", 0),
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Directory ingest failed: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Record user feedback (thumbs up / down) for a query."""
    try:
        if request.feedback not in ("up", "down"):
            raise HTTPException(
                status_code=400, detail="Feedback must be 'up' or 'down'"
            )

        quality_metrics: QualityMetrics = components["quality_metrics"]
        quality_metrics.record_feedback(request.query_id, request.feedback)

        return {"status": "recorded"}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Feedback failed: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/metrics/latency")
async def get_latency_metrics(hours: int = 24):
    """Return latency history and averages for the given time window."""
    try:
        monitoring_db: MonitoringDB = components["monitoring_db"]
        history = monitoring_db.get_latency_history(hours=hours)

        # Compute averages
        avg_latency: dict = {}
        if history:
            all_keys: set = set()
            for entry in history:
                if isinstance(entry["latency_breakdown"], dict):
                    all_keys.update(entry["latency_breakdown"].keys())
            for key in all_keys:
                values = [
                    entry["latency_breakdown"].get(key, 0.0) for entry in history if isinstance(entry["latency_breakdown"], dict)
                ]
                if values:
                    avg_latency[key] = round(sum(values) / len(values), 2)

        return {"history": history, "avg_latency": avg_latency}

    except Exception as exc:
        logger.error(f"Latency metrics failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/metrics/quality")
async def get_quality_metrics(hours: int = 24):
    """Return the quality summary for the given time window."""
    try:
        quality_metrics: QualityMetrics = components["quality_metrics"]
        return quality_metrics.get_quality_summary(hours=hours)

    except Exception as exc:
        logger.error(f"Quality metrics failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/metrics/cost")
async def get_cost_metrics(hours: int = 24):
    """Return cost history and totals for the given time window."""
    try:
        monitoring_db: MonitoringDB = components["monitoring_db"]
        history = monitoring_db.get_cost_history(hours=hours)

        total_cost: dict = {}
        if history:
            all_keys: set = set()
            for entry in history:
                if isinstance(entry["cost_breakdown"], dict):
                    all_keys.update(entry["cost_breakdown"].keys())
            for key in all_keys:
                values = [
                    entry["cost_breakdown"].get(key, 0.0) for entry in history if isinstance(entry["cost_breakdown"], dict)
                ]
                total_cost[key] = round(sum(values), 8)

        return {"history": history, "total_cost": total_cost}

    except Exception as exc:
        logger.error(f"Cost metrics failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/metrics/dashboard")
async def get_dashboard():
    """Return the full aggregated dashboard summary."""
    try:
        monitoring_db: MonitoringDB = components["monitoring_db"]
        quality_metrics: QualityMetrics = components["quality_metrics"]
        alert_manager: AlertManager = components["alert_manager"]
        cache_manager: CacheManager = components["cache_manager"]
        vector_store: VectorStore = components["vector_store"]

        dashboard = monitoring_db.get_dashboard_summary()

        # Enrich with live component data
        dashboard["quality_summary"] = quality_metrics.get_quality_summary()
        dashboard["recent_alerts"] = alert_manager.get_recent_alerts(limit=20)
        dashboard["cache_stats"] = cache_manager.get_stats()
        dashboard["document_stats"] = {
            "total_documents": vector_store.get_stats().get("document_count", 0),
        }

        return dashboard

    except Exception as exc:
        logger.error(f"Dashboard failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/alerts")
async def get_alerts(limit: int = 50):
    """Return recent alerts."""
    try:
        alert_manager: AlertManager = components["alert_manager"]
        return alert_manager.get_recent_alerts(limit=limit)

    except Exception as exc:
        logger.error(f"Alerts fetch failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/health")
async def health_check():
    """Return health status of all pipeline components."""
    component_status = {}
    for name in [
        "vector_store",
        "cache_manager",
        "monitoring_db",
        "preprocessor",
        "retriever",
        "reranker",
        "assembler",
        "generator",
        "quality_metrics",
        "alert_manager",
        "document_loader",
    ]:
        component_status[name] = "healthy" if name in components else "unavailable"

    overall = (
        "healthy"
        if all(s == "healthy" for s in component_status.values())
        else "degraded"
    )

    return {"status": overall, "components": component_status}
