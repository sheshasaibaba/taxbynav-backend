import logging

from app.api.deps import get_current_admin_user, get_session
from app.core.config import settings
from app.models.contact import (
    ContactInquiry,
    ContactInquiryCreate,
    ContactInquiryPublic,
    ContactInquiryStatusUpdate,
)
from app.models.user import User
from app.services.email_service import (
    send_contact_acknowledgment_email,
    send_contact_inquiry_admin_email,
)
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/contact", tags=["contact"])


@router.post("", response_model=ContactInquiryPublic, status_code=status.HTTP_201_CREATED)
async def submit_contact_inquiry(
    body: ContactInquiryCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ContactInquiryPublic:
    """Submit a contact message. Saves to DB and dispatches notification emails in background."""
    inquiry = ContactInquiry(
        name=body.name.strip(),
        email=body.email.strip().lower(),
        phone=body.phone.strip() if body.phone else None,
        subject=body.subject.strip(),
        message=body.message.strip(),
        status="new",
    )
    session.add(inquiry)
    await session.flush()
    await session.refresh(inquiry)

    # 1. Notify admin
    admin_email = settings.admin_email_for_auth or settings.smtp_user
    if admin_email:
        background_tasks.add_task(
            send_contact_inquiry_admin_email,
            admin_email=admin_email,
            name=inquiry.name,
            email=inquiry.email,
            phone=inquiry.phone,
            subject=inquiry.subject,
            message=inquiry.message,
        )

    # 2. Acknowledge client
    background_tasks.add_task(
        send_contact_acknowledgment_email,
        to_email=inquiry.email,
        name=inquiry.name,
        subject=inquiry.subject,
    )

    return ContactInquiryPublic(
        id=inquiry.id,
        name=inquiry.name,
        email=inquiry.email,
        phone=inquiry.phone,
        subject=inquiry.subject,
        message=inquiry.message,
        status=inquiry.status,
        created_at=inquiry.created_at,
    )


@router.get("/inquiries", response_model=list[ContactInquiryPublic])
async def list_contact_inquiries(
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(get_current_admin_user),
) -> list[ContactInquiryPublic]:
    """Admin endpoint: view all client inquiries."""
    result = await session.execute(
        select(ContactInquiry).order_by(ContactInquiry.created_at.desc())
    )
    items = result.scalars().all()
    return [
        ContactInquiryPublic(
            id=i.id,
            name=i.name,
            email=i.email,
            phone=i.phone,
            subject=i.subject,
            message=i.message,
            status=i.status,
            created_at=i.created_at,
        )
        for i in items
    ]


@router.patch("/inquiries/{inquiry_id}", response_model=ContactInquiryPublic)
async def update_inquiry_status(
    inquiry_id: int,
    body: ContactInquiryStatusUpdate,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(get_current_admin_user),
) -> ContactInquiryPublic:
    """Admin endpoint: update inquiry status (new, read, resolved)."""
    result = await session.execute(select(ContactInquiry).where(ContactInquiry.id == inquiry_id))
    inquiry = result.scalar_one_or_none()
    if not inquiry:
        raise HTTPException(status_code=404, detail="Inquiry not found")

    inquiry.status = body.status
    session.add(inquiry)
    await session.flush()
    await session.refresh(inquiry)

    return ContactInquiryPublic(
        id=inquiry.id,
        name=inquiry.name,
        email=inquiry.email,
        phone=inquiry.phone,
        subject=inquiry.subject,
        message=inquiry.message,
        status=inquiry.status,
        created_at=inquiry.created_at,
    )
