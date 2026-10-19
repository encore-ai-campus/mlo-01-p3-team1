"""Expire only the specified OIDC subject's Elasticsearch/Kibana tokens."""
import os
import requests
from django.conf import settings
from .sso import secure_url


def invalidate_kibana(subject):
    base = secure_url(settings.ADMIN_SSO_ELASTICSEARCH_URL).rstrip('/')
    api_key = os.environ.get('ADMIN_SSO_ELASTIC_API_KEY', '')
    if not subject or not api_key:
        raise ValueError('elastic_token_invalidation_not_configured')
    response = requests.delete(base + '/_security/oauth2/token',
        headers={'Authorization':'ApiKey ' + api_key},
        json={'realm_name':'cafe_sso', 'username':subject}, timeout=10, allow_redirects=False)
    if response.status_code != 200 or response.json().get('error_count') != 0:
        raise ValueError('elastic_token_invalidation_failed')
