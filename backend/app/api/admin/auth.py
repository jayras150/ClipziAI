"""
Admin authentication endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session
from app.models.admin_user import AdminUser, AdminRole
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.schemas.auth import UserLogin, TokenResponse

router = APIRouter()
security = HTTPBearer()


@router.post("/login", response_model=TokenResponse)
async def admin_login(login_data: UserLogin, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(AdminUser).where(AdminUser.email == login_data.email))
    admin = result.scalar_one_or_none()
    
    if not admin or not admin.password_hash or not verify_password(login_data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not admin.is_active:
        raise HTTPException(status_code=401, detail="Admin account is deactivated")
    
    access_token = create_access_token({"sub": str(admin.id), "role": admin.role.value})
    refresh_token = create_refresh_token({"sub": str(admin.id), "role": admin.role.value})
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)