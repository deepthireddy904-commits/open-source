"""
SMTP Email Dispatcher Module.
Formats and dispatches learning dispatches asynchronously with HTML and Plain Text formatting.
Runs smtplib in a worker thread via asyncio.to_thread to avoid blocking async event loops.
"""

import asyncio
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Dict, Any

from pr_chronicler.logger import logger
from pr_chronicler.config import settings
from pr_chronicler.schemas import PRChroniclerOutput

class EmailDispatcher:
    """Asynchronous SMTP Email Dispatcher for PR Chronicler learnings."""

    def __init__(self):
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_user = settings.smtp_email
        self.smtp_password = settings.smtp_app_password
        self.recipient = settings.recipient_email
        self.use_tls = settings.smtp_use_tls
        self.dry_run = settings.dry_run_smtp

    def format_plain_text(
        self,
        output: PRChroniclerOutput,
        repo: str,
        pull_number: int,
        pr_title: str,
        author: str,
        diff_length: int
    ) -> str:
        """Constructs clean plain-text version of the learning dispatch."""
        learnings_txt = ""
        for idx, item in enumerate(output.key_learnings, 1):
            learnings_txt += f"""
[{idx}] Category: {item.category}
    Insight:  {item.insight}
    Evidence: {item.evidence}
"""

        return f"""================================================================================
PR CHRONICLER & LEARNING DISPATCH
================================================================================
Repository:    {repo}
PR Number:     #{pull_number}
PR Title:      {pr_title}
Author:        @{author}
Diff Length:   {diff_length:,} characters

--------------------------------------------------------------------------------
1. ISSUE DETAILS
--------------------------------------------------------------------------------
{output.issue_details}

--------------------------------------------------------------------------------
2. EXECUTION SUMMARY
--------------------------------------------------------------------------------
{output.execution_summary}

--------------------------------------------------------------------------------
3. KEY LEARNINGS (EVIDENCE-BASED)
--------------------------------------------------------------------------------
{learnings_txt.strip()}

================================================================================
Generated automatically by GenAI 101 PR Chronicler
================================================================================
"""

    def format_html(
        self,
        output: PRChroniclerOutput,
        repo: str,
        pull_number: int,
        pr_title: str,
        author: str,
        diff_length: int
    ) -> str:
        """Constructs an elegant, responsive HTML email version."""
        learning_cards_html = ""
        for idx, item in enumerate(output.key_learnings, 1):
            learning_cards_html += f"""
            <div style="background-color: #f8fafc; border-left: 4px solid #3b82f6; padding: 14px 18px; margin-bottom: 14px; border-radius: 4px;">
                <div style="font-weight: 700; color: #1e3a8a; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;">
                    {idx}. {item.category}
                </div>
                <div style="margin: 8px 0; color: #334155; font-size: 15px; line-height: 1.5;">
                    <strong>Insight:</strong> {item.insight}
                </div>
                <div style="color: #64748b; font-size: 13px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; background-color: #f1f5f9; padding: 6px 10px; border-radius: 4px; display: inline-block;">
                    <strong>Evidence:</strong> {item.evidence}
                </div>
            </div>
            """

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PR Chronicler: {repo}#{pull_number}</title>
</head>
<body style="margin:0; padding:0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f1f5f9; padding: 24px 0;">
        <tr>
            <td align="center">
                <table width="640" cellpadding="0" cellspacing="0" style="max-width: 640px; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 24px 28px; color: #ffffff;">
                            <div style="font-size: 12px; letter-spacing: 1.5px; text-transform: uppercase; color: #94a3b8; font-weight: 600;">
                                GenAI 101 &bull; Automated PR Chronicler
                            </div>
                            <h1 style="margin: 8px 0 4px 0; font-size: 22px; font-weight: 700; color: #ffffff;">
                                {repo} <span style="color: #60a5fa;">#{pull_number}</span>
                            </h1>
                            <div style="font-size: 15px; color: #cbd5e1;">
                                {pr_title}
                            </div>
                            <div style="margin-top: 12px; font-size: 12px; color: #94a3b8;">
                                Merged by <strong>@{author}</strong> &bull; Diff: <strong>{diff_length:,} chars</strong>
                            </div>
                        </td>
                    </tr>

                    <!-- Body Content -->
                    <tr>
                        <td style="padding: 28px;">
                            <!-- Section 1: Issue Details -->
                            <div style="margin-bottom: 26px;">
                                <h2 style="font-size: 16px; color: #0f172a; margin-top: 0; margin-bottom: 10px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px;">
                                    📌 1. Issue Details
                                </h2>
                                <p style="font-size: 14px; line-height: 1.6; color: #334155; margin: 0;">
                                    {output.issue_details}
                                </p>
                            </div>

                            <!-- Section 2: Execution Summary -->
                            <div style="margin-bottom: 26px;">
                                <h2 style="font-size: 16px; color: #0f172a; margin-top: 0; margin-bottom: 10px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px;">
                                    ⚙️ 2. Execution Summary
                                </h2>
                                <p style="font-size: 14px; line-height: 1.6; color: #334155; margin: 0;">
                                    {output.execution_summary}
                                </p>
                            </div>

                            <!-- Section 3: Key Learnings -->
                            <div style="margin-bottom: 20px;">
                                <h2 style="font-size: 16px; color: #0f172a; margin-top: 0; margin-bottom: 12px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px;">
                                    💡 3. Key Learnings (Evidence-Based)
                                </h2>
                                {learning_cards_html}
                            </div>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 16px 28px; text-align: center; font-size: 12px; color: #64748b;">
                            Dispatched via automated GitHub Webhook &amp; LangChain LCEL pipeline.
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
        return html

    def _send_sync(self, subject: str, plain_body: str, html_body: str, recipient: str) -> bool:
        """Synchronous SMTP transmission executed inside a worker thread."""
        sender = self.smtp_user or "pr-chronicler@localhost"

        # Check for dry run or unconfigured credentials
        if self.dry_run or not self.smtp_user or not self.smtp_password or self.smtp_password.startswith("your_"):
            logger.info(
                f"[SMTP Simulation] Dry-run or unconfigured SMTP credentials. "
                f"Simulating delivery to <{recipient}> with subject: '{subject}'"
            )
            logger.info(f"[SMTP Simulation] Headers: From={sender}, To={recipient}, Host={self.smtp_host}:{self.smtp_port}")
            logger.info("[SMTP Simulation] Delivery status: SIMULATED_DELIVERY_SUCCESS (250 OK)")
            return True

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient

        # Attach plain text and HTML parts
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        start_time = time.time()
        logger.info(f"[SMTP Dispatch] Connecting to {self.smtp_host}:{self.smtp_port} for delivery to <{recipient}>...")
        try:
            if self.smtp_port == 465:
                # SSL connection
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                # Standard connection with STARTTLS
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)

            latency = time.time() - start_time
            logger.info(
                f"[SMTP Dispatch] Email successfully delivered to <{recipient}> in {latency:.2f}s! Status: 250 OK"
            )
            return True
        except Exception as exc:
            logger.error(
                f"[SMTP Dispatch] Failed to send email to <{recipient}> via {self.smtp_host}:{self.smtp_port}: {exc}",
                exc_info=True
            )
            return False

    async def dispatch(
        self,
        output: PRChroniclerOutput,
        repo: str,
        pull_number: int,
        pr_title: str,
        author: str,
        diff_length: int,
        target_email: Optional[str] = None
    ) -> bool:
        """
        Dispatches learning dispatch email asynchronously using asyncio.to_thread.
        """
        recipient = target_email or self.recipient or self.smtp_user or "recipient@example.com"
        subject = f"[PR Chronicler] Learnings from {repo}#{pull_number}: {pr_title}"

        plain_text = self.format_plain_text(
            output=output,
            repo=repo,
            pull_number=pull_number,
            pr_title=pr_title,
            author=author,
            diff_length=diff_length
        )

        html_text = self.format_html(
            output=output,
            repo=repo,
            pull_number=pull_number,
            pr_title=pr_title,
            author=author,
            diff_length=diff_length
        )

        # Offload synchronous smtplib to background worker thread
        success = await asyncio.to_thread(
            self._send_sync,
            subject=subject,
            plain_body=plain_text,
            html_body=html_text,
            recipient=recipient
        )

        return success
