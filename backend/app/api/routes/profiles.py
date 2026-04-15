from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.schemas import ProfileCreate, ProfileResponse, ProfileUpdate
from app.models.profile import UserProfile
from app.models.user import User


router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileResponse])
def list_profiles(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(UserProfile).filter(UserProfile.user_id == user.id).order_by(UserProfile.created_at.desc()).all()


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfileCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = UserProfile(user_id=user.id, **payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    if user.active_profile_id is None:
        user.active_profile_id = profile.id
        db.add(user)
        db.commit()
    return profile


@router.get("/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(UserProfile, profile_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/{profile_id}", response_model=ProfileResponse)
def update_profile(profile_id: int, payload: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(UserProfile, profile_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Profile not found")
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    profile.updated_at = datetime.now(timezone.utc)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{profile_id}")
def delete_profile(profile_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(UserProfile, profile_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Profile not found")
    if user.active_profile_id == profile.id:
        user.active_profile_id = None
        db.add(user)
    db.delete(profile)
    db.commit()
    return {"status": "ok"}


@router.post("/{profile_id}/select", response_model=ProfileResponse)
def select_profile(profile_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(UserProfile, profile_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Profile not found")
    user.active_profile_id = profile.id
    db.add(user)
    db.commit()
    return profile
