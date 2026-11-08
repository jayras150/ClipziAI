"""
Audit Logger - Records all user and admin actions for investigation
"""
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert

from app.models.audit_log import AuditLog, ActorType


class AuditLogger:
    """Centralized audit logging for all system actions."""
    
    @staticmethod
    async def log(
        db: AsyncSession,
        actor_type: ActorType,
        actor_id: UUID,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        geolocation: Optional[Dict[str, Any]] = None,
        request_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        actor_email: Optional[str] = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        log_entry = AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            actor_email=actor_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            old_values=old_values,
            new_values=new_values,
            meta_data=metadata,
            ip_address=ip_address,
            user_agent=user_agent,
            geolocation=geolocation,
            request_id=request_id,
            session_id=session_id,
        )
        db.add(log_entry)
        await db.flush()
        return log_entry
    
    @staticmethod
    async def log_user_action(
        db: AsyncSession,
        user_id: UUID,
        action: str,
        **kwargs
    ) -> AuditLog:
        """Convenience method for logging user actions."""
        return await AuditLogger.log(
            db=db,
            actor_type=ActorType.USER,
            actor_id=user_id,
            action=action,
            **kwargs
        )
    
    @staticmethod
    async def log_admin_action(
        db: AsyncSession,
        admin_id: UUID,
        action: str,
        **kwargs
    ) -> AuditLog:
        """Convenience method for logging admin actions."""
        return await AuditLogger.log(
            db=db,
            actor_type=ActorType.ADMIN,
            actor_id=admin_id,
            action=action,
            **kwargs
        )
    
    @staticmethod
    async def log_system_event(
        db: AsyncSession,
        action: str,
        **kwargs
    ) -> AuditLog:
        """Convenience method for logging system events."""
        return await AuditLogger.log(
            db=db,
            actor_type=ActorType.SYSTEM,
            actor_id=UUID("00000000-0000-0000-0000-000000000000"),  # System ID
            action=action,
            **kwargs
        )