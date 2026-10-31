"""Gửi tin vào nhóm Lark bằng Bot của Lark app (App ID / App Secret).

Cần: tính năng Bot đã bật, bot đã được thêm vào nhóm, quyền `im:message:send_as_bot` (gửi tin),
`im:chat:readonly` (liệt kê nhóm bot đang tham gia để lấy chat_id) và `im:resource` (tải ảnh bản tin lên).
"""
import json
import os

import httpx

LARK_BASE = os.getenv("LARK_BASE", "https://open.larksuite.com").rstrip("/")


class LarkError(RuntimeError):
    pass


class LarkBot:
    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or os.getenv("LARK_APP_ID", "")
        self.app_secret = app_secret or os.getenv("LARK_APP_SECRET", "")
        if not self.app_id or not self.app_secret:
            raise LarkError("Thiếu LARK_APP_ID / LARK_APP_SECRET (đặt trong GitHub Secrets)")
        self._token = None
        self._http = httpx.Client(base_url=LARK_BASE, timeout=20)

    @staticmethod
    def _check(resp: httpx.Response) -> dict:
        try:
            data = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise
        if data.get("code", 0) != 0:
            raise LarkError(f"Lark lỗi {data.get('code')}: {data.get('msg')}")
        return data

    def token(self) -> str:
        if not self._token:
            data = self._check(self._http.post(
                "/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret}))
            self._token = data["tenant_access_token"]
        return self._token

    def _headers(self):
        return {"Authorization": f"Bearer {self.token()}"}

    def send_card(self, chat_id: str, card: dict) -> str:
        if not chat_id:
            raise LarkError("Nhóm chưa cấu hình chat_id")
        data = self._check(self._http.post(
            "/open-apis/im/v1/messages", params={"receive_id_type": "chat_id"}, headers=self._headers(),
            json={"receive_id": chat_id, "msg_type": "interactive", "content": json.dumps(card, ensure_ascii=False)}))
        return data["data"]["message_id"]

    def upload_image(self, data: bytes, filename: str = "ban-tin.jpg") -> str:
        """Tải ảnh lên Lark, trả về image_key (dùng lại được cho nhiều tin nhắn)."""
        resp = self._http.post("/open-apis/im/v1/images", headers=self._headers(), timeout=60,
                               data={"image_type": "message"}, files={"image": (filename, data, "image/jpeg")})
        return self._check(resp)["data"]["image_key"]

    def send_image(self, chat_id: str, image_key: str) -> str:
        data = self._check(self._http.post(
            "/open-apis/im/v1/messages", params={"receive_id_type": "chat_id"}, headers=self._headers(),
            json={"receive_id": chat_id, "msg_type": "image", "content": json.dumps({"image_key": image_key})}))
        return data["data"]["message_id"]

    def list_chats(self) -> list:
        """Các nhóm bot đang tham gia: [{chat_id, name}]"""
        out, page_token = [], None
        while True:
            params = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self._check(self._http.get("/open-apis/im/v1/chats", params=params, headers=self._headers()))["data"]
            out += [{"chat_id": c["chat_id"], "name": c.get("name", "")} for c in data.get("items", [])]
            if not data.get("has_more"):
                return out
            page_token = data.get("page_token")
