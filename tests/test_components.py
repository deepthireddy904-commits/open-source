"""
Unit tests for PR Chronicler components.
"""

import hmac
import hashlib
from pr_chronicler.schemas import PRChroniclerOutput, KeyLearning, GitHubWebhookPayload
from pr_chronicler.github_client import GitHubClient
from pr_chronicler.email_dispatcher import EmailDispatcher
from pr_chronicler.app import check_and_record_idempotency, verify_github_signature
from pr_chronicler.config import settings

def test_pydantic_schema_validation():
    """Verify that PRChroniclerOutput strictly requires 3-4 KeyLearnings and fields."""
    learnings = [
        KeyLearning(category="API", insight="Explicit signatures prevent misinterpretation", evidence="app.py:L12"),
        KeyLearning(category="Concurrency", insight="Worker threads offload blocking I/O", evidence="email_dispatcher.py:L90"),
        KeyLearning(category="Resilience", insight="Graceful fallbacks handle missing patch data", evidence="github_client.py:L60")
    ]
    output = PRChroniclerOutput(
        issue_details="Test issue context description",
        execution_summary="Test execution summary description",
        key_learnings=learnings
    )
    assert len(output.key_learnings) == 3
    assert output.issue_details == "Test issue context description"

def test_issue_reference_extraction():
    """Verify issue reference extraction regex against various GitHub conventions."""
    client = GitHubClient()
    
    text1 = "This PR fixes #42 and resolves #108. Also closes https://github.com/org/repo/issues/999"
    issues1 = client.extract_issue_references(text1)
    assert issues1 == [42, 108, 999]

    text2 = "No issue references here, just normal commit description."
    issues2 = client.extract_issue_references(text2)
    assert issues2 == []

    text3 = "Fixed #5, closed #5, closes #5"  # duplicate references
    issues3 = client.extract_issue_references(text3)
    assert issues3 == [5]

def test_email_formatting():
    """Verify plain text and HTML email formatting contains all three required sections."""
    dispatcher = EmailDispatcher()
    output = PRChroniclerOutput(
        issue_details="Underlying issue details context",
        execution_summary="Execution technical walkthrough summary",
        key_learnings=[
            KeyLearning(category="Architecture", insight="Decoupled pipeline layers", evidence="synthesizer.py"),
            KeyLearning(category="Async", insight="Non-blocking HTTP dispatch", evidence="app.py"),
            KeyLearning(category="Testing", insight="Deterministic simulation cases", evidence="simulate_merge.py")
        ]
    )

    plain = dispatcher.format_plain_text(
        output=output,
        repo="octocat/Hello-World",
        pull_number=12,
        pr_title="Add contribution guidelines",
        author="octocat",
        diff_length=1250
    )
    assert "1. ISSUE DETAILS" in plain
    assert "2. EXECUTION SUMMARY" in plain
    assert "3. KEY LEARNINGS (EVIDENCE-BASED)" in plain
    assert "Underlying issue details context" in plain

    html = dispatcher.format_html(
        output=output,
        repo="octocat/Hello-World",
        pull_number=12,
        pr_title="Add contribution guidelines",
        author="octocat",
        diff_length=1250
    )
    assert "1. Issue Details" in html
    assert "2. Execution Summary" in html
    assert "3. Key Learnings (Evidence-Based)" in html
    assert "Decoupled pipeline layers" in html

def test_idempotency_cache():
    """Verify duplicate delivery rejection."""
    deliv = "deliv-unique-12345"
    # First delivery should return False (not duplicate)
    assert check_and_record_idempotency(deliv, "org/repo", 1, "sha123") is False
    # Second delivery with same ID should return True (is duplicate)
    assert check_and_record_idempotency(deliv, "org/repo", 1, "sha123") is True

def test_webhook_hmac_verification():
    """Verify HMAC SHA-256 signature verification."""
    body = b'{"action": "closed"}'
    secret = "my-test-secret"
    
    # Temporarily set secret
    original_secret = settings.github_webhook_secret
    settings.github_webhook_secret = secret

    try:
        mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        valid_header = f"sha256={mac}"
        invalid_header = "sha256=invalid00000000000000000000000000"

        assert verify_github_signature(body, valid_header) is True
        assert verify_github_signature(body, invalid_header) is False
        assert verify_github_signature(body, None) is False
    finally:
        settings.github_webhook_secret = original_secret

if __name__ == "__main__":
    test_pydantic_schema_validation()
    test_issue_reference_extraction()
    test_email_formatting()
    test_idempotency_cache()
    test_webhook_hmac_verification()
    print("All unit tests passed successfully!")
