import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from src.network.cloud_auth import WeighbridgeAuthClient


class TestWeighbridgeAuthClient:
    def make_client(self) -> WeighbridgeAuthClient:
        state = SimpleNamespace(access_token="", refresh_token="", expires_at=0.0)
        return WeighbridgeAuthClient("https://example.test/", "device", "secret", state)

    @patch("src.network.cloud_auth.requests.post")
    def test_login_saves_tokens_and_expiry(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 300,
        }
        post.return_value = response
        client = self.make_client()

        before = time.time()
        client.login()

        post.assert_called_once_with(
            "https://example.test/api/auth/login",
            json={"username": "device", "password": "secret"},
            timeout=15,
        )
        assert client.access_token == "access-1"
        assert client.refresh_token == "refresh-1"
        assert before + 300 <= client.expires_at <= time.time() + 300

    @patch("src.network.cloud_auth.requests.post")
    def test_refresh_rotates_refresh_token(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {
            "access_token": "access-2",
            "refresh_token": "refresh-2",
            "expires_in": 300,
        }
        post.return_value = response
        client = self.make_client()
        client.access_token = "access-1"
        client.refresh_token = "refresh-1"

        client.refresh()

        post.assert_called_once_with(
            "https://example.test/api/auth/refresh",
            json={"refresh_token": "refresh-1"},
            timeout=15,
        )
        assert client.access_token == "access-2"
        assert client.refresh_token == "refresh-2"

    @patch("src.network.cloud_auth.requests.post")
    def test_refresh_falls_back_to_login(self, post: Mock) -> None:
        refresh_response = Mock()
        refresh_response.raise_for_status.side_effect = requests.HTTPError("expired")
        login_response = Mock()
        login_response.json.return_value = {
            "access_token": "access-login",
            "refresh_token": "refresh-login",
            "expires_in": 300,
        }
        post.side_effect = [refresh_response, login_response]
        client = self.make_client()
        client.refresh_token = "expired-refresh"

        client.refresh()

        assert client.access_token == "access-login"
        assert client.refresh_token == "refresh-login"
        assert post.call_count == 2

    @patch("src.network.cloud_auth.requests.post")
    def test_post_entry_refreshes_and_retries_once_after_401(self, post: Mock) -> None:
        unauthorized = Mock(status_code=401)
        accepted = Mock(status_code=201)
        post.side_effect = [unauthorized, accepted]
        client = self.make_client()
        client.access_token = "access-1"
        client.refresh_token = "refresh-1"
        client.expires_at = time.time() + 300
        client.refresh = Mock(side_effect=lambda: setattr(client, "access_token", "access-2"))

        response = client.post_entry({"weight": 125.5})

        assert response is accepted
        client.refresh.assert_called_once_with()
        assert post.call_args_list[0].kwargs["headers"] == {"Authorization": "Bearer access-1"}
        assert post.call_args_list[1].kwargs["headers"] == {"Authorization": "Bearer access-2"}
