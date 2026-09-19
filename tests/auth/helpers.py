"""인증 API 테스트가 공유하는 최소 HTTP 요청 도우미를 제공합니다."""

PREFIX = "/api/v1/auth"


def signup(client, username="User123", password="Abcdef12", display_name="홍길동"):
    """명시된 계정을 등록해 테스트의 실제 인증 흐름을 준비합니다."""
    return client.post(
        PREFIX + "/sign-up",
        json=dict(username=username, password=password, display_name=display_name),
    )


def signin(client, username="user123", password="Abcdef12"):
    """실제 로그인 요청을 보내고 원본 응답을 반환합니다."""
    return client.post(
        PREFIX + "/sign-in", json=dict(username=username, password=password)
    )


def account(client, token):
    """GET 계정 조회에 Bearer 헤더만 사용합니다."""
    return client.get(PREFIX + "/account", headers={"Authorization": "Bearer " + token})


def patch_account(client, token, payload):
    """PATCH 계정 수정에 Bearer 헤더와 변경 JSON만 전달합니다."""
    return client.patch(
        PREFIX + "/account",
        headers={"Authorization": "Bearer " + token},
        json=payload,
    )


def delete_account(client, token):
    """DELETE 계정 삭제에 Bearer 헤더만 전달합니다."""
    return client.delete(
        PREFIX + "/account", headers={"Authorization": "Bearer " + token}
    )
