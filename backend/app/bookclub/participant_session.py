"""Session middleware for bookclub_public_app, keyed on a private scope
attribute instead of Starlette's built-in "session" key.

bookclub_public_app is mounted inside the primary app's own router via
Host() (see docs/architecture.md) rather than as a truly separate ASGI
mount — so a request to bookclub.libtools.app still passes through the
primary app's own SessionMiddleware before reaching this one. Starlette's
stock SessionMiddleware unconditionally does `scope["session"] = ...` and
its response hook reads `scope["session"]` back at send-time; with two
nested instances sharing that one scope key, the *inner* middleware's
session object silently became what *both* middlewares' response hooks
saw and serialized — i.e. the participant session leaked into both the
`libtools_session` and `bookclub_participant_session` cookies. Using a
distinct scope key (`SCOPE_KEY` below) makes the two middleware instances
fully independent, at the cost of duplicating Starlette's ~50-line
SessionMiddleware implementation (its scope key is a hardcoded literal,
not a constructor parameter, so subclassing can't override just that).
"""

import json
from base64 import b64decode, b64encode
from typing import Literal

import itsdangerous
from itsdangerous.exc import BadSignature
from starlette.datastructures import MutableHeaders, Secret
from starlette.middleware.sessions import Session
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SCOPE_KEY = "bookclub_participant_session"


class ParticipantSessionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        secret_key: str | Secret,
        session_cookie: str = "bookclub_participant_session",
        max_age: int | None = 14 * 24 * 60 * 60,
        path: str = "/",
        same_site: Literal["lax", "strict", "none"] = "lax",
        https_only: bool = False,
    ) -> None:
        self.app = app
        self.signer = itsdangerous.TimestampSigner(str(secret_key))
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.path = path
        self.security_flags = "httponly; samesite=" + same_site
        if https_only:
            self.security_flags += "; secure"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        initial_session_was_empty = True

        if self.session_cookie in connection.cookies:
            data = connection.cookies[self.session_cookie].encode("utf-8")
            try:
                data = self.signer.unsign(data, max_age=self.max_age)
                scope[SCOPE_KEY] = Session(json.loads(b64decode(data)))
                initial_session_was_empty = False
            except BadSignature:
                scope[SCOPE_KEY] = Session()
        else:
            scope[SCOPE_KEY] = Session()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                session: Session = scope[SCOPE_KEY]
                headers = MutableHeaders(scope=message)
                if session.accessed:
                    headers.add_vary_header("Cookie")
                if session.modified and session:
                    data = b64encode(json.dumps(session).encode("utf-8"))
                    data = self.signer.sign(data)
                    header_value = "{session_cookie}={data}; path={path}; {max_age}{security_flags}".format(
                        session_cookie=self.session_cookie,
                        data=data.decode("utf-8"),
                        path=self.path,
                        max_age=f"Max-Age={self.max_age}; " if self.max_age else "",
                        security_flags=self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
                elif session.modified and not initial_session_was_empty:
                    header_value = "{session_cookie}={data}; path={path}; {expires}{security_flags}".format(
                        session_cookie=self.session_cookie,
                        data="null",
                        path=self.path,
                        expires="expires=Thu, 01 Jan 1970 00:00:00 GMT; ",
                        security_flags=self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
            await send(message)

        await self.app(scope, receive, send_wrapper)


def get_participant_session(request) -> Session:
    assert SCOPE_KEY in request.scope, (
        "ParticipantSessionMiddleware must be installed to access the participant session"
    )
    return request.scope[SCOPE_KEY]
