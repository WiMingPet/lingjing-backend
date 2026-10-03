import os
from fastapi import APIRouter, Depends, Query, Header, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.case import Case
from app.schemas.task import APIResponse
from fastapi import Form

router = APIRouter(prefix="/cases", tags=["案例"])

ADMIN_KEY = os.getenv("ADMIN_KEY", "lingjing-admin-2026M1988")


@router.get("", response_model=APIResponse)
def get_cases(
    module: Optional[str] = Query(None),
    section: Optional[str] = Query(None),
    is_case: Optional[bool] = Query(None),
    is_template: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Case).filter(Case.is_active == True)
    if module:
        q = q.filter(Case.module == module)
    if section:
        q = q.filter(Case.section == section)
    if is_case is not None:
        q = q.filter(Case.is_case == is_case)
    if is_template is not None:
        q = q.filter(Case.is_template == is_template)
    cases = q.order_by(Case.position, Case.sort_order, Case.id.desc()).all()
    return APIResponse(code=200, data=[
        {
            "id": c.id,
            "module": c.module,
            "title": c.title,
            "thumbnail": c.thumbnail,
            "preview_video": c.preview_video,
            "result_url": c.result_url,
            "template_prompt": c.template_prompt,
            "template_params": c.template_params,
            "section": c.section,
            "position": c.position,
        }
        for c in cases
    ])


@router.post("", response_model=APIResponse)
def create_case(
    module: str = Form(...),
    title: str = Form(...),
    thumbnail: str = Form(...),
    preview_video: str = Form(""),
    result_url: str = Form(""),
    template_prompt: str = Form(""),
    template_params: str = Form("{}"),
    section: str = Form("ai_video"),
    position: int = Form(0),
    is_case: bool = Form(True),
    is_template: bool = Form(False),
    sort_order: int = Form(0),
    admin_key: str = Header(None, alias="X-Admin-Key"),
    db: Session = Depends(get_db),
):
    if admin_key != ADMIN_KEY:
        raise HTTPException(403, "无权操作")
    c = Case(
        module=module, title=title, thumbnail=thumbnail,
        preview_video=preview_video, result_url=result_url,
        template_prompt=template_prompt, template_params=template_params,
        section=section, position=position,
        is_case=is_case, is_template=is_template, sort_order=sort_order,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return APIResponse(code=200, data={"id": c.id})

@router.delete("/all", response_model=APIResponse)
def delete_all_cases(
    admin_key: str = Header(None, alias="X-Admin-Key"),
    db: Session = Depends(get_db),
):
    if admin_key != ADMIN_KEY:
        raise HTTPException(403, "无权操作")
    count = db.query(Case).delete()
    db.commit()
    return APIResponse(code=200, message=f"已清空 {count} 条")