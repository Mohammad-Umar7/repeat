"""Integration factory. Demo mode -> sandbox; otherwise live clients per configured app.

Partial configuration is allowed: e.g. live Jira + live Slack + sandbox Gmail. Each
app falls back to its sandbox independently and the /health endpoint reports which.
"""

from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import (
    ActionResult,
    GmailClient,
    IntegrationError,
    Integrations,
    JiraClient,
    SlackClient,
    VerifyResult,
)
from .sandbox import SandboxGmail, SandboxJira, SandboxSlack

__all__ = [
    "ActionResult",
    "GmailClient",
    "IntegrationError",
    "Integrations",
    "JiraClient",
    "SlackClient",
    "VerifyResult",
    "get_integrations",
    "integration_modes",
]


@lru_cache
def get_integrations() -> Integrations:
    s = get_settings()
    if s.repeat_demo_mode:
        return Integrations(
            jira=SandboxJira(s.jira_project_key),
            slack=SandboxSlack(s.slack_channel),
            gmail=SandboxGmail(s.gmail_handled_label),
            mode="sandbox",
        )

    jira: JiraClient
    slack: SlackClient
    gmail: GmailClient
    if s.jira_configured:
        from .jira import LiveJiraClient

        jira = LiveJiraClient(
            base_url=s.jira_base_url or "",
            email=s.jira_email or "",
            api_token=s.jira_api_token or "",
            project_key=s.jira_project_key,
            issue_type=s.jira_issue_type,
        )
    else:
        jira = SandboxJira(s.jira_project_key)
    if s.slack_configured:
        from .slack import LiveSlackClient

        slack = LiveSlackClient(bot_token=s.slack_bot_token or "")
    else:
        slack = SandboxSlack(s.slack_channel)
    if s.gmail_credentials_file.exists():
        from .gmail import LiveGmailClient

        gmail = LiveGmailClient(
            credentials_file=s.gmail_credentials_file,
            token_file=s.gmail_token_file,
            handled_label=s.gmail_handled_label,
        )
    else:
        gmail = SandboxGmail(s.gmail_handled_label)
    all_live = s.jira_configured and s.slack_configured and s.gmail_credentials_file.exists()
    return Integrations(jira=jira, slack=slack, gmail=gmail, mode="live" if all_live else "mixed")


def integration_modes(i: Integrations) -> dict[str, str]:
    return {
        "jira": "sandbox" if isinstance(i.jira, SandboxJira) else "live",
        "slack": "sandbox" if isinstance(i.slack, SandboxSlack) else "live",
        "gmail": "sandbox" if isinstance(i.gmail, SandboxGmail) else "live",
    }
