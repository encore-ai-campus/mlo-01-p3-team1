# backend/common/api.py

- 작성/수정일: 2026-10-19
- 담당: B 공통 관리자 통합
- 흐름/검증: [공통 관리자 연결 라우팅](../../../../development/공통_관리자와_YouTube_검수_통합_변경_라우팅.md)

## account_data_for_user

```python
account_data_for_user(user)
```

## account_data

```python
account_data(request)
```

## Me

```python
class Me(Endpoint)
```

## Me.get

```python
Me.get(self, request)
```

## Login

```python
class Login(Endpoint)
```

## Login.post

```python
Login.post(self, request)
```

## Logout

```python
class Logout(Endpoint)
```

## Logout.post

```python
Logout.post(self, request)
```

## AdsContext

```python
class AdsContext(APIView)
```

## AdsContext.post

```python
AdsContext.post(self, request)
```

## Health

```python
class Health(Endpoint)
```

## Health.get

```python
Health.get(self, request)
```

## Regions

```python
class Regions(Endpoint)
```

## Regions.get

```python
Regions.get(self, request)
```

## RegionTree

```python
class RegionTree(Endpoint)
```

## RegionTree.get

```python
RegionTree.get(self, request)
```
