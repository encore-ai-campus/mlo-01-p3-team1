import hashlib
import io
import warnings
from datetime import UTC, datetime
from urllib.parse import urlsplit

from bson import BSON
from bson.errors import InvalidDocument
from PIL import Image, UnidentifiedImageError

from .errors import DomainError, ValidationError

MAX_IMAGE_BYTES = 2_000_000
MAX_BSON_BYTES = 16 * 1024 * 1024
AD_FIELDS = frozenset(
    {"title", "asset_id", "link_url", "placement", "starts_at", "ends_at", "priority"}
)
IMAGE_MIME_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def utc_datetime(value):
    """시간대가 있는 시각만 UTC로 변환하고 MongoDB의 ms 정밀도로 고정합니다."""
    try:
        parsed = (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            if isinstance(value, str)
            else value
        )
        if not isinstance(parsed, datetime) or parsed.tzinfo is None:
            raise ValueError
        parsed = parsed.astimezone(UTC)
        return parsed.replace(microsecond=(parsed.microsecond // 1000) * 1000)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValidationError("시간대가 포함된 ISO 8601 시각을 입력해 주세요.") from exc


def utc_string(value):
    return utc_datetime(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def validate_fields(data, allowed, required=None):
    if not isinstance(data, dict):
        raise ValidationError("JSON 객체를 입력해 주세요.")
    unknown = set(data) - set(allowed)
    missing = set(required if required is not None else allowed) - set(data)
    if unknown or missing:
        fields = {}
        if unknown:
            fields["unknown_fields"] = sorted(str(field) for field in unknown)
        if missing:
            fields["missing_fields"] = sorted(missing)
        raise ValidationError(fields=fields)


def validate_positive_version(value):
    if type(value) is not int or value < 1:
        raise ValidationError(fields={"version": "1 이상의 정수가 필요합니다."})
    return value


def validate_ad_input(data, with_version=False):
    allowed = AD_FIELDS | {"version"} if with_version else AD_FIELDS
    validate_fields(data, allowed)
    values = dict(data)
    for field in ("title", "asset_id", "link_url"):
        if not isinstance(values[field], str) or not values[field].strip():
            raise ValidationError(fields={field: "비어 있지 않은 문자열이 필요합니다."})
    if not isinstance(values["placement"], str):
        raise ValidationError(fields={"placement": "top 또는 bottom이 필요합니다."})
    if values["placement"] not in {"top", "bottom"}:
        raise DomainError(
            "OPTION_INVALID",
            "지원하지 않는 광고 위치입니다.",
            400,
            fields={"placement": "top 또는 bottom이 필요합니다."},
        )
    if type(values["priority"]) is not int:
        raise ValidationError(fields={"priority": "정수가 필요합니다."})
    # BSON int64의 표현 범위입니다. 운영 priority 범위를 새로 정하지 않습니다.
    if not -(2**63) <= values["priority"] < 2**63:
        raise ValidationError(fields={"priority": "BSON 정수 표현 범위를 벗어났습니다."})
    try:
        url = values["link_url"]
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or any(character.isspace() or ord(character) < 32 for character in url)
            or "\\" in url
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError
        parsed.port
    except ValueError as exc:
        raise ValidationError(fields={"link_url": "절대 HTTPS URL이 필요합니다."}) from exc
    for field in ("starts_at", "ends_at"):
        try:
            values[field] = utc_datetime(values[field])
        except ValidationError as exc:
            raise ValidationError(fields={field: exc.message}) from exc
    if values["starts_at"] >= values["ends_at"]:
        raise ValidationError(fields={"ends_at": "시작 시각보다 이후여야 합니다."})
    if with_version:
        validate_positive_version(values["version"])
    return values


def validate_stop_input(data):
    validate_fields(data, {"version"})
    return {"version": validate_positive_version(data["version"])}


def validate_image(data):
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_IMAGE_BYTES:
        raise ValidationError(fields={"image": "1~2,000,000바이트 이미지가 필요합니다."})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                mime_type = IMAGE_MIME_TYPES.get(image.format)
                if mime_type is None or getattr(image, "is_animated", False):
                    raise ValidationError(
                        fields={"image": "정적 PNG/JPEG/WebP 이미지만 지원합니다."}
                    )
                width, height = image.size
                image.verify()
            # verify() 후 새 decoder로 실제 픽셀을 읽어 잘린 파일을 검사합니다.
            with Image.open(io.BytesIO(data)) as image:
                image.load()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValidationError(fields={"image": "디코딩할 수 없는 이미지입니다."}) from exc
    return {
        "mime_type": mime_type,
        "byte_size": len(data),
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def validate_bson_size(document):
    try:
        size = len(BSON.encode(document))
    except (InvalidDocument, OverflowError, ValueError, TypeError) as exc:
        raise ValidationError("MongoDB에 저장할 수 없는 자료입니다.") from exc
    if size > MAX_BSON_BYTES:
        raise ValidationError("BSON 문서 크기가 16MiB를 초과했습니다.")
    return size
