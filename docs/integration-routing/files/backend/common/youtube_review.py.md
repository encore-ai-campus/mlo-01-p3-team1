# backend/common/youtube_review.py

- 작성/수정일: 2026-10-19
- 담당: B 공통 관리자 통합
- 흐름/검증: [공통 관리자 연결 라우팅](../../../../development/공통_관리자와_YouTube_검수_통합_변경_라우팅.md)

## AdminReviewAuthorization

```python
class AdminReviewAuthorization
```

## AdminReviewAuthorization.authorize

```python
AdminReviewAuthorization.authorize(self, request)
```

## Status

```python
class Status(Endpoint)
```

## Status.get

```python
Status.get(self, request)
```

## Tracks

```python
class Tracks(AdminReviewAuthorization, review.ReviewTracks)
```

## Mappings

```python
class Mappings(AdminReviewAuthorization, review.ReviewMappings)
```

## Import

```python
class Import(AdminReviewAuthorization, review.ReviewImport)
```

## Verify

```python
class Verify(AdminReviewAuthorization, review.ReviewVerify)
```

## Block

```python
class Block(AdminReviewAuthorization, review.ReviewBlock)
```

## NativeVerify

```python
class NativeVerify(AdminReviewAuthorization, review.ReviewNativeVerify)
```

## NativeBlock

```python
class NativeBlock(AdminReviewAuthorization, review.ReviewNativeBlock)
```
