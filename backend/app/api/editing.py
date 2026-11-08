"""
Editing endpoints - Available editing options per plan
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.editing import EditingOptionsList, EditingOption, ValidateEditingRequest, ValidateEditingResponse

router = APIRouter()

PLAN_HIERARCHY = {"free": 0, "standar": 1, "pro": 2, "team": 3}

ALL_EDITING_OPTIONS = [
    EditingOption(key="smart_crop_9x16", name="Smart Crop 9:16", description="Auto crop to vertical format", category="framing", cost_credits=0, min_plan="free"),
    EditingOption(key="auto_subtitle", name="Auto Subtitle", description="Whisper transcription", category="subtitle", cost_credits=0, min_plan="free"),
    EditingOption(key="contrast_brightness", name="Auto Contrast/Brightness", description="Fix exposure", category="visual", cost_credits=0, min_plan="standar"),
    EditingOption(key="auto_zoom_face", name="Auto Zoom (Face)", description="Zoom to speaker face", category="zoom", cost_credits=1, min_plan="standar"),
    EditingOption(key="auto_zoom_audio", name="Auto Zoom (Audio)", description="Zoom based on audio intensity", category="zoom", cost_credits=1, min_plan="standar"),
    EditingOption(key="blur_background", name="Blur Background", description="Blur background for 9:16", category="framing", cost_credits=1, min_plan="standar"),
    EditingOption(key="karaoke_subtitle", name="Karaoke Subtitle", description="Word-by-word highlight", category="subtitle", cost_credits=1, min_plan="standar"),
    EditingOption(key="silence_removal", name="Silence Removal", description="Remove silent parts", category="audio", cost_credits=1, min_plan="standar"),
    EditingOption(key="background_music", name="Background Music", description="Auto background music", category="audio", cost_credits=1, min_plan="standar"),
    EditingOption(key="title_card", name="Title Card", description="Intro text overlay", category="text", cost_credits=0.5, min_plan="standar"),
    EditingOption(key="progress_bar", name="Progress Bar", description="Video progress bar", category="branding", cost_credits=0.5, min_plan="standar"),
    EditingOption(key="youtube_upload", name="YouTube Upload", description="Auto upload to YouTube", category="distribution", cost_credits=1, min_plan="standar"),
    EditingOption(key="object_tracking", name="Object Tracking", description="Track moving objects", category="tracking", cost_credits=2, min_plan="pro"),
    EditingOption(key="ken_burns", name="Ken Burns Effect", description="Slow pan and zoom", category="effects", cost_credits=1, min_plan="pro"),
    EditingOption(key="animated_caption", name="Animated Caption", description="Animated text styles", category="subtitle", cost_credits=1, min_plan="pro"),
    EditingOption(key="multi_language_subtitle", name="Multi-language Subtitle", description="30+ languages", category="subtitle", cost_credits=1, min_plan="pro"),
    EditingOption(key="audio_ducking", name="Audio Ducking", description="Lower music during speech", category="audio", cost_credits=1, min_plan="pro"),
    EditingOption(key="noise_reduction", name="Noise Reduction", description="Remove background noise", category="audio", cost_credits=1, min_plan="pro"),
    EditingOption(key="voice_enhancement", name="Voice Enhancement", description="Enhance speech clarity", category="audio", cost_credits=1, min_plan="pro"),
    EditingOption(key="sound_effects", name="Sound Effects", description="Add SFX", category="audio", cost_credits=0.5, min_plan="pro"),
    EditingOption(key="color_grading", name="Color Grading", description="Cinematic color", category="visual", cost_credits=1, min_plan="pro"),
    EditingOption(key="video_filters", name="Video Filters", description="Preset filters", category="visual", cost_credits=1, min_plan="pro"),
    EditingOption(key="speed_ramp", name="Speed Ramp", description="Slow motion / speed up", category="effects", cost_credits=1, min_plan="pro"),
    EditingOption(key="transitions", name="Transitions", description="Fade/cut/wipe", category="effects", cost_credits=0.5, min_plan="pro"),
    EditingOption(key="custom_watermark", name="Custom Watermark", description="Logo overlay", category="branding", cost_credits=0.5, min_plan="pro"),
    EditingOption(key="sticker_overlay", name="Sticker/Emoji", description="Add stickers", category="branding", cost_credits=0.5, min_plan="pro"),
    EditingOption(key="intro_outro", name="Intro/Outro", description="Template intro/outro", category="branding", cost_credits=1, min_plan="pro"),
    EditingOption(key="end_screen", name="End Screen", description="CTA end screen", category="branding", cost_credits=0.5, min_plan="pro"),
    EditingOption(key="viral_scoring", name="Viral Scoring AI", description="AI viral potential score", category="ai", cost_credits=2, min_plan="pro"),
    EditingOption(key="ai_metadata", name="AI Title & Tags", description="AI-generated metadata", category="ai", cost_credits=1, min_plan="pro"),
    EditingOption(key="thumbnail_ai", name="Thumbnail AI", description="AI-generated thumbnail", category="ai", cost_credits=2, min_plan="pro"),
]


@router.get("/options", response_model=EditingOptionsList)
async def get_editing_options(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    
    user_plan = profile.plan_type.value if profile else "free"
    user_plan_level = PLAN_HIERARCHY.get(user_plan, 0)
    
    locked_features = []
    available_options = []
    
    for option in ALL_EDITING_OPTIONS:
        option_plan_level = PLAN_HIERARCHY.get(option.min_plan, 0)
        if option_plan_level > user_plan_level:
            locked_features.append(option.key)
        else:
            available_options.append(option)
    
    return EditingOptionsList(options=available_options, locked_for_plan=locked_features)


@router.post("/validate", response_model=ValidateEditingResponse)
async def validate_editing_options(
    request: ValidateEditingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    
    user_plan = profile.plan_type.value if profile else "free"
    user_plan_level = PLAN_HIERARCHY.get(user_plan, 0)
    
    editing_options = request.editing_options or {}
    locked_features = []
    total_extra_cost = 0.0
    
    for key, value in editing_options.items():
        if not value:
            continue
        option = next((o for o in ALL_EDITING_OPTIONS if o.key == key), None)
        if option:
            option_plan_level = PLAN_HIERARCHY.get(option.min_plan, 0)
            if option_plan_level > user_plan_level:
                locked_features.append(key)
            else:
                total_extra_cost += option.cost_credits
    
    return ValidateEditingResponse(
        valid=len(locked_features) == 0,
        locked_features=locked_features,
        total_extra_cost=total_extra_cost,
    )