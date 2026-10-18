# backend/common/tests.py

- 작성/수정일: 2026-10-19
- 담당: B 공통 관리자 통합
- 흐름/검증: [공통 관리자 연결 라우팅](../../../../development/공통_관리자와_YouTube_검수_통합_변경_라우팅.md)

## IntegrationTests

```python
class IntegrationTests(TestCase)
```

## IntegrationTests.setUpTestData

```python
IntegrationTests.setUpTestData(cls)
```

## IntegrationTests.post

```python
IntegrationTests.post(self, path, body, key='test', client=None)
```

## IntegrationTests.result

```python
IntegrationTests.result(self)
```

## IntegrationTests.test_cookie_is_opaque_hashed_and_expiry_changes_ownership

```python
IntegrationTests.test_cookie_is_opaque_hashed_and_expiry_changes_ownership(self)
```

## IntegrationTests.test_worker_request_events_and_http_idempotency

```python
IntegrationTests.test_worker_request_events_and_http_idempotency(self)
```

## IntegrationTests.test_feedback_cancel_retry_revision_and_projection_reordering

```python
IntegrationTests.test_feedback_cancel_retry_revision_and_projection_reordering(self)
```

## IntegrationTests.test_event_failure_rolls_back_feedback

```python
IntegrationTests.test_event_failure_rolls_back_feedback(self)
```

## IntegrationTests.test_rating_envelope_has_no_track_fields_and_matches_contract

```python
IntegrationTests.test_rating_envelope_has_no_track_fields_and_matches_contract(self)
```

## IntegrationTests.test_outbox_retry_uses_same_event_and_envelope

```python
IntegrationTests.test_outbox_retry_uses_same_event_and_envelope(self)
```

## IntegrationTests.test_stream_conflict_preserves_original

```python
IntegrationTests.test_stream_conflict_preserves_original(self)
```

## IntegrationTests.test_login_requires_csrf_and_permissions_are_checked_again

```python
IntegrationTests.test_login_requires_csrf_and_permissions_are_checked_again(self)
```

## IntegrationTests.test_internal_ads_guest_bootstrap_and_secret

```python
IntegrationTests.test_internal_ads_guest_bootstrap_and_secret(self)
```

## IntegrationTests.test_admin_password_reissue_revokes_old_session_and_preserves_roles

```python
IntegrationTests.test_admin_password_reissue_revokes_old_session_and_preserves_roles(self)
```

## IntegrationTests.test_off_weather_refresh_is_noop_without_provider

```python
IntegrationTests.test_off_weather_refresh_is_noop_without_provider(self)
```

## IntegrationTests.test_off_no_region_preserves_null_and_allows_approval_feedback_and_refresh

```python
IntegrationTests.test_off_no_region_preserves_null_and_allows_approval_feedback_and_refresh(self)
```

## IntegrationTests.test_unset_weather_becomes_off_and_invalid_types_are_rejected

```python
IntegrationTests.test_unset_weather_becomes_off_and_invalid_types_are_rejected(self)
```

## IntegrationTests.test_region_tree_covers_provided_mapping_and_production_reads_pg

```python
IntegrationTests.test_region_tree_covers_provided_mapping_and_production_reads_pg(self)
```

## IntegrationTests.test_import_review_publish_excludes_unapproved_and_binds_source

```python
IntegrationTests.test_import_review_publish_excludes_unapproved_and_binds_source(self)
```

## WeatherAdapterTests

```python
class WeatherAdapterTests(SimpleTestCase)
```

## WeatherAdapterTests.source

```python
WeatherAdapterTests.source(self)
```

## WeatherAdapterTests.test_actual_source_current_hour_and_184_minute_forecast_contract

```python
WeatherAdapterTests.test_actual_source_current_hour_and_184_minute_forecast_contract(self)
```

## WeatherAdapterTests.test_missing_current_sky_cannot_be_filled_from_next_hour

```python
WeatherAdapterTests.test_missing_current_sky_cannot_be_filled_from_next_hour(self)
```

## RegionInputContractTests

```python
class RegionInputContractTests(SimpleTestCase)
```

## RegionInputContractTests.test_current_request_schema_accepts_unset_weather

```python
RegionInputContractTests.test_current_request_schema_accepts_unset_weather(self)
```

## MusicArchiveTests

```python
class MusicArchiveTests(SimpleTestCase)
```

## MusicArchiveTests.test_conditional_upload_pins_version_and_restore_checks_hash

```python
MusicArchiveTests.test_conditional_upload_pins_version_and_restore_checks_hash(self)
```

## MusicArchiveTests.test_s3_retry_preserves_existing_object_and_checks_content_identity

```python
MusicArchiveTests.test_s3_retry_preserves_existing_object_and_checks_content_identity(self)
```

## MusicArchiveTests.test_failed_or_unversioned_archive_never_counts_as_success

```python
MusicArchiveTests.test_failed_or_unversioned_archive_never_counts_as_success(self)
```
