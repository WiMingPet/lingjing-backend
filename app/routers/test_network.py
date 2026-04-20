from fastapi import APIRouter
import httpx

router = APIRouter(prefix="/test", tags=["测试"])

@router.get("/network")
async def test_network():
    results = {}
    
    # 直接写入 API Key
    api_key = "sk-effTartCqXaPPp_ccIcJ3g"
    base_url = "https://hnd1.aihub.zeabur.ai/v1"
    
    # 测试 Zeabur AI Hub
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            r = await client.get(f"{base_url}/models", headers=headers)
            results["zeabur_aihub"] = {"status": "success", "code": r.status_code}
    except Exception as e:
        results["zeabur_aihub"] = {"status": "failed", "error": str(e)}
    
    # 测试百度
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("https://www.baidu.com")
            results["baidu"] = {"status": "success", "code": r.status_code}
    except Exception as e:
        results["baidu"] = {"status": "failed", "error": str(e)}
    
    return results