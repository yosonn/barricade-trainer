from __future__ import annotations

import json
import random
import re
import threading
import time
import urllib.parse
import urllib.request

API_BASE = "https://api.barricade.gg"
SOCKET_URL = f"{API_BASE}/socket.io/"
ORIGIN = "https://barricade.gg"


def mirror_action(action: str) -> str:
    """Mirror a move vertically between local blue-first and Barricade.gg red-first coordinates."""
    action = action.strip().lower()
    if re.fullmatch(r"[a-i][1-9]", action):
        return f"{action[0]}{10 - int(action[1])}"
    if re.fullmatch(r"[hv][a-h][1-8]", action):
        return f"{action[0]}{action[1]}{9 - int(action[2])}"
    return action


def expert_history_for_start_turn(history: list[str], start_turn: str) -> list[str]:
    if start_turn == "blue":
        return [mirror_action(action) for action in history]
    return history


def local_action_from_expert(action: str, start_turn: str) -> str:
    if start_turn == "blue":
        return mirror_action(action)
    return action


class BarricadeGgAiClient:
    """Small Socket.IO polling client for Barricade.gg's remote AI service."""

    def __init__(self, difficulty: str = "expert", timeout: float = 35.0, pause_sec: float = 0.0) -> None:
        self.difficulty = difficulty
        self.timeout = timeout
        self.pause_sec = pause_sec
        self.device_id = f"codex-{int(time.time())}-{random.randint(1000, 9999)}"
        self.sid: str | None = None
        self.poll_url: str | None = None
        self._lock = threading.Lock()

    def get_move(self, history: list[str]) -> str:
        with self._lock:
            return self._get_move_locked(history)

    def _get_move_locked(self, history: list[str]) -> str:
        if self.pause_sec:
            time.sleep(self.pause_sec)

        try:
            return self._get_move_with_session(history)
        except Exception:
            # Socket.IO polling sessions can expire between turns. Re-open once
            # so the UI recovers without forcing the user to restart the app.
            self.close()
            return self._get_move_with_session(history)

    def _get_move_with_session(self, history: list[str]) -> str:
        poll_url = self._ensure_session()

        correlation_id = f"codex-{int(time.time() * 1000)}"
        payload = [
            "ai:get_move",
            {
                "moves": ",".join(history),
                "difficulty": self.difficulty,
                "correlationId": correlation_id,
                "deviceId": self.device_id,
            },
        ]
        self._request(poll_url, method="POST", data="42/ai,0" + json.dumps(payload, separators=(",", ":")))
        for _ in range(4):
            response = self._request(poll_url)
            if response == "2":
                self._request(poll_url, method="POST", data="3")
                continue
            return self._parse_ai_response(response)
        raise RuntimeError("Barricade.gg Expert did not return a move after ping/pong polling")

    def close(self) -> None:
        self.sid = None
        self.poll_url = None

    def _ensure_session(self) -> str:
        if self.poll_url:
            return self.poll_url
        sid = self._open_session()
        self.sid = sid
        self.poll_url = (
            f"{SOCKET_URL}?EIO=4&transport=polling&sid={urllib.parse.quote(sid)}"
            f"&t={int(time.time() * 1000)}"
        )
        self._request(self.poll_url, method="POST", data=f'40/ai,{{"deviceId":"{self.device_id}"}}')
        self._request(self.poll_url)
        return self.poll_url

    def _open_session(self) -> str:
        url = f"{SOCKET_URL}?EIO=4&transport=polling&t={int(time.time() * 1000)}"
        body = self._request(url)
        if not body.startswith("0"):
            raise RuntimeError(f"Unexpected Socket.IO handshake: {body[:120]}")
        return str(json.loads(body[1:])["sid"])

    def _request(self, url: str, method: str = "GET", data: str | None = None) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36",
            "Accept": "*/*",
            "Origin": ORIGIN,
            "Referer": ORIGIN + "/computer",
        }
        encoded = None
        if data is not None:
            encoded = data.encode("utf-8")
            headers["Content-Type"] = "text/plain;charset=UTF-8"
        request = urllib.request.Request(url, data=encoded, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8", "replace")

    @staticmethod
    def _parse_ai_response(packet: str) -> str:
        if not packet.startswith("43/ai,0"):
            raise RuntimeError(f"Unexpected AI response packet: {packet[:160]}")
        payload = json.loads(packet[len("43/ai,0"):])
        data = payload[0] if payload else {}
        if not data.get("ok"):
            raise RuntimeError(f"Barricade.gg Expert returned an error: {data}")
        move = str(data.get("move", "")).strip().lower()
        if not move:
            raise RuntimeError(f"Barricade.gg Expert returned no move: {data}")
        return move
