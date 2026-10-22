"""
Simulation and Mock Webhook Testing Script.
Validates the PR Chronicler pipeline across 3 required scenarios:
  Case 1: Merged PR (action='closed', merged=True) -> Pipeline executes
  Case 2: Closed but unmerged PR (action='closed', merged=False) -> Ignored
  Case 3: Opened/Updated PR (action='opened', merged=False) -> Ignored
"""

import sys
import time
import json
import uuid
import argparse
import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
ENDPOINT = "/webhook/github"

# ANSI colors for readable terminal validation output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def make_payload(
    repo_full_name: str,
    pr_number: int,
    pr_title: str,
    action: str,
    merged: bool,
    body: str = "",
    author: str = "octocat"
) -> dict:
    """Generates a realistic GitHub pull_request webhook payload."""
    owner, _, repo_name = repo_full_name.partition("/")
    commit_sha = uuid.uuid4().hex[:12] if merged else None
    
    return {
        "action": action,
        "number": pr_number,
        "pull_request": {
            "id": 1000000 + pr_number,
            "number": pr_number,
            "state": "closed" if action == "closed" else "open",
            "title": pr_title,
            "body": body,
            "user": {
                "login": author,
                "html_url": f"https://github.com/{author}"
            },
            "html_url": f"https://github.com/{repo_full_name}/pull/{pr_number}",
            "diff_url": f"https://github.com/{repo_full_name}/pull/{pr_number}.diff",
            "patch_url": f"https://github.com/{repo_full_name}/pull/{pr_number}.patch",
            "merged": merged,
            "merge_commit_sha": commit_sha,
            "merged_at": "2026-10-22T10:00:00Z" if merged else None,
            "created_at": "2026-10-22T08:00:00Z"
        },
        "repository": {
            "name": repo_name or owner,
            "full_name": repo_full_name,
            "html_url": f"https://github.com/{repo_full_name}",
            "owner": {
                "login": owner
            }
        },
        "sender": {
            "login": author
        }
    }

def run_simulation(base_url: str, target_repo: str, target_pr: int):
    """Executes the test suite against the target FastAPI server."""
    webhook_url = f"{base_url.rstrip('/')}{ENDPOINT}"
    print(f"\n{BOLD}{CYAN}========================================================================{RESET}")
    print(f"{BOLD}{CYAN}      PR Chronicler & Learning Dispatcher - Validation Suite            {RESET}")
    print(f"{BOLD}{CYAN}========================================================================{RESET}")
    print(f"Target Endpoint:  {BOLD}{webhook_url}{RESET}")
    print(f"Hydration Target: {BOLD}{target_repo}#{target_pr}{RESET}\n")

    results = []

    with httpx.Client(timeout=60.0) as client:
        # Pre-check: Health endpoint
        try:
            health_resp = client.get(f"{base_url.rstrip('/')}/health")
            if health_resp.status_code == 200:
                print(f"[{GREEN}HEALTH OK{RESET}] Server is healthy. Config: {health_resp.json()}\n")
            else:
                print(f"[{YELLOW}WARN{RESET}] Server returned {health_resp.status_code} on /health\n")
        except Exception as exc:
            print(f"{RED}ERROR: Unable to connect to {base_url}: {exc}{RESET}")
            print("Please ensure the FastAPI server is running with:")
            print("  python -m uvicorn pr_chronicler.app:app --host 0.0.0.0 --port 8000")
            sys.exit(1)

        # ---------------------------------------------------------------------
        # Case 1: Merged PR (action='closed', merged=True)
        # Expected: HTTP 200, status='success', pipeline executes
        # ---------------------------------------------------------------------
        print(f"{BOLD}--- Case 1: Merged PR (action='closed', merged=True) ---{RESET}")
        case1_delivery = f"deliv-test-merged-{uuid.uuid4().hex[:8]}"
        case1_payload = make_payload(
            repo_full_name=target_repo,
            pr_number=target_pr,
            pr_title="Refactor internal session connection pooling and error resilience",
            action="closed",
            merged=True,
            body="Implements resilient connection backoff. Fixes #12 and Closes #42.",
            author="dev-contributor"
        )

        start_t = time.time()
        resp1 = client.post(
            webhook_url,
            json=case1_payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": case1_delivery,
                "Content-Type": "application/json"
            }
        )
        dur1 = time.time() - start_t
        resp1_json = resp1.json() if resp1.headers.get("content-type", "").startswith("application/json") else {}

        success1 = resp1.status_code == 200 and resp1_json.get("status") == "success"
        mark1 = f"{GREEN}PASSED{RESET}" if success1 else f"{RED}FAILED{RESET}"
        print(f"Status Code:      {resp1.status_code}")
        print(f"Response:         {json.dumps(resp1_json, indent=2)}")
        print(f"Observed Latency: {dur1:.2f}s")
        print(f"Result:           [{mark1}]\n")
        results.append(("Case 1: Merged PR (Pipeline Executes)", success1, f"{dur1:.2f}s"))

        # ---------------------------------------------------------------------
        # Case 2: Closed but Unmerged PR (action='closed', merged=False)
        # Expected: HTTP 200, status='ignored', reason mentions unmerged, LLM skipped
        # ---------------------------------------------------------------------
        print(f"{BOLD}--- Case 2: Closed But Unmerged PR (action='closed', merged=False) ---{RESET}")
        case2_delivery = f"deliv-test-unmerged-{uuid.uuid4().hex[:8]}"
        case2_payload = make_payload(
            repo_full_name=target_repo,
            pr_number=target_pr + 1,
            pr_title="Experimental prototype: rejected approach",
            action="closed",
            merged=False,
            body="Closing as abandoned.",
            author="test-user"
        )

        start_t = time.time()
        resp2 = client.post(
            webhook_url,
            json=case2_payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": case2_delivery,
                "Content-Type": "application/json"
            }
        )
        dur2 = time.time() - start_t
        resp2_json = resp2.json() if resp2.headers.get("content-type", "").startswith("application/json") else {}

        success2 = resp2.status_code == 200 and resp2_json.get("status") == "ignored"
        mark2 = f"{GREEN}PASSED{RESET}" if success2 else f"{RED}FAILED{RESET}"
        print(f"Status Code:      {resp2.status_code}")
        print(f"Response:         {json.dumps(resp2_json, indent=2)}")
        print(f"Observed Latency: {dur2:.2f}s")
        print(f"Result:           [{mark2}]\n")
        results.append(("Case 2: Closed Unmerged PR (Ignored)", success2, f"{dur2:.2f}s"))

        # ---------------------------------------------------------------------
        # Case 3: Opened / Synchronized PR (action='opened', merged=False)
        # Expected: HTTP 200, status='ignored', reason mentions non-closed action, LLM skipped
        # ---------------------------------------------------------------------
        print(f"{BOLD}--- Case 3: Opened/Updated PR (action='opened', merged=False) ---{RESET}")
        case3_delivery = f"deliv-test-opened-{uuid.uuid4().hex[:8]}"
        case3_payload = make_payload(
            repo_full_name=target_repo,
            pr_number=target_pr + 2,
            pr_title="Draft work in progress: new feature",
            action="opened",
            merged=False,
            body="Initial commit for review.",
            author="junior-dev"
        )

        start_t = time.time()
        resp3 = client.post(
            webhook_url,
            json=case3_payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": case3_delivery,
                "Content-Type": "application/json"
            }
        )
        dur3 = time.time() - start_t
        resp3_json = resp3.json() if resp3.headers.get("content-type", "").startswith("application/json") else {}

        success3 = resp3.status_code == 200 and resp3_json.get("status") == "ignored"
        mark3 = f"{GREEN}PASSED{RESET}" if success3 else f"{RED}FAILED{RESET}"
        print(f"Status Code:      {resp3.status_code}")
        print(f"Response:         {json.dumps(resp3_json, indent=2)}")
        print(f"Observed Latency: {dur3:.2f}s")
        print(f"Result:           [{mark3}]\n")
        results.append(("Case 3: Opened PR Event (Ignored)", success3, f"{dur3:.2f}s"))

        # ---------------------------------------------------------------------
        # Optional Case 4: Idempotency Verification (duplicate delivery)
        # ---------------------------------------------------------------------
        print(f"{BOLD}--- Case 4: Idempotency Re-delivery Test (Same Delivery ID) ---{RESET}")
        start_t = time.time()
        resp4 = client.post(
            webhook_url,
            json=case1_payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": case1_delivery,
                "Content-Type": "application/json"
            }
        )
        dur4 = time.time() - start_t
        resp4_json = resp4.json() if resp4.headers.get("content-type", "").startswith("application/json") else {}
        success4 = resp4.status_code == 200 and resp4_json.get("status") == "ignored" and "Duplicate" in resp4_json.get("message", "")
        mark4 = f"{GREEN}PASSED{RESET}" if success4 else f"{RED}FAILED{RESET}"
        print(f"Status Code:      {resp4.status_code}")
        print(f"Response:         {json.dumps(resp4_json, indent=2)}")
        print(f"Result:           [{mark4}]\n")
        results.append(("Case 4: Duplicate Webhook Idempotency", success4, f"{dur4:.2f}s"))

    # Print Summary Table
    print(f"{BOLD}{CYAN}========================================================================{RESET}")
    print(f"{BOLD}{CYAN}                       VALIDATION SUMMARY REPORT                        {RESET}")
    print(f"{BOLD}{CYAN}========================================================================{RESET}")
    all_passed = True
    for name, passed, lat in results:
        status_str = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        if not passed:
            all_passed = False
        print(f"• {name:<42} : [{status_str}] (Latency: {lat})")

    print(f"{BOLD}{CYAN}========================================================================{RESET}")
    if all_passed:
        print(f"{BOLD}{GREEN}ALL 4 TEST SCENARIOS PASSED SUCCESSFULLY!{RESET}\n")
    else:
        print(f"{BOLD}{RED}SOME SCENARIOS FAILED. Check logs for details.{RESET}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate GitHub PR Webhooks for PR Chronicler.")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="Base URL of PR Chronicler server")
    parser.add_argument("--repo", default="octocat/Hello-World", help="Public GitHub repository (owner/repo)")
    parser.add_argument("--pr", type=int, default=12, help="Historical PR number for context hydration")
    args = parser.parse_args()

    run_simulation(base_url=args.url, target_repo=args.repo, target_pr=args.pr)
