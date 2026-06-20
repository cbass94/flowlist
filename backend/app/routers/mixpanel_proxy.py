import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter(prefix="/api/mp", tags=["mixpanel"])

_MIXPANEL_API = "https://api.mixpanel.com"


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request) -> Response:
    url = f"{_MIXPANEL_API}/{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.request(
            method=request.method,
            url=url,
            content=await request.body(),
            params=dict(request.query_params),
            headers={"content-type": request.headers.get("content-type", "application/x-www-form-urlencoded")},
        )
    return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))
