from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.utils.file_utils import upload_file_helper
import logging

router = APIRouter(prefix="/upload", tags=["上传"])
logger = logging.getLogger(__name__)


@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    上传图片文件
    """
    try:
        file_url, file_id = await upload_file_helper(file, "ecommerce_images")
        return {
            "code": 200,
            "message": "上传成功",
            "url": file_url,
            "file_id": file_id
        }
    except Exception as e:
        logger.error(f"上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))