"""Import every ORM model so SQLAlchemy can resolve cross-model relationships."""

from app.models.admin_session import AdminSession
from app.models.admin_user import AdminRole, AdminUser
from app.models.ai_regenerate import AiRegenerateLog
from app.models.api_key import APIKey
from app.models.api_usage_log import APIUsageLog
from app.models.audit_log import ActorType, AuditLog
from app.models.auth_revocation import AuthRevocation
from app.models.best_time_to_post import BestTimeToPost
from app.models.bulk_job import BulkJob, BulkJobStatus
from app.models.clip import Clip
from app.models.clip_performance import ClipPerformance
from app.models.clip_template import ClipTemplate
from app.models.content_moderation import ContentModeration, ModerationStatus
from app.models.copyright_check import CopyrightAction, CopyrightCheck, CopyrightStatus
from app.models.credit_transaction import CreditTransaction, CreditTransactionType
from app.models.download_log import DownloadAttempt, TaskLog
from app.models.download_runner import DownloadRunner, RunnerJob
from app.models.encrypted_secret import EncryptedSecret
from app.models.gdpr_request import GDPRRequest, GDPRRequestStatus, GDPRRequestType
from app.models.invoice import Invoice, InvoiceStatus
from app.models.multi_platform import MultiPlatformJob, PlatformOutput, PlatformPreset
from app.models.pricing_plan import PricingPlan
from app.models.platform_setting import PlatformSetting
from app.models.security_event import EventType, RiskLevel, SecurityEvent
from app.models.task import Task, TaskStatus
from app.models.task_asset import TaskAsset
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import AuthProvider, User
from app.models.user_api_key import UserAPIKey
from app.models.user_profile import PlanType, UserProfile
from app.models.user_subscription import SubscriptionStatus, UserSubscription
from app.models.viral_prediction_history import ViralPredictionHistory
from app.models.webhook_subscription import WebhookSubscription
from app.models.worker_instance import WorkerInstance
from app.models.youtube_credential import YouTubeCredential
from app.models.ytdlp_cookie import (
    COOKIE_STATUS_ACTIVE,
    COOKIE_STATUS_DISABLED,
    COOKIE_STATUS_EXPIRED,
    YtdlpCookie,
)

__all__ = [
    "AdminSession", "AdminRole", "AdminUser", "AiRegenerateLog", "APIKey", "APIUsageLog", "ActorType",
    "AuditLog", "AuthRevocation", "BestTimeToPost", "BulkJob", "BulkJobStatus", "Clip", "ClipPerformance",
    "ClipTemplate", "ContentModeration", "ModerationStatus", "CopyrightCheck", "CopyrightAction",
    "CopyrightStatus", "CreditTransaction", "CreditTransactionType",
    "EncryptedSecret", "GDPRRequest", "GDPRRequestStatus", "GDPRRequestType", "Invoice",
    "InvoiceStatus", "MultiPlatformJob", "PlatformOutput", "PlatformPreset", "PricingPlan",
    "PlatformSetting",
    "SecurityEvent", "EventType", "RiskLevel", "Task", "TaskStatus", "Transaction",
    "TransactionStatus", "AuthProvider", "User", "UserAPIKey", "PlanType", "UserProfile",
    "SubscriptionStatus", "UserSubscription", "ViralPredictionHistory", "WebhookSubscription",
    "YouTubeCredential",
    "WorkerInstance",
    "YtdlpCookie", "COOKIE_STATUS_ACTIVE", "COOKIE_STATUS_EXPIRED", "COOKIE_STATUS_DISABLED",
    "DownloadAttempt", "TaskLog", "DownloadRunner", "RunnerJob", "TaskAsset",
]