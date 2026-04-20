from fastapi import APIRouter
import httpx

router = APIRouter(prefix="/test", tags=["测试"])

@router.get("/network")
async def test_network():
    results = {}
    
    # 测试 OpenAI - 使用 httpx 直接请求
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY')}"
            }
            r = await client.get(
                "https://api.openai.com/v1/models",
                headers=headers
            )
            results["openai_direct"] = {"status": "success", "code": r.status_code}
    except Exception as e:
        results["openai_direct"] = {"status": "failed", "error": str(e)}
    
    # 测试 Zeabur AI Hub
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY')}"
            }
            r = await client.get(
                "https://hnd1.aihub.zeabur.ai/v1/models",
                headers=headers
            )
            results["zeabur_aihub"] = {"status": "success", "code": r.status_code}
    except Exception as e:
        results["zeabur_aihub"] = {"status": "failed", "error": str(e)}
    
    return results