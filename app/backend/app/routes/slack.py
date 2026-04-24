import base64
import hashlib
import hmac
import json
import secrets
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
import httpx

from app.backend.app.errors import ApiError
from app.backend.app.services.slack_service import SlackService
from app.backend.app.slack.signature import verify_slack_signature


SLACK_SCOPES = "commands,chat:write,chat:write.public,users:read"


def _slack_configured(settings) -> bool:
    return bool(settings.slack_client_id and settings.slack_client_secret and settings.slack_signing_secret)


def _not_configured_response() -> JSONResponse:
    return JSONResponse({"error": "slack_not_configured"}, status_code=503)


def _state_secret(settings) -> str:
    return settings.slack_client_secret or settings.slack_signing_secret or "slack-state"


def _build_state(settings) -> str:
    nonce = secrets.token_urlsafe(24)
    signature = hmac.new(_state_secret(settings).encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).digest()
    return f"{nonce}.{base64.urlsafe_b64encode(signature).decode('ascii').rstrip('=')}"


def _verify_state(settings, state: str) -> bool:
    if "." not in state:
        return False
    nonce, encoded_signature = state.rsplit(".", 1)
    expected = _build_state_from_nonce(settings, nonce)
    return hmac.compare_digest(expected, state)


def _build_state_from_nonce(settings, nonce: str) -> str:
    signature = hmac.new(_state_secret(settings).encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).digest()
    return f"{nonce}.{base64.urlsafe_b64encode(signature).decode('ascii').rstrip('=')}"


async def _read_signed_form(request: Request, settings) -> dict[str, str]:
    body = await request.body()
    if not verify_slack_signature(
        signing_secret=settings.slack_signing_secret or "",
        timestamp=request.headers.get("X-Slack-Request-Timestamp"),
        body=body,
        signature=request.headers.get("X-Slack-Signature"),
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _service(repository, request: Request, bot_token: str | None = None) -> SlackService:
    client = getattr(request.app.state, "slack_http_client", None)
    return SlackService(repository, bot_token=bot_token, client=client)


def create_slack_router(settings, repository) -> APIRouter:
    router = APIRouter(tags=["slack"])

    @router.get("/api/v1/slack/status")
    def slack_status() -> dict:
        installation = repository.get_latest_slack_installation()
        return {
            "configured": _slack_configured(settings),
            "installed": installation is not None,
            "team_id": installation.get("team_id") if installation else None,
            "team_name": installation.get("team_name") if installation else None,
            "installed_at": installation.get("installed_at") if installation else None,
        }

    @router.get("/slack/install")
    def slack_install():
        if not _slack_configured(settings):
            return _not_configured_response()
        query = urlencode(
            {
                "client_id": settings.slack_client_id,
                "scope": SLACK_SCOPES,
                "state": _build_state(settings),
            }
        )
        return RedirectResponse(f"https://slack.com/oauth/v2/authorize?{query}")

    @router.get("/slack/oauth/callback")
    def slack_oauth_callback(request: Request, code: str = "", state: str = ""):
        if not _slack_configured(settings):
            return _not_configured_response()
        if not code or not _verify_state(settings, state):
            raise HTTPException(status_code=400, detail="Invalid Slack OAuth callback")
        client = getattr(request.app.state, "slack_http_client", None) or httpx.Client(timeout=10.0)
        response = client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "code": code,
            },
        )
        data = response.json()
        if not data.get("ok"):
            raise ApiError(str(data.get("error") or "Slack OAuth failed"), error_code="slack_oauth_failed", status_code=502)
        team = data.get("team") or {}
        team_id = str(team.get("id") or "")
        bot_token = str(data.get("access_token") or "")
        if not team_id or not bot_token:
            raise ApiError("Slack OAuth response is incomplete", error_code="slack_oauth_failed", status_code=502)
        user = data.get("authed_user") or {}
        installation = _service(repository, request).save_installation(
            team_id=team_id,
            team_name=team.get("name"),
            bot_token=bot_token,
            user_token=user.get("access_token"),
        )
        return {"ok": True, "team_id": installation["team_id"], "team_name": installation.get("team_name")}

    @router.post("/slack/commands")
    async def slack_commands(request: Request):
        if not _slack_configured(settings):
            return _not_configured_response()
        form = await _read_signed_form(request, settings)
        team_id = form.get("team_id", "")
        installation = repository.get_slack_installation(team_id) or repository.get_latest_slack_installation()
        bot_token = installation.get("bot_token") if installation else None
        return _service(repository, request, bot_token=bot_token).handle_command(form.get("text", ""))

    @router.post("/slack/interactive")
    async def slack_interactive(request: Request):
        if not _slack_configured(settings):
            return _not_configured_response()
        form = await _read_signed_form(request, settings)
        payload = json.loads(form.get("payload") or "{}")
        actions = payload.get("actions") or []
        action = actions[0] if actions else {}
        project_id = action.get("value")
        action_id = action.get("action_id")
        if action_id == "approve_analysis" and project_id:
            project = repository.get_project(str(project_id), include_archived=True)
            repository.log_audit_entry(
                action="analysis.approve",
                actor=str((payload.get("user") or {}).get("id") or "slack"),
                request_id=None,
                ip_address=None,
                project_id=str(project_id),
                project_name=project.get("project_name") if project else None,
            )
            return {"response_type": "ephemeral", "text": f"Analysis approved for `{project_id}`."}
        if action_id == "request_review" and project_id:
            return {"response_type": "ephemeral", "text": f"Review requested for `{project_id}`."}
        return {"response_type": "ephemeral", "text": "Slack action received."}

    @router.post("/slack/events")
    async def slack_events(request: Request):
        if not _slack_configured(settings):
            return _not_configured_response()
        body = await request.json()
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge")}
        return {"ok": True}

    return router
