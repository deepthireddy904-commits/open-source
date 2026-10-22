"""
Pydantic data models for GitHub Webhook payloads and LLM output parsing.
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

# ============================================================================
# LLM Synthesis & Structured Output Models (Strict Pydantic Schema for LCEL)
# ============================================================================

class KeyLearning(BaseModel):
    """A specific, evidence-based technical learning derived from the PR changes."""
    category: str = Field(
        ...,
        description="Technical category of the learning (e.g., 'Architecture & Design', 'Async & Concurrency', 'Error Handling & Resilience', 'Performance', 'API Design')."
    )
    insight: str = Field(
        ...,
        description="The technical lesson or design takeaway observed from the code change. Must be concrete and avoid generic platitudes."
    )
    evidence: str = Field(
        ...,
        description="Exact code reference, pattern, function name, file path, or patch snippet providing proof of this learning."
    )

class PRChroniclerOutput(BaseModel):
    """
    Structured extraction representing technical synthesis of the merged PR.
    Enforces the three required reflection components:
    1. Issue Details
    2. Execution Summary
    3. 3-4 Key Learnings
    """
    issue_details: str = Field(
        ...,
        description="Comprehensive summary of the problem, bug report, or feature request being solved, drawing from linked issues or PR description."
    )
    execution_summary: str = Field(
        ...,
        description="Detailed technical walkthrough of the changes implemented in the pull request, explaining the architectural decisions and code modifications."
    )
    key_learnings: List[KeyLearning] = Field(
        ...,
        min_length=3,
        max_length=4,
        description="Exactly 3 to 4 specific, evidence-based technical learnings derived directly from the code changes."
    )


# ============================================================================
# GitHub Webhook Payload Models
# ============================================================================

class GitHubUser(BaseModel):
    login: str
    id: Optional[int] = None
    html_url: Optional[str] = None

class GitHubRepo(BaseModel):
    name: str
    full_name: str
    html_url: Optional[str] = None
    owner: Optional[GitHubUser] = None
    default_branch: Optional[str] = "main"

class GitHubPullRequest(BaseModel):
    number: int
    title: str
    body: Optional[str] = ""
    state: Optional[str] = None
    merged: Optional[bool] = False
    html_url: Optional[str] = None
    user: Optional[GitHubUser] = None
    merge_commit_sha: Optional[str] = None
    created_at: Optional[str] = None
    merged_at: Optional[str] = None
    diff_url: Optional[str] = None
    patch_url: Optional[str] = None

class GitHubWebhookPayload(BaseModel):
    action: str
    number: Optional[int] = None
    pull_request: Optional[GitHubPullRequest] = None
    repository: Optional[GitHubRepo] = None
    sender: Optional[GitHubUser] = None

    class Config:
        extra = "allow"


# ============================================================================
# API Response & Processing Context Models
# ============================================================================

class ProcessingResponse(BaseModel):
    status: str
    message: str
    action: Optional[str] = None
    repository: Optional[str] = None
    pull_number: Optional[int] = None
    latency_seconds: Optional[float] = None
    diff_length: Optional[int] = None
    email_dispatched: Optional[bool] = None
