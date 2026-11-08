"""
Feature Gate - Plan-based feature access control
Determines which editing features are available per subscription plan.
"""
from typing import List, Dict, Set
from app.models.user_profile import UserProfile, PlanType

PLAN_HIERARCHY: Dict[str, int] = {
    "free": 0,
    "standar": 1,
    "pro": 2,
    "team": 3,
}

# Feature key -> minimum plan required
FEATURE_MIN_PLAN: Dict[str, str] = {
    # Free features
    "smart_crop_9x16": "free",
    "auto_subtitle": "free",
    
    # Standar features
    "contrast_brightness": "standar",
    "auto_zoom_face": "standar",
    "auto_zoom_audio": "standar",
    "blur_background": "standar",
    "karaoke_subtitle": "standar",
    "silence_removal": "standar",
    "background_music": "standar",
    "title_card": "standar",
    "progress_bar": "standar",
    "youtube_upload": "standar",
    
    # Pro features
    "object_tracking": "pro",
    "ken_burns": "pro",
    "animated_caption": "pro",
    "multi_language_subtitle": "pro",
    "audio_ducking": "pro",
    "noise_reduction": "pro",
    "voice_enhancement": "pro",
    "sound_effects": "pro",
    "color_grading": "pro",
    "video_filters": "pro",
    "speed_ramp": "pro",
    "transitions": "pro",
    "custom_watermark": "pro",
    "sticker_overlay": "pro",
    "intro_outro": "pro",
    "end_screen": "pro",
    "viral_scoring": "pro",
    "ai_metadata": "pro",
    "thumbnail_ai": "pro",
}

# Credit cost per feature
FEATURE_CREDIT_COST: Dict[str, float] = {
    "smart_crop_9x16": 0,
    "auto_subtitle": 0,
    "contrast_brightness": 0,
    "auto_zoom_face": 1,
    "auto_zoom_audio": 1,
    "blur_background": 1,
    "karaoke_subtitle": 1,
    "silence_removal": 1,
    "background_music": 1,
    "title_card": 0.5,
    "progress_bar": 0.5,
    "youtube_upload": 1,
    "object_tracking": 2,
    "ken_burns": 1,
    "animated_caption": 1,
    "multi_language_subtitle": 1,
    "audio_ducking": 1,
    "noise_reduction": 1,
    "voice_enhancement": 1,
    "sound_effects": 0.5,
    "color_grading": 1,
    "video_filters": 1,
    "speed_ramp": 1,
    "transitions": 0.5,
    "custom_watermark": 0.5,
    "sticker_overlay": 0.5,
    "intro_outro": 1,
    "end_screen": 0.5,
    "viral_scoring": 2,
    "ai_metadata": 1,
    "thumbnail_ai": 2,
}

# Base credit cost per task
BASE_TASK_CREDIT_COST = 1
EXTRA_CLIP_CREDIT_COST = 0.5


class FeatureGate:
    """Check if a user can access a feature based on their plan."""
    
    @staticmethod
    def get_user_plan_level(plan_type: str) -> int:
        return PLAN_HIERARCHY.get(plan_type, 0)
    
    @staticmethod
    def is_feature_available(plan_type: str, feature_key: str) -> bool:
        min_plan = FEATURE_MIN_PLAN.get(feature_key)
        if min_plan is None:
            return True  # Unknown feature, allow by default
        return PLAN_HIERARCHY.get(plan_type, 0) >= PLAN_HIERARCHY.get(min_plan, 99)
    
    @staticmethod
    def get_locked_features(plan_type: str, requested_features: List[str]) -> List[str]:
        user_level = PLAN_HIERARCHY.get(plan_type, 0)
        locked = []
        for feature in requested_features:
            min_plan = FEATURE_MIN_PLAN.get(feature)
            if min_plan and PLAN_HIERARCHY.get(min_plan, 99) > user_level:
                locked.append(feature)
        return locked
    
    @staticmethod
    def get_credit_cost(feature_key: str) -> float:
        return FEATURE_CREDIT_COST.get(feature_key, 0)
    
    @staticmethod
    def calculate_task_credits(editing_options: dict, clip_count: int = 1) -> float:
        """Calculate total credit cost for a task."""
        total = BASE_TASK_CREDIT_COST
        total += EXTRA_CLIP_CREDIT_COST * max(0, clip_count - 1)
        
        for key, value in (editing_options or {}).items():
            if value:
                total += FEATURE_CREDIT_COST.get(key, 0)
        
        return total
    
    @staticmethod
    def get_all_features_with_status(plan_type: str) -> List[dict]:
        """Return all features with availability status for a plan."""
        user_level = PLAN_HIERARCHY.get(plan_type, 0)
        features = []
        for key, min_plan in FEATURE_MIN_PLAN.items():
            min_level = PLAN_HIERARCHY.get(min_plan, 99)
            features.append({
                "key": key,
                "available": user_level >= min_level,
                "min_plan": min_plan,
                "cost_credits": FEATURE_CREDIT_COST.get(key, 0),
            })
        return features


class PlanMiddleware:
    """Middleware logic for enforcing plan limits and credit checks."""
    
    @staticmethod
    def check_concurrent_tasks(profile: UserProfile, active_count: int) -> bool:
        return active_count < profile.max_concurrent_tasks
    
    @staticmethod
    def check_credits(profile: UserProfile, required_credits: float) -> bool:
        return profile.credits_balance >= required_credits
    
    @staticmethod
    def check_video_duration(duration_minutes: float, plan_type: str) -> bool:
        limits = {
            "free": 5,
            "standar": 30,
            "pro": 60,
            "team": 120,
        }
        max_duration = limits.get(plan_type, 5)
        return duration_minutes <= max_duration
    
    @staticmethod
    def deduct_credits(profile: UserProfile, amount: float) -> int:
        """Deduct credits from profile. Returns new balance."""
        profile.credits_balance -= int(amount)
        profile.credits_total_spent += int(amount)
        return profile.credits_balance