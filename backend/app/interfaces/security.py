from fastapi import HTTPException, Request

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def require_json_for_writes(request: Request) -> None:
    # Cross-site forms cannot send application/json, and a cross-site fetch that does needs a
    # CORS preflight this API never grants, so this blocks CSRF against the unauthenticated API.
    if request.method in SAFE_METHODS:
        return
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(415, "content-type must be application/json")
