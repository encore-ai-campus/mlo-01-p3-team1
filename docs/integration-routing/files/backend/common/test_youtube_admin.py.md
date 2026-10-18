# backend/common/test_youtube_admin.py

- 작성/수정일: 2026-10-19
- 담당: B 공통 관리자 통합
- 흐름/검증: [공통 관리자 연결 라우팅](../../../../development/공통_관리자와_YouTube_검수_통합_변경_라우팅.md)

## YoutubeAdminTests

```python
class YoutubeAdminTests(TestCase)
```

## YoutubeAdminTests.setUp

```python
YoutubeAdminTests.setUp(self)
```

## YoutubeAdminTests.authenticate

```python
YoutubeAdminTests.authenticate(self)
```

## YoutubeAdminTests.post

```python
YoutubeAdminTests.post(self, suffix, body, csrf)
```

## YoutubeAdminTests.test_common_login_music_only_menu_and_no_external_redirect

```python
YoutubeAdminTests.test_common_login_music_only_menu_and_no_external_redirect(self)
```

## YoutubeAdminTests.test_anonymous_and_ads_permission_cannot_use_review

```python
YoutubeAdminTests.test_anonymous_and_ads_permission_cannot_use_review(self)
```

## YoutubeAdminTests.test_csrf_registration_native_review_and_iframe_independence

```python
YoutubeAdminTests.test_csrf_registration_native_review_and_iframe_independence(self)
```

## YoutubeAdminTests.test_conflict_and_unknown_track_do_not_partially_import

```python
YoutubeAdminTests.test_conflict_and_unknown_track_do_not_partially_import(self)
```

## YoutubeAdminTests.test_permission_revocation_logout_and_snapshot_scope

```python
YoutubeAdminTests.test_permission_revocation_logout_and_snapshot_scope(self)
```

## YoutubeAdminTests.test_production_registry_remains_unavailable

```python
YoutubeAdminTests.test_production_registry_remains_unavailable(self)
```

## YoutubeAdminTests.test_account_without_management_permissions_cannot_login

```python
YoutubeAdminTests.test_account_without_management_permissions_cannot_login(self)
```
