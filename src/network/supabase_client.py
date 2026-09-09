"""
supabase_client.py
Base URL and AuthState singleton for the Gluvok Cloud API backend (gluvok.vercel.app).
"""

GLUVOK_BASE_URL = "https://gluvok.vercel.app"

class AuthState:
    def __init__(self):
        self.access_token: str = ""
        self.refresh_token: str = ""
        self.expires_at: float = 0.0

    @property
    def is_token_valid(self) -> bool:
        import time
        # Valid if access token exists and has at least 30 seconds before expiry
        return bool(self.access_token) and (time.time() < self.expires_at - 30.0)

auth_state = AuthState()
