from fastapi import APIRouter
import httpx

router = APIRouter(prefix="/test", tags=["测试"])

@router.get("/network")
async def test_network():
    """测试外网访问"""
    results = {}
    
    # 测试 OpenAI
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("https://api.openai.com/v1/models")
            results["openai_api"] = {"status": "success", "code": r.status_code}
    except Exception as e:
        results["openai_api"] = {"status": "failed", "error": str(e)}
    
    # 测试 Zeabur AI Hub
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("https://hnd1.aihub.zeabur.ai/v1/models")
            results["zeabur_aihub"] = {"status": "success", "code": r.status_code}
    except Exception as e:
        results["zeabur_aihub"] = {"status": "failed", "error": str(e)}
    
    # 测试百度（国内网站）
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("https://www.baidu.com")
            results["baidu"] = {"status": "success", "code": r.status_code}
    except Exception as e:
        results["baidu"] = {"status": "failed", "error": str(e)}
    
    return results