"""Read native Codex task names without model calls or a summary cache."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from pathlib import Path
import re
import sqlite3
from typing import Any
import unicodedata

from codex_thread_index import open_thread_index


TASK_OVERVIEW_COLUMNS = 48
RECENT_TASK_LIMIT = 5
MAX_SEED_CHARACTERS = 4096
MAX_SANITIZE_CHARACTERS = MAX_SEED_CHARACTERS + 1024
REDACTION = "[redacted]"
UNAVAILABLE_OVERVIEW = "Task overview unavailable"

IMAGE_PLACEHOLDER = re.compile(r"\[Image(?:\s+#?\d+)?\]", re.IGNORECASE)
TASK_COMMAND_PREFIX = re.compile(
    r"^(?:(?:[$/][A-Za-z][A-Za-z0-9_-]*):?(?:\s+|$))+",
)
AGENTS_HEADER = re.compile(
    r"^\s*#{1,6}\s*AGENTS\.md instructions[^\r\n]*(?:\r?\n|$)",
    re.IGNORECASE,
)
INJECTED_MARKDOWN_ONLY = re.compile(
    r"^\s*#{1,6}\s*(?:Skills|Handoff)(?:\s|:|$)",
    re.IGNORECASE,
)
INJECTED_XML_BLOCK = re.compile(
    r"(?:(?:>\s*)+)?"
    r"<(?P<tag>INSTRUCTIONS|environment_context|handoff|"
    r"skills_instructions|skill)\b[^>]*>"
    r".*?</(?P=tag)\s*>\s*",
    re.IGNORECASE | re.DOTALL,
)
INJECTED_XML_OPEN = re.compile(
    r"(?:(?:>\s*)+)?"
    r"<(?:INSTRUCTIONS|environment_context|handoff|"
    r"skills_instructions|skill)\b",
    re.IGNORECASE,
)
INJECTED_SUMMARY_PREFIXES = (
    "another language model started to solve this problem",
    "produced a summary of its thinking process",
)
BRIDGE_MARKER = re.compile(
    r"\[BEGIN (?:BRIDGE INSTRUCTIONS|USER REQUEST)\]",
    re.IGNORECASE,
)
BRIDGE_USER_REQUEST = re.compile(
    r"\[BEGIN USER REQUEST\]\s*(.*?)\s*\[END USER REQUEST\]",
    re.IGNORECASE | re.DOTALL,
)
MARKDOWN_LINK = re.compile(r"\[([^\]\r\n]+)\]\([^)]+\)")
LEADING_MARKDOWN = re.compile(
    r"^\s*(?:(?:#{1,6}|[-*+]|>+)\s+)+",
)
LEADING_GREETING = re.compile(
    r"^(?:\u4f60\u597d|\u60a8\u597d|hello|hi)"
    r"[,\uff0c:\uff1a\u3002.!\uff01\s]+",
    re.IGNORECASE,
)
CREDENTIAL_CORE_PATTERN = (
    r"(?:(?:aws[_\s-]?)?(?:access[_\s-]?key(?:[_\s-]?id)?|"
    r"secret[_\s-]?access[_\s-]?key)|"
    r"access[_\s-]?token|account[_\s-]?key|api[_\s-]?key|"
    r"auth(?:orization)?|bearer|client[_\s-]?secret|"
    r"connection[_\s-]?string|cookie|credential|database[_\s-]?url|"
    r"dsn|encryption[_\s-]?key|otp|password|passwd|pin|"
    r"private[_\s-]?key|refresh[_\s-]?token|secret|"
    r"session[_\s-]?(?:id|key|token)|signing[_\s-]?key|"
    r"signature|sig|token|webhook[_\s-]?secret)"
)
CREDENTIAL_VENDOR_PATTERN = (
    r"(?:anthropic|aws|azure|cloudflare|digital[_\s-]?ocean|docker|"
    r"github|gitlab|google|hugging[_\s-]?face|npm|openai|pypi|"
    r"sendgrid|slack|stripe|telegram|twilio)"
)
CREDENTIAL_CAMEL_PATTERN = (
    r"(?:[A-Za-z][A-Za-z0-9]{0,24})?"
    r"(?:AccessKeyId|AccessToken|ApiKey|ClientSecret|ConnectionString|"
    r"Credential|DatabaseUrl|EncryptionKey|Password|Passwd|PrivateKey|"
    r"RefreshToken|Secret|SecretAccessKey|SessionToken|SigningKey|"
    r"Token|WebhookSecret)"
)
CREDENTIAL_NAME_PATTERN = (
    rf"(?:(?:(?:[A-Za-z][A-Za-z0-9]{{0,19}})[_-]){{0,4}}"
    rf"{CREDENTIAL_CORE_PATTERN}|"
    rf"{CREDENTIAL_VENDOR_PATTERN}\s+{CREDENTIAL_CORE_PATTERN}|"
    rf"{CREDENTIAL_CAMEL_PATTERN})"
)
URL_CREDENTIALS = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)"
    r"[^/\s:@]+:[^@\s/]+@",
    re.IGNORECASE,
)
URL_QUERY_SECRET = re.compile(
    rf"(?P<prefix>[?&]{CREDENTIAL_NAME_PATTERN}=)[^&#\s]+",
    re.IGNORECASE,
)
CREDENTIAL_ASSIGNMENT = re.compile(
    rf"(?P<quote>['\"]?)(?P<name>\b{CREDENTIAL_NAME_PATTERN})"
    r"(?P=quote)"
    r"\s*[:=]\s*"
    r"(?P<value>"
    r"(?:(?:bearer|basic|token)\s+)?"
    r"(?:"
    r'"(?:\\.|[^"\\\r\n])*(?:"|$)|'
    r"'(?:\\.|[^'\\\r\n])*(?:'|$)|"
    r"[^\s,;]+"
    r")"
    r")",
    re.IGNORECASE,
)
BARE_CREDENTIAL_VALUE = re.compile(
    rf"(?P<label_quote>['\"]?)(?P<name>\b{CREDENTIAL_NAME_PATTERN})"
    r"(?P=label_quote)\s+"
    r"(?:(?:is|value)\s+)?"
    r"(?P<value>"
    r"(?:(?:bearer|basic|token)\s+)?"
    r"(?:"
    r'"(?:\\.|[^"\\\r\n])*(?:"|$)|'
    r"'(?:\\.|[^'\\\r\n])*(?:'|$)|"
    r"[^\s,;]+"
    r")"
    r")",
    re.IGNORECASE,
)
COOKIE_HEADER = re.compile(
    r"\b(?P<name>(?:set-)?cookie)\s*:\s*[^\r\n]+",
    re.IGNORECASE,
)
PRIVATE_KEY_MATERIAL = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----",
    re.IGNORECASE,
)
SOCIAL_SECURITY_NUMBER = re.compile(
    r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)",
)
PAYMENT_CARD_CANDIDATE = re.compile(
    r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)",
)
NATIONAL_IDENTIFIER = re.compile(
    r"(?<!\d)\d{17}[\dXx](?![A-Za-z0-9])",
)
PHONE_IDENTIFIER = re.compile(
    r"(?<!\d)(?:(?:\+?86[ .-]?)?1[3-9]\d{9})(?!\d)|"
    r"(?<![\w+])\+\d(?:[ .()-]?\d){7,14}(?!\d)|"
    r"(?<!\d)(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?"
    r"[ .-]\d{3}[ .-]\d{4}(?!\d)",
)
LABELED_COMPACT_US_PHONE = re.compile(
    r"\b(?:(?:cell(?:ular)?(?:[_\s-]?phone)?|mobile|phone|telephone|tel)"
    r"(?:[_\s-]?number)?|call(?:\s+[A-Za-z]+){0,4}\s+at)\b"
    r"\s*(?::|=|#)?\s*"
    r"(?P<value>(?:\+?1)?[2-9]\d{9})(?!\d)",
    re.IGNORECASE,
)
LABELED_COMPACT_SSN = re.compile(
    r"\b(?:ssn|social[_\s-]?security(?:[_\s-]?number)?)\b"
    r"\s*(?::|=|#)?\s*"
    r"(?P<value>\d{9})(?!\d)",
    re.IGNORECASE,
)
LABELED_CANADIAN_SIN = re.compile(
    r"\b(?:(?:canada|canadian)[_\s-]+)?"
    r"(?:sin(?:[_\s-]?number)?|"
    r"social[_\s-]?insurance(?:[_\s-]?number)?)\b"
    r"\s*(?::|=|#)?\s*"
    r"(?P<value>\d{3}(?:[ -]?\d{3}){2})(?!\d)",
    re.IGNORECASE,
)
TIMESTAMP_CONTEXT = re.compile(
    r"\b(?:(?:epoch|unix)(?:\s+timestamp)?|timestamp|milliseconds?)"
    r"(?:\s*(?::|=|\bms\b))*\s*$",
    re.IGNORECASE,
)
CREDENTIAL_LABEL = re.compile(
    rf"\b{CREDENTIAL_NAME_PATTERN}\b",
    re.IGNORECASE,
)
KNOWN_TOKEN = re.compile(
    r"(?<![0-9a-z])(?:"
    r"aiza[0-9a-z_-]{12,}|"
    r"(?:aida|aipa|akia|anpa|anva|aroa|asca|asia)[0-9a-z]{12,}|"
    r"eyj[0-9a-z_.=-]{12,}|"
    r"gh[oprsu]_[0-9a-z_-]{12,}|github_pat_[0-9a-z_-]{12,}|"
    r"glpat-[0-9a-z_-]{12,}|pypi-[0-9a-z_-]{12,}|"
    r"npm_[0-9a-z_-]{12,}|hf_[0-9a-z_-]{12,}|"
    r"dckr_pat_[0-9a-z_-]{12,}|dop_v1_[0-9a-z_-]{12,}|"
    r"[prs]k_(?:live|test)_[0-9a-z_-]{12,}|"
    r"sk-[0-9a-z_-]{12,}|xox[aboprs]-[0-9a-z-]{12,}|"
    r"sg\.[0-9a-z_-]{8,}\.[0-9a-z_-]{8,}|"
    r"[0-9]{6,}:[0-9a-z_-]{20,}"
    r")(?=$|[^0-9a-z])",
    re.IGNORECASE,
)
GENERIC_USER_REPLY = re.compile(
    r"^(?:"
    r"\u7ee7\u7eed(?:\u5427|\u4e00\u4e0b)?|"
    r"\u597d(?:\u7684)?\u786e\u5b9a|"
    r"\u597d(?:\u7684)?|\u53ef\u4ee5|\u786e\u8ba4|"
    r"\u662f\u7684|\u4e0d\u662f|\u4e0d\u884c|"
    r"\u6ca1\u95ee\u9898|\u6ca1\u9519|"
    r"\u5bf9(?:\u7684)?|\u884c(?:\u5427)?|\u55ef+|"
    r"\u77e5\u9053\u4e86|\u660e\u767d|\u6536\u5230|\u4e86\u89e3|"
    r"\u8c22\u8c22(?:\u4f60|\u60a8)?|"
    r"\u6d4b\u8bd5(?:\u5df2)?\u901a\u8fc7|"
    r"\u9a8c\u8bc1(?:\u5df2)?\u5b8c\u6210|"
    r"(?:ok(?:ay)?|yes|sure)(?:please)?"
    r"(?:continue(?:please)?|goahead|proceed)|"
    r"ok(?:ay)?|yes|no|thanks?(?:you)?|sure|understood|gotit|"
    r"sounds?good|looksgood|alright|allright|fine|roger|"
    r"continue(?:please)?|goahead|proceed"
    r")$",
    re.IGNORECASE,
)
WORKFLOW_STATUS = re.compile(
    r"(?:(?:all|the)\s+)?"
    r"(?:build|checks?|ci|formatting|implementation|lint|review|task|"
    r"tests?|verification)\s+"
    r"(?:complete|completed|green|passed|succeeded|successful)|"
    r"(?:changes?\s+applied|done)",
    re.IGNORECASE,
)
THREAD_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
SAFE_CREDENTIAL_CONTEXT_WORDS = frozenset({
    "authentication",
    "behavior",
    "bucket",
    "cache",
    "compatibility",
    "configuration",
    "creation",
    "deletion",
    "delivery",
    "deployment",
    "design",
    "display",
    "documentation",
    "entry",
    "exchange",
    "expiration",
    "field",
    "flow",
    "form",
    "format",
    "generation",
    "handling",
    "hashing",
    "header",
    "input",
    "integration",
    "interoperability",
    "length",
    "lifecycle",
    "loading",
    "logic",
    "management",
    "manager",
    "mapping",
    "material",
    "migration",
    "naming",
    "parsing",
    "permissions",
    "policy",
    "provider",
    "redaction",
    "refresh",
    "renewal",
    "requirements",
    "reset",
    "resolution",
    "retrieval",
    "revocation",
    "rotation",
    "rules",
    "scope",
    "security",
    "selection",
    "scanning",
    "scanner",
    "storage",
    "strength",
    "support",
    "test",
    "testing",
    "usage",
    "validation",
    "verification",
})
REDACTED_ASSIGNMENT = re.compile(
    rf"\b{CREDENTIAL_NAME_PATTERN}\s*[:=]\s*"
    + re.escape(REDACTION),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RecentRootThread:
    """One root thread with its native display name and recency."""

    thread_id: str
    title: str
    updated_at: str


@dataclass(frozen=True, order=True)
class SensitiveNumberSpan:
    """One half-open span containing a sensitive numeric value."""

    start: int
    end: int


def _display_width(value: str) -> int:
    return sum(
        0
        if unicodedata.combining(character)
        else 2
        if unicodedata.east_asian_width(character) in {"W", "F"}
        else 1
        for character in value
    )


def _is_safe_credential_context(value: str) -> bool:
    words = tuple(
        word
        for word in re.split(r"[-\s._/]+", value.casefold())
        if word
    )
    return bool(words) and all(
        word in SAFE_CREDENTIAL_CONTEXT_WORDS
        for word in words
    )


def _looks_like_secret_value(value: str, name: str = "") -> bool:
    candidate = value.strip()
    quote = candidate[0] if candidate[:1] in {'"', "'"} else ""
    quoted = bool(quote)
    if quoted:
        candidate = (
            candidate[1:-1]
            if len(candidate) >= 2 and candidate[-1] == quote
            else candidate[1:]
        )
    if not candidate:
        return False
    if quoted or KNOWN_TOKEN.search(candidate):
        return True
    auth_value = re.match(
        r"^(?:bearer|basic|token)\s+(?P<value>\S.*)$",
        candidate,
        re.IGNORECASE,
    )
    if auth_value:
        return not _is_safe_credential_context(
            auth_value.group("value")
        )
    if _is_safe_credential_context(candidate):
        return False
    compact_name = re.sub(r"[\W_]+", "", name).casefold()
    if (
        compact_name.endswith(("otp", "password", "passwd", "pin"))
        and candidate.isdigit()
        and 4 <= len(candidate) <= 12
    ):
        return True
    if name and candidate.isalpha():
        return True
    if len(candidate) < 6:
        return False
    has_lower = any(character.islower() for character in candidate)
    has_upper = any(character.isupper() for character in candidate)
    has_letter = has_lower or has_upper
    has_digit = any(character.isdigit() for character in candidate)
    has_symbol = any(
        character in "._+/=-"
        for character in candidate
    )
    return (
        (has_letter and has_digit)
        or (has_digit and has_symbol)
        or (has_letter and has_symbol)
        or (len(candidate) >= 12 and has_lower and has_upper)
        or (len(candidate) >= 20 and candidate.isalpha())
    )


def _contains_bare_credential(value: str) -> bool:
    return any(
        _looks_like_secret_value(
            match.group("value"),
            match.group("name"),
        )
        for match in BARE_CREDENTIAL_VALUE.finditer(value)
    )


def _redact_bare_credentials(value: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        if not _looks_like_secret_value(
            match.group("value"),
            match.group("name"),
        ):
            return match.group(0)
        return f"{match.group('name')}={REDACTION}"

    return BARE_CREDENTIAL_VALUE.sub(replacement, value)


def _has_timestamp_context(value: str, start: int) -> bool:
    prefix = value[max(0, start - 48):start]
    return TIMESTAMP_CONTEXT.search(prefix) is not None


def _is_payment_card_number(value: str) -> bool:
    digits = "".join(character for character in value if character.isdigit())
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    for index, character in enumerate(reversed(digits)):
        digit = int(character)
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _sensitive_number_spans(value: str) -> tuple[SensitiveNumberSpan, ...]:
    spans: list[SensitiveNumberSpan] = []

    for pattern, group_name in (
        (SOCIAL_SECURITY_NUMBER, None),
        (NATIONAL_IDENTIFIER, None),
        (PHONE_IDENTIFIER, None),
        (LABELED_COMPACT_US_PHONE, "value"),
        (LABELED_COMPACT_SSN, "value"),
        (LABELED_CANADIAN_SIN, "value"),
    ):
        for match in pattern.finditer(value):
            start, end = match.span(group_name or 0)
            if not _has_timestamp_context(value, start):
                spans.append(SensitiveNumberSpan(start, end))

    for match in PAYMENT_CARD_CANDIDATE.finditer(value):
        if (
            not _has_timestamp_context(value, match.start())
            and _is_payment_card_number(match.group(0))
        ):
            spans.append(SensitiveNumberSpan(*match.span()))

    merged: list[SensitiveNumberSpan] = []
    for span in sorted(spans):
        if merged and span.start < merged[-1].end:
            merged[-1] = SensitiveNumberSpan(
                merged[-1].start,
                max(merged[-1].end, span.end),
            )
        else:
            merged.append(span)
    return tuple(merged)


def _redact_sensitive_numbers(value: str) -> str:
    spans = _sensitive_number_spans(value)
    if not spans:
        return value
    redacted: list[str] = []
    cursor = 0
    for span in spans:
        redacted.extend((value[cursor:span.start], REDACTION))
        cursor = span.end
    redacted.append(value[cursor:])
    return "".join(redacted)


def _contains_sensitive_content(value: str) -> bool:
    return bool(
        URL_CREDENTIALS.search(value)
        or URL_QUERY_SECRET.search(value)
        or COOKIE_HEADER.search(value)
        or CREDENTIAL_ASSIGNMENT.search(value)
        or _contains_bare_credential(value)
        or PRIVATE_KEY_MATERIAL.search(value)
        or _sensitive_number_spans(value)
        or KNOWN_TOKEN.search(value)
    )


def _strip_injected_content(value: str) -> str:
    text = value.lstrip()
    if INJECTED_MARKDOWN_ONLY.match(text):
        return ""

    agents_header = AGENTS_HEADER.match(text)
    if agents_header:
        text = text[agents_header.end():]

    removed_block = INJECTED_XML_BLOCK.search(text) is not None
    text = INJECTED_XML_BLOCK.sub(" ", text)

    if (agents_header and not removed_block) or INJECTED_XML_OPEN.search(text):
        return ""
    if text.casefold().startswith(INJECTED_SUMMARY_PREFIXES):
        return ""
    return text


def _strip_unsafe_unicode(value: str) -> str:
    """Remove controls and format characters without transliterating text."""

    accepted: list[str] = []
    for character in value:
        category = unicodedata.category(character)
        if character in "\t\n\r":
            accepted.append(character)
        elif category not in {"Cc", "Cf", "Cs"}:
            accepted.append(character)
    return "".join(accepted)


def _contains_compatibility_unsafe_content(value: str) -> bool:
    """Detect unsafe text revealed only by compatibility normalization."""

    probe = unicodedata.normalize("NFKC", value)
    if probe == value:
        return False
    probe = REDACTED_ASSIGNMENT.sub("", probe).replace(REDACTION, "")
    stripped = probe.lstrip()
    return bool(
        BRIDGE_MARKER.search(probe)
        or TASK_COMMAND_PREFIX.match(stripped)
        or AGENTS_HEADER.match(stripped)
        or INJECTED_MARKDOWN_ONLY.match(stripped)
        or INJECTED_XML_OPEN.search(stripped)
        or stripped.casefold().startswith(INJECTED_SUMMARY_PREFIXES)
        or IMAGE_PLACEHOLDER.search(probe)
        or _contains_sensitive_content(probe)
    )


def sanitize_seed(value: Any) -> str:
    """Return bounded task text with injected wrappers and markup removed."""

    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize(
        "NFC",
        value[:MAX_SANITIZE_CHARACTERS],
    )
    text = _strip_unsafe_unicode(text)
    bridge_request = BRIDGE_USER_REQUEST.search(text)
    if bridge_request:
        text = bridge_request.group(1)
    elif BRIDGE_MARKER.search(text):
        return ""
    text = TASK_COMMAND_PREFIX.sub("", text.lstrip())
    text = _strip_injected_content(text)
    text = IMAGE_PLACEHOLDER.sub(" ", text)
    text = MARKDOWN_LINK.sub(r"\1", text)
    text = LEADING_MARKDOWN.sub("", text)
    if PRIVATE_KEY_MATERIAL.search(text):
        return ""
    text = COOKIE_HEADER.sub(
        lambda match: f"{match.group('name')}={REDACTION}",
        text,
    )
    text = URL_CREDENTIALS.sub(r"\g<scheme>", text)
    text = URL_QUERY_SECRET.sub(
        lambda match: f"{match.group('prefix')}{REDACTION}",
        text,
    )
    text = CREDENTIAL_ASSIGNMENT.sub(
        lambda match: f"{match.group('name')}={REDACTION}",
        text,
    )
    text = _redact_bare_credentials(text)
    text = _redact_sensitive_numbers(text)
    text = KNOWN_TOKEN.sub(REDACTION, text)
    if _contains_compatibility_unsafe_content(text):
        return ""
    text = " ".join(text.split())
    text = LEADING_GREETING.sub("", text).strip()
    return text[:MAX_SEED_CHARACTERS]


def _sanitize_thread_seed(value: Any, thread_id: str) -> str:
    if (
        not isinstance(value, str)
        or thread_id.casefold() in value.casefold()
    ):
        return ""
    sanitized = sanitize_seed(value)
    if thread_id.casefold() in sanitized.casefold():
        return ""
    return sanitized


def _is_meaningful_seed(value: str) -> bool:
    residual = re.sub(
        re.escape(REDACTION),
        " ",
        value,
        flags=re.IGNORECASE,
    )
    if residual != value:
        residual = CREDENTIAL_LABEL.sub(" ", residual)
    status = residual.strip().rstrip(".!").strip()
    if WORKFLOW_STATUS.fullmatch(status):
        return False
    compact = re.sub(r"[\W_]+", "", residual, flags=re.UNICODE)
    return bool(compact) and GENERIC_USER_REPLY.fullmatch(compact) is None


def _bounded_source_text(value: str) -> str:
    if _display_width(value) <= TASK_OVERVIEW_COLUMNS:
        return value

    available_columns = TASK_OVERVIEW_COLUMNS - _display_width("\u2026")
    accepted: list[str] = []
    width = 0
    last_space = -1
    for character in value:
        character_width = _display_width(character)
        if width + character_width > available_columns:
            break
        accepted.append(character)
        width += character_width
        if character.isspace():
            last_space = len(accepted) - 1

    if last_space >= TASK_OVERVIEW_COLUMNS // 3:
        accepted = accepted[:last_space]
    truncated = "".join(accepted).strip(
        " \t\r\n,;:\uff0c\uff1b\uff1a"
    )
    truncated = truncated.rstrip("\u2026")
    return f"{truncated}\u2026" if truncated else ""


def _iso_timestamp(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    numeric = float(value)
    if not numeric or numeric <= 0:
        return ""
    if numeric >= 10_000_000_000:
        numeric /= 1_000
    try:
        moment = dt.datetime.fromtimestamp(numeric, tz=dt.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return ""
    return moment.isoformat().replace("+00:00", "Z")


def recent_root_threads(
    codex_home: Path,
    *,
    limit: int = RECENT_TASK_LIMIT,
) -> list[RecentRootThread]:
    """Read recent unarchived root threads from the current read-only index."""

    with open_thread_index(codex_home) as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(threads)")
            if len(row) > 1
        }
        if "id" not in columns:
            raise sqlite3.DatabaseError("Codex thread index is incomplete")

        time_column = next(
            (
                column
                for column in (
                    "recency_at_ms",
                    "recency_at",
                    "updated_at_ms",
                    "updated_at",
                )
                if column in columns
            ),
            None,
        )
        if time_column is None:
            raise sqlite3.DatabaseError("Codex thread recency is unavailable")

        conditions: list[str] = []
        if "archived" in columns:
            conditions.append("archived = 0")
        if "thread_source" in columns:
            conditions.append(
                "(thread_source IS NULL "
                "OR TRIM(thread_source) = '' "
                "OR thread_source = 'user')"
            )
        if "source" in columns:
            conditions.append("(source IS NULL OR source NOT LIKE '%subagent%')")
        if "agent_path" in columns:
            conditions.append(
                "(agent_path IS NULL OR TRIM(agent_path) = '')"
            )

        expression = {
            column: column if column in columns else "NULL"
            for column in ("name", "title", "history_mode")
        }
        where_clause = " AND ".join(conditions) or "1 = 1"
        rows = connection.execute(
            f"""
            SELECT id, {expression["name"]},
                   {expression["title"]},
                   {expression["history_mode"]}, {time_column}
            FROM threads
            WHERE {where_clause}
            ORDER BY {time_column} DESC, id DESC
            LIMIT 30
            """
        ).fetchall()

    bounded_limit = max(0, min(int(limit), RECENT_TASK_LIMIT))
    if bounded_limit == 0:
        return []
    result: list[RecentRootThread] = []
    for thread_id, name, title, history_mode, updated_at in rows:
        identifier = str(thread_id)
        if THREAD_ID.fullmatch(identifier) is None:
            continue
        display_name = native_name(name)
        # In current Codex, paginated threads use `name`. Their `title` is
        # search metadata, not a replacement for a name that is still pending.
        if not display_name and history_mode != "paginated":
            legacy_title = _sanitize_thread_seed(title, identifier)
            if _is_meaningful_seed(legacy_title):
                display_name = _bounded_source_text(legacy_title)
        result.append(
            RecentRootThread(
                thread_id=identifier,
                title=display_name or UNAVAILABLE_OVERVIEW,
                updated_at=_iso_timestamp(updated_at),
            )
        )
        if len(result) >= bounded_limit:
            break
    return result



def native_name(value: Any) -> str:
    """Keep Codex's wording and language, with display and privacy safeguards."""

    if not isinstance(value, str):
        return ""
    text = " ".join(_strip_unsafe_unicode(
        unicodedata.normalize("NFC", value[:MAX_SANITIZE_CHARACTERS])
    ).split())
    if _contains_sensitive_content(unicodedata.normalize("NFKC", text)):
        text = sanitize_seed(text)
    return _bounded_source_text(text)


def recent_task_payload(codex_home: Path) -> list[dict[str, str]]:
    """Return native task metadata; never start work or read a summary cache."""

    return [
        {
            "title": thread.title,
            "status": "recent",
            "updated_at": thread.updated_at,
        }
        for thread in recent_root_threads(codex_home)
    ]
