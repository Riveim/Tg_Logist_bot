import os
import aiohttp

class ServerClient:
    def __init__(self):
        self.base = os.getenv("SERVER_BASE_URL", "").rstrip("/")
        self.endpoint = os.getenv("SERVER_ENDPOINT", "/loads/latest")
        self.api_key = os.getenv("SERVER_API_KEY", "")
        self.timeout = int(os.getenv("SERVER_TIMEOUT", "10"))

    async def get_loads(self, tg_id: int) -> dict:
        if not self.base:
            return {"ok": False, "error": "SERVER_BASE_URL not set"}

        url = f"{self.base}{self.endpoint}"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        params = {"tg_id": tg_id}

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, params=params) as r:
                ct = r.headers.get("content-type", "")
                if r.status != 200:
                    text = await r.text()
                    return {"ok": False, "status": r.status, "body": text[:2000], "content_type": ct}
                if "application/json" in ct:
                    return {"ok": True, "data": await r.json()}
                return {"ok": True, "data": {"raw": (await r.text())[:4000]}}
