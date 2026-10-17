"""What counts as a secret: files refused by name, and key shapes redacted from output.
Kept in step with the maintainer's Claude Code guard hook, so both refuse the same files."""

import os
import re

SECRET_NAME = re.compile(
    r"^(?:\.env(?:\..+)?|.*\.creds\.json|token\.json|client_secret.*\.json|id_(?:rsa|ed25519|ecdsa|dsa)|"
    r".*(?:-key|private.*)\.pem|\.netrc|\.?credentials(?:\.json)?|cookies?(?:\.(?:json|txt|sqlite))?|gateway\.env)$", re.I)
SECRET_OK = re.compile(r"\.env\.(?:example|sample|template|dist)$", re.I)
SECRET_PATH = re.compile(r"/\.ssh/(?!.*\.pub$)(?!known_hosts)(?!config$)|/\.openclaw/secrets/|/\.config/op/|/\.aws/credentials|/\.config/gh/hosts\.yml$")

SECRET_PATTERNS = [
    ("1Password service account token", r"ops_[A-Za-z0-9+/=_-]{40,}"),
    ("Anthropic API key", r"sk-ant-[A-Za-z0-9_-]{20,}"),
    ("OpenAI-style API key", r"(?<![A-Za-z0-9])sk-(?:proj-|svcacct-|admin-)?(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{32,}"),
    ("Google API key", r"AIza[0-9A-Za-z_-]{35}"),
    ("GitHub token", r"gh[opsur]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}"),
    ("private key", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY"),
    ("Google OAuth refresh token", r"\b1//[0-9A-Za-z_-]{40,}"),
    ("Slack token", r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    ("AWS access key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("Stripe live key", r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}|whsec_[A-Za-z0-9]{24,}"),
]
_PATTERNS = [(kind, re.compile(pat)) for kind, pat in SECRET_PATTERNS]


def secret_path(path: str) -> bool:
    """True when the file's name or location marks it as a secret."""
    base = os.path.basename(path.rstrip("/"))
    if SECRET_OK.search(base):
        return False
    return bool(SECRET_NAME.match(base) or SECRET_PATH.search(path))


def redact(text: str) -> str:
    """Replace anything shaped like a key with a marker naming its kind."""
    for kind, pat in _PATTERNS:
        text = pat.sub(f"[redacted {kind}]", text)
    return text
