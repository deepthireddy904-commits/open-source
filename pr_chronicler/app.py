"""
FastAPI Webhook Ingestion Application.
Exposes POST /webhook/github for receiving GitHub pull_request events,
filtering non-merged events, verifying HMAC signatures, ensuring idempotency,
and orchestrating the context hydration, LCEL synthesis, and email dispatch pipeline.
"""

import hashlib
import hmac
import time
from typing import Set, Dict, Any, Optional
from collections import OrderedDict

from fastapi import FastAPI, Request, Header, HTTPException, status
from fastapi.responses import JSONResponse

from pr_chronicler.logger import logger
from pr_chronicler.config import settings
from pr_chronicler.schemas import ProcessingResponse, PRChroniclerOutput
from pr_chronicler.github_client import GitHubClient
from pr_chronicler.synthesizer import PRSynthesizer
from pr_chronicler.email_dispatcher import EmailDispatcher

# Create FastAPI application
app = FastAPI(
    title="PR Chronicler & Learning Dispatcher",
    description="Automated Open-Source PR Chronicler and Learning Dispatcher (GenAI 101)",
    version="1.0.0"
)

# Initialize core services
github_client = GitHubClient()
synthesizer = PRSynthesizer()
email_dispatcher = EmailDispatcher()

# In-memory LRU cache for delivery idempotency (stores recent delivery IDs and PR commits)
PROCESSED_DELIVERIES: OrderedDict[str, float] = OrderedDict()
MAX_CACHE_SIZE = 1000

def check_and_record_idempotency(delivery_id: Optional[str], repo: str, pull_number: int, commit_sha: Optional[str]) -> bool:
    """
    Checks if this delivery or PR merge commit was already processed.
    Returns True if already processed (duplicate), False if new.
    """
    # Key on delivery ID if present, otherwise on repo + PR number + commit sha
    cache_key = delivery_id or f"{repo}#{pull_number}@{commit_sha or 'unknown'}"

    # Clean old cache entries if too large
    if len(PROCESSED_DELIVERIES) > MAX_CACHE_SIZE:
        PROCESSED_DELIVERIES.popitem(last=False)

    if cache_key in PROCESSED_DELIVERIES:
        return True

    PROCESSED_DELIVERIES[cache_key] = time.time()
    return False

def verify_github_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    """
    Verifies GitHub webhook HMAC SHA-256 signature against settings.github_webhook_secret.
    """
    secret = settings.github_webhook_secret
    if not secret:
        # Secret verification not configured
        return True

    if not signature_header:
        logger.warning("[Webhook Security] Missing X-Hub-Signature-256 header when secret is configured.")
        return False

    prefix, _, sig = signature_header.partition("=")
    if prefix != "sha256":
        logger.warning(f"[Webhook Security] Unsupported signature prefix: {prefix}")
        return False

    mac = hmac.new(secret.encode("utf-8"), msg=raw_body, digestmod=hashlib.sha256)
    expected_sig = mac.hexdigest()
    is_valid = hmac.compare_digest(expected_sig, sig)
    if not is_valid:
        logger.warning("[Webhook Security] Invalid HMAC SHA-256 signature received.")
    return is_valid

@app.on_event("startup")
async def startup_event():
    """Logs system startup and masked configuration parameters."""
    logger.info("==========================================================")
    logger.info("Starting PR Chronicler & Learning Dispatcher (GenAI 101)")
    logger.info(f"Active Settings: {settings.safe_dict()}")
    logger.info("Ready to accept webhook events on POST /webhook/github")
    logger.info("==========================================================")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "pr-chronicler",
        "gemini_model": settings.gemini_model,
        "smtp_configured": bool(settings.smtp_email and settings.smtp_app_password),
        "dry_run_smtp": settings.dry_run_smtp
    }

@app.get("/")
async def root():
    """Root info endpoint."""
    return {
        "service": "Automated Open-Source PR Chronicler and Learning Dispatcher",
        "version": "1.0.0",
        "documentation": "/docs",
        "webhook_endpoint": "POST /webhook/github"
    }

@app.post("/webhook/github", response_model=ProcessingResponse)
async def github_webhook(
    request: Request,
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_github_delivery: Optional[str] = Header(None, alias="X-GitHub-Delivery"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256")
):
    """
    Primary GitHub Webhook Ingestion Endpoint.
    Listens for pull_request events, strictly filters for action=='closed' and merged==True,
    hydrates diff & linked issue context, triggers LangChain LCEL synthesis,
    dispatches email reflections, and logs all lifecycle events.
    """
    total_start_time = time.time()
    raw_body = await request.body()

    # Step 1: Webhook Authenticity Check
    if not verify_github_signature(raw_body, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub webhook HMAC SHA256 signature"
        )

    # Step 2: Handle GitHub Ping Event
    if x_github_event == "ping":
        logger.info(f"[Webhook Event] Received GitHub 'ping' event (Delivery ID: {x_github_delivery})")
        return ProcessingResponse(
            status="success",
            message="Pong! Webhook configured successfully.",
            action="ping"
        )

    # Step 3: Parse Webhook Payload
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as exc:
        logger.error(f"[Webhook Error] Malformed JSON payload: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed JSON payload: {str(exc)}"
        )

    # Extract pull request and repo information
    action = payload.get("action", "")
    pr_data = payload.get("pull_request")
    repo_data = payload.get("repository", {})
    repo_full_name = repo_data.get("full_name") or repo_data.get("name") or "unknown/repo"
    pr_number = pr_data.get("number") if pr_data else payload.get("number", 0)

    logger.info(
        f"[Webhook Event] Delivery: {x_github_delivery or 'none'} | Event: {x_github_event or 'pull_request'} | "
        f"Action: '{action}' | Repo: {repo_full_name} | PR #{pr_number}"
    )

    # If payload is not a pull_request event
    if not pr_data:
        logger.info(f"[Filter] Event lacks 'pull_request' payload. Ignored.")
        return ProcessingResponse(
            status="ignored",
            message=f"Event does not contain pull_request object",
            action=action,
            repository=repo_full_name,
            pull_number=pr_number
        )

    # Step 4: Strict Event Filtering
    # Only execute pipeline when action == "closed" and pull_request.merged is True.
    # For opened, synchronized, edited, or closed-but-unmerged events, log and return HTTP 200.
    is_merged = bool(pr_data.get("merged", False))

    if action != "closed":
        reason = f"Event action '{action}' is ignored; only 'closed' events are evaluated."
        logger.info(f"[Filter] PR #{pr_number} on {repo_full_name} - {reason}")
        return ProcessingResponse(
            status="ignored",
            message=reason,
            action=action,
            repository=repo_full_name,
            pull_number=pr_number
        )

    if not is_merged:
        reason = f"PR was closed without being merged (merged=False). Synthesis pipeline skipped."
        logger.info(f"[Filter] PR #{pr_number} on {repo_full_name} - {reason}")
        return ProcessingResponse(
            status="ignored",
            message=reason,
            action=action,
            repository=repo_full_name,
            pull_number=pr_number
        )

    # Step 5: Idempotency Check
    merge_commit_sha = pr_data.get("merge_commit_sha")
    if check_and_record_idempotency(x_github_delivery, repo_full_name, pr_number, merge_commit_sha):
        reason = f"Duplicate delivery detected for {repo_full_name}#{pr_number} (Commit: {merge_commit_sha}). Skipping."
        logger.warning(f"[Idempotency] {reason}")
        return ProcessingResponse(
            status="ignored",
            message=reason,
            action=action,
            repository=repo_full_name,
            pull_number=pr_number
        )

    # Accepted Event! Proceed with full Chronicler Pipeline
    logger.info(
        f"[Pipeline Lifecycle] >>> ACCEPTED: PR #{pr_number} merged in {repo_full_name}. Launching Chronicler pipeline."
    )

    try:
        # Step 6: GitHub API Context Hydration
        owner_part = repo_full_name.split("/")[0] if "/" in repo_full_name else "unknown"
        repo_part = repo_full_name.split("/")[1] if "/" in repo_full_name else repo_full_name
        pr_title = pr_data.get("title", f"PR #{pr_number}")
        pr_body = pr_data.get("body", "")
        author = pr_data.get("user", {}).get("login", "unknown")

        hydration_context = await github_client.hydrate_context(
            owner=owner_part,
            repo=repo_part,
            pull_number=pr_number,
            pr_title=pr_title,
            pr_body=pr_body
        )

        diff_char_count = hydration_context.get("total_diff_length", 0)
        logger.info(
            f"[Pipeline Lifecycle] Hydrated context for {repo_full_name}#{pr_number}: "
            f"Diff length = {diff_char_count} chars, Has linked issue = {hydration_context.get('has_linked_issue')}"
        )

        # Step 7: LCEL Synthesis with Gemini Flash & Strict Pydantic Parser
        synthesis_output: PRChroniclerOutput = await synthesizer.synthesize(
            hydration_context=hydration_context,
            author=author
        )

        logger.info(
            f"[Pipeline Lifecycle] Synthesis succeeded for {repo_full_name}#{pr_number}. "
            f"Structured parser output generated with {len(synthesis_output.key_learnings)} key learnings."
        )

        # Step 8: SMTP Email Dispatch
        email_dispatched = await email_dispatcher.dispatch(
            output=synthesis_output,
            repo=repo_full_name,
            pull_number=pr_number,
            pr_title=pr_title,
            author=author,
            diff_length=diff_char_count
        )

        elapsed_latency = time.time() - total_start_time
        logger.info(
            f"[Pipeline Lifecycle] >>> COMPLETED: PR #{pr_number} pipeline finished in {elapsed_latency:.2f}s "
            f"(Email Dispatched: {email_dispatched})"
        )

        return ProcessingResponse(
            status="success",
            message="PR chronicler pipeline executed and learning dispatch processed successfully",
            action="closed",
            repository=repo_full_name,
            pull_number=pr_number,
            latency_seconds=round(elapsed_latency, 2),
            diff_length=diff_char_count,
            email_dispatched=email_dispatched
        )

    except Exception as exc:
        elapsed_latency = time.time() - total_start_time
        logger.error(
            f"[Pipeline Lifecycle] !!! FAILED: Processing PR #{pr_number} failed after {elapsed_latency:.2f}s: {exc}",
            exc_info=True
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "message": f"Pipeline processing failed: {str(exc)}",
                "repository": repo_full_name,
                "pull_number": pr_number,
                "latency_seconds": round(elapsed_latency, 2)
            }
        )
