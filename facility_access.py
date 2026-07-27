from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3


JST = timezone(timedelta(hours=9))
PASSWORD_ITERATIONS = 600_000
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
FACILITY_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,31}$")
KNOWN_SCALES = {"ADCT", "DLQI", "UCT"}
ALLOWED_BILLING_STATUSES = {
    "not_connected",
    "manual",
    "trialing",
    "active",
    "past_due",
    "canceled",
    "unpaid",
}


@dataclass(frozen=True)
class FacilityContext:
    facility_id: str
    facility_name: str
    project_id: str
    status: str
    access_enabled: bool
    usage_mode: str
    allowed_scales: tuple[str, ...]
    adct_license_status: str
    plan_code: str
    billing_status: str
    stripe_customer_id: str
    stripe_subscription_id: str
    stripe_price_id: str
    current_period_end: str
    authenticated: bool = False
    external: bool = True


@dataclass(frozen=True)
class IssuedCredentials:
    facility: FacilityContext
    staff_password: str
    patient_access_token: str


@dataclass(frozen=True)
class AuthenticationResult:
    ok: bool
    facility: FacilityContext | None = None
    reason: str = "invalid_credentials"


def normalize_facility_id(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().upper())


def validate_facility_id(value: object) -> str:
    facility_id = normalize_facility_id(value)
    if not FACILITY_ID_PATTERN.fullmatch(facility_id):
        raise ValueError(
            "facility_id must be 3-32 characters and use "
            "uppercase letters, numbers, or underscores"
        )
    return facility_id


def generate_facility_id() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "FAC_" + "".join(secrets.choice(alphabet) for _ in range(8))


def generate_staff_password() -> str:
    return secrets.token_urlsafe(15)


def generate_patient_access_token() -> str:
    return secrets.token_urlsafe(32)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(
    password: str,
    *,
    iterations: int = PASSWORD_ITERATIONS,
    salt: bytes | None = None,
) -> str:
    text = str(password or "")
    if len(text) < 12:
        raise ValueError("password must be at least 12 characters")
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        text.encode("utf-8"),
        actual_salt,
        iterations,
    )
    return (
        f"pbkdf2_sha256${iterations}$"
        f"{_b64encode(actual_salt)}${_b64encode(digest)}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split(
            "$",
            3,
        )
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        expected = _b64decode(digest_text)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            str(password or "").encode("utf-8"),
            _b64decode(salt_text),
            iterations,
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def hash_access_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


_DUMMY_PASSWORD_HASH = hash_password(
    "invalid-password-placeholder",
    salt=b"\0" * 16,
)


def _json_list(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        try:
            parsed = json.loads(str(value or "[]"))
            raw = parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            raw = []
    return tuple(
        scale
        for scale in (str(item).strip().upper() for item in raw)
        if scale in KNOWN_SCALES
    )


def _iso(value: object) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class FacilityStore:
    """Facility registry, login, patient entry, and future billing mapping."""

    def __init__(
        self,
        database_url: str | None = None,
        sqlite_path: str | Path | None = None,
    ) -> None:
        raw_url = (database_url or os.getenv("DATABASE_URL", "")).strip()
        if raw_url.startswith("postgres://"):
            raw_url = "postgresql://" + raw_url[len("postgres://") :]
        self.database_url = raw_url
        self.backend = "postgres" if raw_url else "sqlite"
        default_sqlite = Path(
            os.getenv(
                "RD7_SQLITE_PATH",
                "/var/data/rd7.sqlite3"
                if Path("/var/data").exists()
                else "data/rd7.sqlite3",
            )
        )
        self.sqlite_path = Path(sqlite_path) if sqlite_path else default_sqlite
        self._fallback_pool: Any | None = None
        self.ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self.backend == "postgres":
            try:
                from db_pool import get_postgres_pool
            except ImportError:
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool

                if self._fallback_pool is None:
                    self._fallback_pool = ConnectionPool(
                        conninfo=self.database_url,
                        min_size=1,
                        max_size=4,
                        timeout=10,
                        open=True,
                        kwargs={"row_factory": dict_row},
                    )
                    self._fallback_pool.wait(timeout=15)
                pool = self._fallback_pool
            else:
                pool = get_postgres_pool(self.database_url)
            with pool.connection() as conn:
                yield conn
            return

        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.sqlite_path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @property
    def _placeholder(self) -> str:
        return "%s" if self.backend == "postgres" else "?"

    def ensure_schema(self) -> None:
        if self.backend == "postgres":
            statements = (
                """
                CREATE TABLE IF NOT EXISTS facilities (
                    facility_id TEXT PRIMARY KEY,
                    facility_name TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    patient_access_token_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    access_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    usage_mode TEXT NOT NULL DEFAULT 'clinical_workflow',
                    allowed_scales_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    adct_license_status TEXT NOT NULL DEFAULT 'not_confirmed',
                    plan_code TEXT NOT NULL DEFAULT 'trial',
                    billing_status TEXT NOT NULL DEFAULT 'not_connected',
                    stripe_customer_id TEXT,
                    stripe_subscription_id TEXT,
                    stripe_price_id TEXT,
                    current_period_end TIMESTAMPTZ,
                    failed_login_count INTEGER NOT NULL DEFAULT 0,
                    locked_until TIMESTAMPTZ,
                    last_login_at TIMESTAMPTZ,
                    password_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS stripe_event_log (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    facility_id TEXT REFERENCES facilities(facility_id),
                    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """,
                (
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "idx_facilities_stripe_customer "
                    "ON facilities (stripe_customer_id) "
                    "WHERE stripe_customer_id IS NOT NULL"
                ),
                (
                    "CREATE INDEX IF NOT EXISTS idx_facilities_status "
                    "ON facilities (status, access_enabled)"
                ),
            )
        else:
            statements = (
                """
                CREATE TABLE IF NOT EXISTS facilities (
                    facility_id TEXT PRIMARY KEY,
                    facility_name TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    patient_access_token_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    access_enabled INTEGER NOT NULL DEFAULT 1,
                    usage_mode TEXT NOT NULL DEFAULT 'clinical_workflow',
                    allowed_scales_json TEXT NOT NULL DEFAULT '[]',
                    adct_license_status TEXT NOT NULL DEFAULT 'not_confirmed',
                    plan_code TEXT NOT NULL DEFAULT 'trial',
                    billing_status TEXT NOT NULL DEFAULT 'not_connected',
                    stripe_customer_id TEXT,
                    stripe_subscription_id TEXT,
                    stripe_price_id TEXT,
                    current_period_end TEXT,
                    failed_login_count INTEGER NOT NULL DEFAULT 0,
                    locked_until TEXT,
                    last_login_at TEXT,
                    password_changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS stripe_event_log (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    facility_id TEXT REFERENCES facilities(facility_id),
                    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                (
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "idx_facilities_stripe_customer "
                    "ON facilities (stripe_customer_id) "
                    "WHERE stripe_customer_id IS NOT NULL"
                ),
                (
                    "CREATE INDEX IF NOT EXISTS idx_facilities_status "
                    "ON facilities (status, access_enabled)"
                ),
            )
        with self._connect() as conn:
            for statement in statements:
                conn.execute(statement)

    @staticmethod
    def _context_from_row(
        row: Mapping[str, Any],
        *,
        authenticated: bool = False,
    ) -> FacilityContext:
        return FacilityContext(
            facility_id=str(row.get("facility_id") or ""),
            facility_name=str(row.get("facility_name") or ""),
            project_id=str(row.get("project_id") or ""),
            status=str(row.get("status") or ""),
            access_enabled=bool(row.get("access_enabled")),
            usage_mode=str(row.get("usage_mode") or "clinical_workflow"),
            allowed_scales=_json_list(row.get("allowed_scales_json")),
            adct_license_status=str(
                row.get("adct_license_status") or "not_confirmed"
            ),
            plan_code=str(row.get("plan_code") or "trial"),
            billing_status=str(
                row.get("billing_status") or "not_connected"
            ),
            stripe_customer_id=str(row.get("stripe_customer_id") or ""),
            stripe_subscription_id=str(
                row.get("stripe_subscription_id") or ""
            ),
            stripe_price_id=str(row.get("stripe_price_id") or ""),
            current_period_end=_iso(row.get("current_period_end")),
            authenticated=authenticated,
            external=True,
        )

    def _fetch_row(self, facility_id: str) -> dict[str, Any] | None:
        p = self._placeholder
        sql = f"SELECT * FROM facilities WHERE facility_id = {p}"
        with self._connect() as conn:
            row = conn.execute(sql, (facility_id,)).fetchone()
        return dict(row) if row else None

    def get_facility(
        self,
        facility_id: str,
        *,
        authenticated: bool = False,
    ) -> FacilityContext | None:
        normalized = normalize_facility_id(facility_id)
        if not normalized:
            return None
        row = self._fetch_row(normalized)
        if not row:
            return None
        return self._context_from_row(row, authenticated=authenticated)

    def create_facility(
        self,
        *,
        facility_name: str,
        facility_id: str | None = None,
        project_id: str = "SHIRABEO_FLOW_2026",
        usage_mode: str = "clinical_workflow",
        allowed_scales: Sequence[str] = ("DLQI", "UCT"),
        adct_license_status: str = "not_confirmed",
        plan_code: str = "trial",
        billing_status: str = "not_connected",
        metadata: Mapping[str, Any] | None = None,
    ) -> IssuedCredentials:
        name = str(facility_name or "").strip()
        if not name:
            raise ValueError("facility_name is required")
        normalized_id = validate_facility_id(
            facility_id or generate_facility_id()
        )
        scales = tuple(
            dict.fromkeys(
                str(scale).strip().upper() for scale in allowed_scales
            )
        )
        if not scales or any(scale not in KNOWN_SCALES for scale in scales):
            raise ValueError("at least one known scale is required")
        if "ADCT" in scales and adct_license_status != "confirmed":
            raise ValueError(
                "ADCT cannot be enabled until the facility-specific "
                "license status is confirmed"
            )
        if adct_license_status not in {"not_confirmed", "confirmed"}:
            raise ValueError("invalid adct_license_status")
        if usage_mode not in {"clinical_workflow", "research"}:
            raise ValueError("invalid usage_mode")
        if billing_status not in ALLOWED_BILLING_STATUSES:
            raise ValueError("invalid billing_status")

        staff_password = generate_staff_password()
        patient_token = generate_patient_access_token()
        password_hash = hash_password(staff_password)
        token_hash = hash_access_token(patient_token)
        p = self._placeholder
        columns = (
            "facility_id",
            "facility_name",
            "project_id",
            "password_hash",
            "patient_access_token_hash",
            "status",
            "access_enabled",
            "usage_mode",
            "allowed_scales_json",
            "adct_license_status",
            "plan_code",
            "billing_status",
            "metadata_json",
        )
        values: list[Any] = [
            normalized_id,
            name,
            str(project_id or "SHIRABEO_FLOW_2026").strip(),
            password_hash,
            token_hash,
            "active",
            True,
            usage_mode,
            list(scales),
            adct_license_status,
            str(plan_code or "trial").strip(),
            billing_status,
            dict(metadata or {}),
        ]
        if self.backend == "postgres":
            from psycopg.types.json import Jsonb

            values[columns.index("allowed_scales_json")] = Jsonb(list(scales))
            values[columns.index("metadata_json")] = Jsonb(
                dict(metadata or {})
            )
        else:
            values[columns.index("access_enabled")] = 1
            values[columns.index("allowed_scales_json")] = json.dumps(
                list(scales),
                ensure_ascii=False,
            )
            values[columns.index("metadata_json")] = json.dumps(
                dict(metadata or {}),
                ensure_ascii=False,
            )
        sql = (
            f"INSERT INTO facilities ({', '.join(columns)}) "
            f"VALUES ({', '.join([p] * len(columns))})"
        )
        try:
            with self._connect() as conn:
                conn.execute(sql, values)
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise ValueError("facility_id already exists") from exc
            raise

        facility = self.get_facility(normalized_id)
        if facility is None:
            raise RuntimeError("facility was created but cannot be read")
        return IssuedCredentials(
            facility=facility,
            staff_password=staff_password,
            patient_access_token=patient_token,
        )

    def authenticate(
        self,
        facility_id: str,
        password: str,
        *,
        now: datetime | None = None,
    ) -> AuthenticationResult:
        normalized = normalize_facility_id(facility_id)
        row = self._fetch_row(normalized) if normalized else None
        encoded = (
            str(row.get("password_hash") or "")
            if row
            else _DUMMY_PASSWORD_HASH
        )
        password_ok = verify_password(password, encoded)
        if not row:
            return AuthenticationResult(ok=False)

        current = now or datetime.now(timezone.utc)
        locked_until = _parse_datetime(row.get("locked_until"))
        if locked_until and current.astimezone(timezone.utc) < locked_until.astimezone(
            timezone.utc
        ):
            return AuthenticationResult(ok=False, reason="temporarily_locked")

        if not password_ok:
            failures = int(row.get("failed_login_count") or 0) + 1
            new_lock = (
                current + timedelta(minutes=LOCK_MINUTES)
                if failures >= MAX_FAILED_LOGINS
                else None
            )
            p = self._placeholder
            sql = (
                "UPDATE facilities SET failed_login_count = "
                f"{p}, locked_until = {p}, updated_at = {p} "
                f"WHERE facility_id = {p}"
            )
            timestamp = current.isoformat()
            with self._connect() as conn:
                conn.execute(
                    sql,
                    (
                        0 if new_lock else failures,
                        new_lock.isoformat() if new_lock else None,
                        timestamp,
                        normalized,
                    ),
                )
            reason = "temporarily_locked" if new_lock else "invalid_credentials"
            return AuthenticationResult(ok=False, reason=reason)

        if (
            str(row.get("status") or "") != "active"
            or not bool(row.get("access_enabled"))
        ):
            return AuthenticationResult(ok=False, reason="access_disabled")

        p = self._placeholder
        sql = (
            "UPDATE facilities SET failed_login_count = 0, "
            f"locked_until = NULL, last_login_at = {p}, updated_at = {p} "
            f"WHERE facility_id = {p}"
        )
        timestamp = current.isoformat()
        with self._connect() as conn:
            conn.execute(sql, (timestamp, timestamp, normalized))
        refreshed = self._fetch_row(normalized) or row
        return AuthenticationResult(
            ok=True,
            facility=self._context_from_row(
                refreshed,
                authenticated=True,
            ),
            reason="ok",
        )

    def resolve_patient_access(
        self,
        facility_id: str,
        token: str,
    ) -> FacilityContext | None:
        normalized = normalize_facility_id(facility_id)
        if not normalized or not token:
            return None
        row = self._fetch_row(normalized)
        if not row:
            return None
        valid = hmac.compare_digest(
            hash_access_token(token),
            str(row.get("patient_access_token_hash") or ""),
        )
        if (
            not valid
            or str(row.get("status") or "") != "active"
            or not bool(row.get("access_enabled"))
        ):
            return None
        return self._context_from_row(row, authenticated=False)

    def rotate_password(self, facility_id: str) -> str:
        normalized = validate_facility_id(facility_id)
        password = generate_staff_password()
        p = self._placeholder
        now = datetime.now(timezone.utc).isoformat()
        sql = (
            f"UPDATE facilities SET password_hash = {p}, "
            f"password_changed_at = {p}, failed_login_count = 0, "
            f"locked_until = NULL, updated_at = {p} "
            f"WHERE facility_id = {p}"
        )
        with self._connect() as conn:
            cursor = conn.execute(
                sql,
                (hash_password(password), now, now, normalized),
            )
            if cursor.rowcount != 1:
                raise ValueError("facility_id was not found")
        return password

    def rotate_patient_access_token(self, facility_id: str) -> str:
        normalized = validate_facility_id(facility_id)
        token = generate_patient_access_token()
        p = self._placeholder
        sql = (
            f"UPDATE facilities SET patient_access_token_hash = {p}, "
            f"updated_at = {p} WHERE facility_id = {p}"
        )
        with self._connect() as conn:
            cursor = conn.execute(
                sql,
                (
                    hash_access_token(token),
                    datetime.now(timezone.utc).isoformat(),
                    normalized,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("facility_id was not found")
        return token

    def set_access_enabled(
        self,
        facility_id: str,
        *,
        enabled: bool,
    ) -> None:
        normalized = validate_facility_id(facility_id)
        p = self._placeholder
        sql = (
            f"UPDATE facilities SET access_enabled = {p}, "
            f"status = {p}, updated_at = {p} WHERE facility_id = {p}"
        )
        with self._connect() as conn:
            cursor = conn.execute(
                sql,
                (
                    bool(enabled) if self.backend == "postgres" else int(enabled),
                    "active" if enabled else "suspended",
                    datetime.now(timezone.utc).isoformat(),
                    normalized,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("facility_id was not found")

    def update_billing(
        self,
        facility_id: str,
        *,
        plan_code: str,
        billing_status: str,
        stripe_customer_id: str = "",
        stripe_subscription_id: str = "",
        stripe_price_id: str = "",
        current_period_end: str | None = None,
    ) -> FacilityContext:
        normalized = validate_facility_id(facility_id)
        if billing_status not in ALLOWED_BILLING_STATUSES:
            raise ValueError("invalid billing_status")
        p = self._placeholder
        sql = (
            f"UPDATE facilities SET plan_code = {p}, billing_status = {p}, "
            f"stripe_customer_id = {p}, stripe_subscription_id = {p}, "
            f"stripe_price_id = {p}, current_period_end = {p}, "
            f"updated_at = {p} WHERE facility_id = {p}"
        )
        values = (
            str(plan_code or "").strip(),
            billing_status,
            str(stripe_customer_id or "").strip() or None,
            str(stripe_subscription_id or "").strip() or None,
            str(stripe_price_id or "").strip() or None,
            current_period_end,
            datetime.now(timezone.utc).isoformat(),
            normalized,
        )
        with self._connect() as conn:
            cursor = conn.execute(sql, values)
            if cursor.rowcount != 1:
                raise ValueError("facility_id was not found")
        facility = self.get_facility(normalized)
        if facility is None:
            raise RuntimeError("facility cannot be read after billing update")
        return facility

    def record_stripe_event(
        self,
        *,
        event_id: str,
        event_type: str,
        facility_id: str | None = None,
    ) -> bool:
        event = str(event_id or "").strip()
        kind = str(event_type or "").strip()
        if not event or not kind:
            raise ValueError("event_id and event_type are required")
        facility = (
            validate_facility_id(facility_id)
            if facility_id
            else None
        )
        p = self._placeholder
        conflict = (
            "ON CONFLICT (event_id) DO NOTHING"
            if self.backend == "postgres"
            else "ON CONFLICT(event_id) DO NOTHING"
        )
        sql = (
            "INSERT INTO stripe_event_log "
            f"(event_id, event_type, facility_id) VALUES ({p}, {p}, {p}) "
            f"{conflict}"
        )
        with self._connect() as conn:
            cursor = conn.execute(sql, (event, kind, facility))
            return cursor.rowcount == 1

    def list_facilities(self) -> list[dict[str, Any]]:
        sql = """
            SELECT
                facility_id,
                facility_name,
                project_id,
                status,
                access_enabled,
                usage_mode,
                allowed_scales_json,
                adct_license_status,
                plan_code,
                billing_status,
                stripe_customer_id,
                stripe_subscription_id,
                stripe_price_id,
                current_period_end,
                last_login_at,
                created_at,
                updated_at
            FROM facilities
            ORDER BY created_at DESC, facility_id ASC
        """
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        result: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            row["access_enabled"] = bool(row.get("access_enabled"))
            row["allowed_scales"] = list(
                _json_list(row.pop("allowed_scales_json", []))
            )
            for key in (
                "current_period_end",
                "last_login_at",
                "created_at",
                "updated_at",
            ):
                row[key] = _iso(row.get(key))
            result.append(row)
        return result


def legacy_facility_context(
    *,
    facility_id: str,
    facility_name: str,
    project_id: str,
    allowed_scales: Sequence[str] = ("ADCT", "DLQI", "UCT"),
    usage_mode: str = "research",
) -> FacilityContext:
    return FacilityContext(
        facility_id=normalize_facility_id(facility_id),
        facility_name=str(facility_name or "").strip(),
        project_id=str(project_id or "").strip(),
        status="active",
        access_enabled=True,
        usage_mode=usage_mode,
        allowed_scales=tuple(
            str(scale).strip().upper() for scale in allowed_scales
        ),
        adct_license_status="confirmed",
        plan_code="legacy",
        billing_status="manual",
        stripe_customer_id="",
        stripe_subscription_id="",
        stripe_price_id="",
        current_period_end="",
        authenticated=False,
        external=False,
    )


def context_as_dict(context: FacilityContext) -> dict[str, Any]:
    return asdict(context)
