"""Marketing email to our own users: who opted out, who must never be mailed, and a log of what was sent."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id, utcnow


class MarketingPref(Base, TimestampMixin):
    """One row per person we have marketed to (made on the first send). `token` is the secret in their unsubscribe link."""

    __tablename__ = "marketing_prefs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="")  # link | one_click | operator


class MarketingSuppression(Base, TimestampMixin):
    """Addresses that must not get marketing mail whatever their preference says (hard bounce, spam complaint)."""

    __tablename__ = "marketing_suppressions"
    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    reason: Mapped[str] = mapped_column(String(100), default="")


class MarketingSend(Base):
    """Every marketing email we sent or decided not to send. Drives the frequency cap, the daily cap, and "why did I get this?"."""

    __tablename__ = "marketing_sends"
    __table_args__ = (UniqueConstraint("idempotency_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="")  # campaign | workflow | test
    ref: Mapped[str] = mapped_column(String(64), default="")  # the campaign or workflow it came from
    subject: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), index=True)  # sent | skipped | failed | dry_run
    skip_reason: Mapped[str] = mapped_column(String(40), default="")
    idempotency_key: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )  # a retry of the same send does nothing
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # tracking: the secret in this email's open pixel and button link, where the button really goes, and what came back
    track_token: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    click_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    click_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MarketingSegment(Base, TimestampMixin):
    """A saved group of users, defined by rules and worked out fresh each time it is used."""

    __tablename__ = "marketing_segments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    rules: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # {"match": "all"|"any", "conditions": [{field, op, value}]}
    created_by: Mapped[str] = mapped_column(String(320), default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MarketingCopy(Base, TimestampMixin):
    """One piece of email copy. Its words live in versions, so an email already sent can always be traced to what it said."""

    __tablename__ = "marketing_copies"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(
        String(20), default="product"
    )  # onboarding | activation | billing | win_back | product
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(320), default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MarketingCopyVersion(Base):
    __tablename__ = "marketing_copy_versions"
    __table_args__ = (UniqueConstraint("copy_id", "version"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    copy_id: Mapped[str] = mapped_column(ForeignKey("marketing_copies.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(200))
    preheader: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text)
    button_label: Mapped[str] = mapped_column(String(60), default="")
    button_url: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[str] = mapped_column(String(320), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MarketingCampaign(Base, TimestampMixin):
    """A one-off send: one copy (a pinned version) to one segment, now or at a time."""

    __tablename__ = "marketing_campaigns"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    segment_id: Mapped[str] = mapped_column(ForeignKey("marketing_segments.id"))
    copy_id: Mapped[str] = mapped_column(ForeignKey("marketing_copies.id"))
    copy_version: Mapped[int] = mapped_column(Integer)  # the words that go out never change after scheduling
    rules: Mapped[dict] = mapped_column(JSON, default=dict)  # the segment's rules as they were when it was scheduled
    # draft | scheduled | sending | sent | cancelled
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)
    send_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audience: Mapped[int] = mapped_column(Integer, default=0)  # who was picked when sending started
    created_by: Mapped[str] = mapped_column(String(320), default="")
    scheduled_by: Mapped[str] = mapped_column(String(320), default="")
    # A/B test of the subject line (subject_b empty = no test). split: everyone is split between A and B. winner: a small test
    # group is split, and after wait_hours the better subject (by metric) goes to everyone else.
    subject_b: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ab_mode: Mapped[str] = mapped_column(String(8), default="split", server_default="split")
    test_percent: Mapped[int] = mapped_column(
        Integer, default=20, server_default="20"
    )  # winner mode: share who get the test
    wait_hours: Mapped[int] = mapped_column(
        Integer, default=4, server_default="4"
    )  # winner mode: how long to wait for results
    metric: Mapped[str] = mapped_column(String(8), default="opens", server_default="opens")  # opens | clicks
    winner: Mapped[str | None] = mapped_column(String(1), nullable=True)
    decide_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MarketingRecipient(Base):
    """One person in one campaign. Made when sending starts, so the list is fixed and a crash resumes where it stopped."""

    __tablename__ = "marketing_recipients"
    __table_args__ = (UniqueConstraint("campaign_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("marketing_campaigns.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(
        String(10), default="pending", index=True
    )  # pending | held | sent | skipped | failed
    reason: Mapped[str] = mapped_column(String(40), default="")
    variant: Mapped[str] = mapped_column(String(1), default="", server_default="")  # A | B (empty: not decided yet)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MarketingWorkflow(Base, TimestampMixin):
    """A sequence sent to people as they come to match a segment: emails and waits, with an optional goal that ends it early."""

    __tablename__ = "marketing_workflows"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(10), default="draft", index=True)  # draft | active | paused | stopped
    trigger_segment_id: Mapped[str] = mapped_column(ForeignKey("marketing_segments.id"))
    rules: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # who gets in: the segment's rules, fixed when it was switched on
    steps: Mapped[list] = mapped_column(
        JSON, default=list
    )  # [{type: wait|email, ...}], email versions fixed when switched on
    goal_segment_id: Mapped[str | None] = mapped_column(ForeignKey("marketing_segments.id"), nullable=True)
    goal_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # anyone who matches this leaves the workflow
    settings: Mapped[dict] = mapped_column(JSON, default=dict)  # sending hours
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(320), default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MarketingEnrollment(Base):
    """One person's place in one workflow."""

    __tablename__ = "marketing_enrollments"
    __table_args__ = (UniqueConstraint("workflow_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("marketing_workflows.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | completed | exited
    exit_reason: Mapped[str] = mapped_column(String(40), default="")
    step_index: Mapped[int] = mapped_column(Integer, default=0)  # the next step to run
    attempts: Mapped[int] = mapped_column(Integer, default=0)  # tries at the current step
    runs: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )  # how many times they have been through (re-entry)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserEvent(Base):
    """Something a person did in the product that no other table records (used by marketing segments). Names are in services/user_events.py."""

    __tablename__ = "user_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
