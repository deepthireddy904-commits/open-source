"""
GitHub API Context Hydration Client.
Handles asynchronous fetching of PR diffs, file changes, and linked issues.
"""

import re
import httpx
from typing import List, Dict, Any, Optional, Tuple
from pr_chronicler.logger import logger
from pr_chronicler.config import settings

# Regex to detect issue closing keywords in PR body / title
ISSUE_REGEX = re.compile(
    r"(?i)\b(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+(?:https?://github\.com/[\w.-]+/[\w.-]+/issues/|#)(\d+)\b"
)

class GitHubClient:
    """Asynchronous client for hydrating PR metadata, diffs, and linked issues."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.github_token
        self.base_url = "https://api.github.com"

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "PR-Chronicler-GenAI101",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def extract_issue_references(self, text: Optional[str]) -> List[int]:
        """
        Extracts linked issue numbers from PR body or title.
        Matches patterns like 'Fixes #12', 'Closes #45', 'Resolves #89',
        as well as full GitHub issue URLs.
        """
        if not text:
            return []
        matches = ISSUE_REGEX.findall(text)
        # Deduplicate while preserving order
        unique_issues = []
        for m in matches:
            num = int(m)
            if num not in unique_issues:
                unique_issues.append(num)
        return unique_issues

    async def fetch_pr_files(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        max_pages: int = 5
    ) -> Tuple[List[Dict[str, Any]], str, int]:
        """
        Fetches changed files and patch snippets from:
        GET /repos/{owner}/{repo}/pulls/{pull_number}/files

        Handles pagination and missing patches.
        Returns:
            - files_summary: List of metadata dicts per changed file
            - combined_patch: Formatted patch string of changes
            - total_diff_length: Total character length of retrieved diff/patch content
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/files"
        headers = self._get_headers()
        files_summary: List[Dict[str, Any]] = []
        patch_segments: List[str] = []
        total_diff_length = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1
            while page <= max_pages:
                logger.info(
                    f"[GitHub API] Fetching PR files page {page} for {owner}/{repo}#{pull_number}"
                )
                try:
                    response = await client.get(
                        url,
                        headers=headers,
                        params={"per_page": 100, "page": page}
                    )
                except httpx.RequestError as exc:
                    logger.error(
                        f"[GitHub API] Network failure requesting files for {owner}/{repo}#{pull_number}: {exc}"
                    )
                    break

                # Handle response codes
                if response.status_code == 401:
                    logger.error(
                        f"[GitHub API] 401 Unauthorized for {owner}/{repo}#{pull_number}. Check GITHUB_TOKEN."
                    )
                    break
                elif response.status_code == 403:
                    rate_limit_reset = response.headers.get("x-ratelimit-reset", "unknown")
                    logger.warning(
                        f"[GitHub API] 403 Forbidden / Rate Limited for {owner}/{repo}#{pull_number}. Reset: {rate_limit_reset}"
                    )
                    break
                elif response.status_code == 404:
                    logger.warning(
                        f"[GitHub API] 404 Not Found for {owner}/{repo}#{pull_number} files endpoint."
                    )
                    break
                elif response.status_code != 200:
                    logger.error(
                        f"[GitHub API] Unexpected status {response.status_code} fetching files: {response.text[:200]}"
                    )
                    break

                data = response.json()
                if not isinstance(data, list) or len(data) == 0:
                    break

                for item in data:
                    filename = item.get("filename", "unknown")
                    status = item.get("status", "modified")
                    additions = item.get("additions", 0)
                    deletions = item.get("deletions", 0)
                    patch = item.get("patch")

                    files_summary.append({
                        "filename": filename,
                        "status": status,
                        "additions": additions,
                        "deletions": deletions,
                        "has_patch": patch is not None
                    })

                    file_header = f"--- {filename} ({status}, +{additions}/-{deletions}) ---"
                    if patch:
                        patch_len = len(patch)
                        total_diff_length += patch_len
                        patch_segments.append(f"{file_header}\n{patch}")
                    else:
                        patch_segments.append(f"{file_header}\n[Patch unavailable: binary or oversized file]")

                # If fewer than 100 items returned, this was the last page
                if len(data) < 100:
                    break
                page += 1

        combined_patch = "\n\n".join(patch_segments)
        logger.info(
            f"[GitHub API] Hydration complete for {owner}/{repo}#{pull_number}: "
            f"{len(files_summary)} files, total diff character length: {total_diff_length}"
        )

        # Enforce max diff character length safeguard if configured
        if settings.max_diff_characters and len(combined_patch) > settings.max_diff_characters:
            logger.info(
                f"[GitHub API] Diff truncated from {len(combined_patch)} to {settings.max_diff_characters} chars for LLM context"
            )
            combined_patch = combined_patch[:settings.max_diff_characters] + "\n\n...[Diff truncated due to size limits]..."

        return files_summary, combined_patch, total_diff_length

    async def fetch_linked_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves linked issue details via:
        GET /repos/{owner}/{repo}/issues/{issue_number}
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}"
        headers = self._get_headers()

        logger.info(f"[GitHub API] Fetching linked issue {owner}/{repo}#{issue_number}")
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.get(url, headers=headers)
            except httpx.RequestError as exc:
                logger.error(
                    f"[GitHub API] Network error fetching issue #{issue_number}: {exc}"
                )
                return None

            if response.status_code == 200:
                data = response.json()
                logger.info(f"[GitHub API] Successfully retrieved issue #{issue_number}: '{data.get('title')}'")
                return {
                    "issue_number": issue_number,
                    "title": data.get("title", ""),
                    "body": data.get("body", "") or "No issue description provided.",
                    "labels": [lbl.get("name") for lbl in data.get("labels", []) if isinstance(lbl, dict)],
                    "state": data.get("state", "closed"),
                    "html_url": data.get("html_url", ""),
                }
            elif response.status_code == 404:
                logger.warning(f"[GitHub API] Linked issue #{issue_number} not found (404)")
            elif response.status_code == 403:
                logger.warning(f"[GitHub API] Rate limit reached fetching issue #{issue_number}")
            else:
                logger.warning(
                    f"[GitHub API] HTTP {response.status_code} fetching issue #{issue_number}: {response.text[:150]}"
                )

            return None

    async def hydrate_context(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        pr_title: str,
        pr_body: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Orchestrates full context hydration:
        1. Extract issue references from PR body
        2. Hydrate linked issue descriptions (or record absence)
        3. Hydrate changed files and diffs
        4. Calculate total diff character length
        """
        # Step 1: Detect issue references
        issue_numbers = self.extract_issue_references(pr_body)
        linked_issues: List[Dict[str, Any]] = []

        if issue_numbers:
            logger.info(f"[Hydration] Found issue reference(s) in PR body: #{issue_numbers}")
            for num in issue_numbers[:3]:  # Hydrate up to top 3 linked issues
                issue_data = await self.fetch_linked_issue(owner, repo, num)
                if issue_data:
                    linked_issues.append(issue_data)
        else:
            logger.info(f"[Hydration] No linked issue references found in PR body for {owner}/{repo}#{pull_number}")

        # Step 2: Hydrate files and diff
        files_summary, diff_content, total_diff_length = await self.fetch_pr_files(owner, repo, pull_number)

        # Build issue context string
        if linked_issues:
            issue_context_str = "\n\n".join([
                f"### Linked Issue #{iss['issue_number']}: {iss['title']}\n"
                f"Labels: {', '.join(iss['labels']) or 'None'}\n"
                f"Description:\n{iss['body']}"
                for iss in linked_issues
            ])
        else:
            issue_context_str = (
                "No linked GitHub issue was referenced in the PR body. "
                f"PR Description provided by author:\n{pr_body or 'No PR body description provided.'}"
            )

        return {
            "owner": owner,
            "repo": repo,
            "pull_number": pull_number,
            "pr_title": pr_title,
            "pr_body": pr_body or "",
            "has_linked_issue": len(linked_issues) > 0,
            "linked_issues": linked_issues,
            "issue_context": issue_context_str,
            "files_summary": files_summary,
            "diff_content": diff_content,
            "total_diff_length": total_diff_length,
        }
