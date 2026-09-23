"""실행 중 인증 OpenAPI가 공식 계약과 일치하는지 검증합니다."""

import json
from pathlib import Path

import pytest

from tests.auth.helpers import PREFIX


def test_web_errors_and_openapi_contract(client):
    """웹 오류에도 CORS 헤더가 있으며 OpenAPI 상태표가 실제 API와 일치합니다."""
    response = client.patch(
        PREFIX + "/account",
        json={"display_name": "새 이름"},
        headers={"Origin": "https://web.example.test"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["access-control-allow-origin"] == "https://web.example.test"
    assert "Retry-After" in response.headers["access-control-expose-headers"]
    wrong_scheme = client.get(
        PREFIX + "/account", headers={"Authorization": "Basic invalid"}
    )
    assert wrong_scheme.status_code == 401
    assert wrong_scheme.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert wrong_scheme.headers["www-authenticate"] == "Bearer"

    schema = client.get("/openapi.json").json()
    auth_operations = {
        (PREFIX + "/sign-up", "post"): {"200", "400", "409", "503"},
        (PREFIX + "/sign-in", "post"): {"200", "400", "401", "429", "503"},
        (PREFIX + "/refresh", "post"): {"200", "400", "401", "503"},
        (PREFIX + "/account", "get"): {"200", "400", "401", "503"},
        (PREFIX + "/account", "patch"): {"200", "400", "401", "503"},
        (PREFIX + "/account", "delete"): {"200", "400", "401", "503"},
    }
    for (path, method), statuses in auth_operations.items():
        responses = schema["paths"][path][method]["responses"]
        assert set(responses) == statuses
        for documented in responses.values():
            response_schema = documented["content"]["application/json"]["schema"]
            for envelope in response_schema.get("anyOf", [response_schema]):
                if "$ref" in envelope:
                    envelope = schema["components"]["schemas"][
                        envelope["$ref"].rsplit("/", 1)[-1]
                    ]
                assert "code" in envelope["properties"]
                assert "code" in envelope["required"]

    account_methods = schema["paths"][PREFIX + "/account"]
    assert set(account_methods) == {"get", "patch", "delete"}
    assert schema["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Authorization: Bearer <JWT> 헤더로 인증합니다.",
    }
    for method in account_methods.values():
        assert method["security"] == [{"BearerAuth": []}]
        assert "422" not in method["responses"]

    for path in (PREFIX + "/sign-in", PREFIX + "/refresh"):
        response_schema = schema["paths"][path]["post"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        envelope = schema["components"]["schemas"][
            response_schema["$ref"].rsplit("/", 1)[-1]
        ]
        assert envelope["properties"]["data"] == {
            "$ref": "#/components/schemas/TokenData"
        }
    token_data = schema["components"]["schemas"]["TokenData"]
    assert set(token_data["properties"]) == {"token", "expires_at", "token_type"}
    assert set(token_data["required"]) == {"token", "expires_at", "token_type"}


def test_live_openapi_exposes_exact_auth_response_contract(client):
    """라이브 문서가 인증 응답의 고정값과 필수 헤더를 정확히 공개합니다."""
    schema = client.get("/openapi.json").json()
    target = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/openapi.json").read_text(
            encoding="utf-8"
        )
    )

    def resolve(value):
        """컴포넌트 참조를 실제 스키마로 바꿔 비교를 단순하게 만듭니다."""
        if "$ref" not in value:
            return value
        return schema["components"]["schemas"][value["$ref"].rsplit("/", 1)[-1]]

    for path, target_methods in target["paths"].items():
        if not path.startswith(PREFIX + "/"):
            continue
        for method, target_operation in target_methods.items():
            operation = schema["paths"][path][method]
            for status, target_response in target_operation["responses"].items():
                if (
                    path == PREFIX + "/account"
                    and method == "patch"
                    and status == "401"
                ):
                    continue
                response = operation["responses"][status]
                example = target_response["content"]["application/json"]["example"]
                envelope = resolve(response["content"]["application/json"]["schema"])
                assert envelope["additionalProperties"] is False
                assert envelope["properties"]["status"]["const"] == example["status"]
                assert envelope["properties"]["code"]["const"] == example["code"]
                assert envelope["properties"]["message"]["const"] == example["message"]
                expected_headers = target_response["headers"]
                assert set(response["headers"]) == set(expected_headers)
                for name, header in response["headers"].items():
                    assert header["schema"] == expected_headers[name]["schema"]
                assert ("WWW-Authenticate" in response["headers"]) == (status == "401")
                assert ("Retry-After" in response["headers"]) == (status == "429")

    for path in (PREFIX + "/sign-up", PREFIX + "/sign-in", PREFIX + "/refresh"):
        assert schema["paths"][path]["post"]["security"] == []

    refresh_request = schema["components"]["schemas"]["RefreshRequest"]
    assert refresh_request["properties"]["token"]["writeOnly"] is True
    assert schema["components"]["schemas"]["TokenData"]["additionalProperties"] is False
    assert (
        schema["components"]["schemas"]["AccountData"]["additionalProperties"] is False
    )

    patch_401 = schema["paths"][PREFIX + "/account"]["patch"]["responses"]["401"]
    variants = [
        resolve(value)
        for value in patch_401["content"]["application/json"]["schema"]["anyOf"]
    ]
    assert {
        (
            value["properties"]["code"]["const"],
            value["properties"]["message"]["const"],
        )
        for value in variants
    } == {
        (
            "AUTHENTICATION_REQUIRED",
            "Authentication is required or the token is invalid.",
        ),
        ("CURRENT_PASSWORD_INCORRECT", "The current password is incorrect."),
    }
    assert "Cache-Control" in patch_401["headers"]
    assert "WWW-Authenticate" in patch_401["headers"]


def test_openapi_token_expiration_contract(client):
    """생성 OpenAPI가 토큰 만료 시각의 형식과 한국 시간 패턴을 명시합니다."""
    schema = client.get("/openapi.json").json()
    expires_at = schema["components"]["schemas"]["TokenData"]["properties"][
        "expires_at"
    ]
    assert expires_at["format"] == "date-time"
    assert expires_at["pattern"] == (
        r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):"
        r"[0-5][0-9]:[0-5][0-9]\+09:00(?![\s\S])"
    )
    assert expires_at["description"] == (
        "발급한 JWT가 만료되는 한국 시간입니다. JWT의 exp와 같은 시점입니다."
    )
    assert expires_at["example"] == "2026-09-21T14:30:00+09:00"


def test_official_patch_401_allows_only_paired_errors():
    """공식 PATCH 401 계약이 실제 오류 두 쌍만 허용하도록 제한합니다."""
    target = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/openapi.json").read_text(
            encoding="utf-8"
        )
    )
    response = target["paths"][PREFIX + "/account"]["patch"]["responses"]["401"][
        "content"
    ]["application/json"]
    schema = response["schema"]
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"status", "code", "message", "data"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["status"] == {"type": "integer", "const": 401}
    assert schema["properties"]["data"] == {"type": "null"}
    assert schema["properties"]["message"] == {"type": "string"}
    pairs = {
        "AUTHENTICATION_REQUIRED": "Authentication is required or the token is invalid.",
        "CURRENT_PASSWORD_INCORRECT": "The current password is incorrect.",
    }
    assert schema["oneOf"] == [
        {"properties": {"code": {"const": code}, "message": {"const": message}}}
        for code, message in pairs.items()
    ]
    assert {
        example["value"]["code"]: example["value"]["message"]
        for example in response["examples"].values()
    } == pairs


def test_official_delete_account_description_matches_current_scope():
    """공식 DELETE 설명이 현재 삭제 범위와 미래 모델 경계를 구분합니다."""
    target = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/openapi.json").read_text(
            encoding="utf-8"
        )
    )
    description = target["paths"][PREFIX + "/account"]["delete"]["description"]
    assert "User" in description
    assert "LoginAttempt" in description
    assert "모델은 아직 없" in description
    assert "구현할 때" in description
    assert (
        "해당 사용자의 거래, 월별 예산, 소비 분석 리포트를 삭제합니다"
        not in description
    )


@pytest.mark.parametrize("endpoint", ["sign-in", "sign-up"])
def test_openapi_credentials_match_official_input_contract(client, endpoint):
    """가입·로그인 공개 필드 제약이 공식 OpenAPI 입력 계약과 일치합니다."""
    target = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/openapi.json").read_text(
            encoding="utf-8"
        )
    )
    live = client.get("/openapi.json").json()
    operation = PREFIX + "/" + endpoint
    request = live["paths"][operation]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    actual = live["components"]["schemas"][request["$ref"].rsplit("/", 1)[-1]]
    expected = target["paths"][operation]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert actual["required"] == expected["required"]
    assert actual["additionalProperties"] is False
    assert {
        name: {key: value for key, value in field.items() if key != "title"}
        for name, field in actual["properties"].items()
    } == expected["properties"]


def test_openapi_account_update_fields_match_target_contract(client):
    """PATCH 계정 수정 필드가 null 없이 목표 제약을 생성 OpenAPI에 공개합니다."""
    schema = client.get("/openapi.json").json()
    request_schema = schema["paths"][PREFIX + "/account"]["patch"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    assert request_schema == {"$ref": "#/components/schemas/AccountUpdate"}
    update = schema["components"]["schemas"]["AccountUpdate"]
    properties = {
        name: {key: value for key, value in field.items() if key != "title"}
        for name, field in update["properties"].items()
    }
    assert properties == {
        "password": {
            "type": "string",
            "minLength": 8,
            "maxLength": 20,
            "format": "password",
            "writeOnly": True,
            "pattern": (
                r"^(?:(?=.*[A-Za-z])(?=.*[0-9])|"
                r"(?=.*[A-Za-z])(?=.*[!@#$%^&*_=+?\-])|"
                r"(?=.*[0-9])(?=.*[!@#$%^&*_=+?\-]))"
                r"[A-Za-z0-9!@#$%^&*_=+?\-]{8,20}(?![\s\S])"
            ),
            "description": (
                "비밀번호: 8–20자, `A–Z`, `a–z`, `0–9`, `!@#$%^&*_-+=?`만 "
                "허용합니다. 영문·숫자·특수문자 세 종류 중 두 종류 이상이 "
                "필요합니다. 대소문자를 구분하며 공백·한글·그 외 문자를 "
                "거부합니다. 가입·비밀번호 변경에 이 정책을 적용하며, 로그인은 "
                "입력한 비밀번호를 해시와 비교합니다."
            ),
        },
        "display_name": {
            "type": "string",
            "pattern": (
                r"^ *[A-Za-z0-9가-힣ㄱ-ㆎᄀ-ᇿ]"
                r"[A-Za-z0-9가-힣ㄱ-ㆎᄀ-ᇿ ]{0,8}"
                r"[A-Za-z0-9가-힣ㄱ-ㆎᄀ-ᇿ] *(?![\s\S])"
            ),
            "description": (
                "표시 이름: 일반 공백을 앞뒤에서 제거한 후 2–10자입니다. 한글 "
                "음절·자모, ASCII 영문·숫자·일반 공백만 허용합니다. 중간 공백을 "
                "유지하고 글자 수에 포함합니다. 공백만 있는 이름·탭·줄바꿈·"
                "제어문자·다른 특수문자를 거부합니다. 중복은 허용합니다. 원본 "
                "입력은 앞뒤 공백을 포함하여 최대 256자이며, 공백 제거 후 2–10자 "
                "제한은 pattern으로 검사합니다."
            ),
            "maxLength": 256,
        },
        "current_password": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128,
            "format": "password",
            "writeOnly": True,
            "description": (
                "password를 바꿀 때 확인할 현재 비밀번호입니다. password와 함께 "
                "전달해야 합니다."
            ),
        },
    }
    assert update["minProperties"] == 1
    assert update["dependentRequired"] == {
        "password": ["current_password"],
        "current_password": ["password"],
    }
