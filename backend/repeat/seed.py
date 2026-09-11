"""Demo seed. Writes the learned "Bug email to Jira and Slack" workflow plus the
demonstration that taught it, and resets the sandbox apps. Runs in well under a second
so the demo can be reset between takes."""

from __future__ import annotations

import time

from .deps import get_deps
from .integrations.sandbox import SandboxGmail, SandboxJira, SandboxSlack
from .models import (
    Demonstration,
    EventKind,
    RecordedEvent,
    StepAction,
    Trigger,
    Variable,
    Workflow,
    WorkflowStep,
)

DEMO_WORKFLOW_ID = "wf_demo_bug_to_jira_slack"
DEMO_DEMONSTRATION_ID = "demo_seed_bug_report"


def demo_workflow(project_key: str, channel: str) -> Workflow:
    return Workflow(
        id=DEMO_WORKFLOW_ID,
        name="Bug email to Jira and Slack",
        demonstration_id=DEMO_DEMONSTRATION_ID,
        trigger=Trigger(
            description="A customer or teammate emails a bug report with steps to reproduce",
            subject_keywords=["bug", "broken", "error", "not working", "does nothing", "crash"],
            body_keywords=["steps to reproduce", "expected", "actual", "console"],
        ),
        variables=[
            Variable(name="email_subject", source="email.subject", description="Becomes the issue summary"),
            Variable(name="email_body", source="email.body", description="Becomes the issue description"),
            Variable(name="reporter", source="email.sender", description="Who reported it"),
            Variable(name="issue_key", source="step:create_issue.key", description="Jira key, e.g. DEMO-142"),
            Variable(name="issue_url", source="step:create_issue.url", description="Link to the issue"),
        ],
        steps=[
            WorkflowStep(
                id="s1_create_issue",
                action=StepAction.jira_create_issue,
                app="jira",
                title=f"Create {project_key} bug in Jira",
                fields={
                    "project": project_key,
                    "issue_type": "Bug",
                    "summary": "{email_subject}",
                    "description": "{email_body}",
                    "reporter_note": "Reported by {reporter} via email.",
                },
                produces=["issue_key", "issue_url"],
            ),
            WorkflowStep(
                id="s2_post_message",
                action=StepAction.slack_post_message,
                app="slack",
                title=f"Post to #{channel}",
                fields={
                    "channel": channel,
                    "text": ":beetle: New bug from {reporter}: *{email_subject}* → {issue_key} {issue_url}",
                },
                produces=["slack_ts"],
            ),
            WorkflowStep(
                id="s3_apply_label",
                action=StepAction.gmail_apply_label,
                app="gmail",
                title="Label email as handled",
                fields={"label": "REPEAT/handled"},
                produces=[],
            ),
        ],
        estimated_manual_seconds=270,
    )


def demo_demonstration(project_key: str, channel: str) -> Demonstration:
    t0 = time.time() * 1000 - 600_000
    ev = lambda kind, dt, app, url, title, **kw: RecordedEvent(  # noqa: E731
        kind=kind, ts=t0 + dt, app=app, url=url, title=title, **kw
    )
    gmail_url = "https://mail.google.com/mail/u/0/#inbox/18f2a"
    jira_url = "https://demo.atlassian.net/jira/software/projects/DEMO/boards/1"
    slack_url = "https://app.slack.com/client/T0DEMO/C0DEM0CHAN"
    subject = "Login page shows blank screen after password reset"
    return Demonstration(
        id=DEMO_DEMONSTRATION_ID,
        events=[
            ev(EventKind.navigate, 0, "gmail", gmail_url, subject + " - Gmail"),
            ev(EventKind.copy, 4_200, "gmail", gmail_url, subject + " - Gmail", text=subject),
            ev(EventKind.navigate, 9_000, "jira", jira_url, "DEMO board - Jira"),
            ev(EventKind.click, 10_500, "jira", jira_url, "DEMO board - Jira", target_text="Create", target_role="button"),
            ev(EventKind.paste, 13_000, "jira", jira_url, "Create issue - Jira", text=subject, field_label="Summary"),
            ev(EventKind.input, 13_100, "jira", jira_url, "Create issue - Jira", field_label="Summary", value=subject),
            ev(EventKind.navigate, 16_000, "gmail", gmail_url, subject + " - Gmail"),
            ev(EventKind.copy, 19_000, "gmail", gmail_url, subject + " - Gmail", text="After resetting my password the login page is blank. Console: Uncaught ReferenceError."),
            ev(EventKind.navigate, 22_000, "jira", jira_url, "Create issue - Jira"),
            ev(EventKind.paste, 24_000, "jira", jira_url, "Create issue - Jira", field_label="Description", text="After resetting my password the login page is blank."),
            ev(EventKind.click, 27_000, "jira", jira_url, "Create issue - Jira", target_text="Create", target_role="button"),
            ev(EventKind.navigate, 33_000, "slack", slack_url, f"#{channel} - Slack"),
            ev(EventKind.input, 41_000, "slack", slack_url, f"#{channel} - Slack", field_label="Message to #" + channel, value=f"New bug from Dana Whitfield: {subject} → {project_key}-141"),
            ev(EventKind.click, 42_500, "slack", slack_url, f"#{channel} - Slack", target_text="Send", target_role="button"),
        ],
        narration=[
            ev(EventKind.narration, 4_400, "gmail", gmail_url, "", transcript="The subject becomes the ticket summary."),
            ev(EventKind.narration, 19_500, "gmail", gmail_url, "", transcript="The body goes into the description, and the sender is the reporter."),
            ev(EventKind.narration, 41_500, "slack", slack_url, "", transcript="Then I tell the channel with the ticket key."),
        ],
        workflow_id=DEMO_WORKFLOW_ID,
    )


async def seed_demo(*, wipe: bool = True) -> dict:
    d = get_deps()
    s = d.settings
    if wipe:
        await d.store.wipe()
    wf = demo_workflow(s.jira_project_key, s.slack_channel)
    demo = demo_demonstration(s.jira_project_key, s.slack_channel)
    await d.store.save_workflow(wf)
    await d.store.save_demonstration(demo)
    for client in (d.integrations.jira, d.integrations.slack, d.integrations.gmail):
        if isinstance(client, (SandboxJira, SandboxSlack, SandboxGmail)):
            client.reset()
    await d.bus.publish("demo.reset", {"workflow_id": wf.id})
    return {"workflow": wf.model_dump(mode="json"), "stats": await d.store.stats()}
