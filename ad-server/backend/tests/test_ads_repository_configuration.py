"""관리·공개·정책 저장소의 공통 연결 계약을 각 팩토리에 같은 입력으로 적용합니다."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from domains.ads.errors import DatabaseUnavailable
from repositories import ads_mongo, ads_policy_mongo, ads_public_mongo

REPOSITORIES = (
    (
        ads_mongo,
        ads_mongo.get_ads_repository,
        ads_mongo._configured_repository,
        ads_mongo.MongoAdsRepository,
    ),
    (
        ads_public_mongo,
        ads_public_mongo.get_public_ads_repository,
        ads_public_mongo._configured_public_repository,
        ads_public_mongo.MongoPublicAdsRepository,
    ),
    (
        ads_policy_mongo,
        ads_policy_mongo.get_ads_policy_repository,
        ads_policy_mongo._configured_policy_repository,
        ads_policy_mongo.MongoAdsPolicyRepository,
    ),
)


@override_settings(ADS_MONGODB_DATABASE="advertising_dev")
class AdsRepositoryConfigurationTests(SimpleTestCase):
    def setUp(self):
        for _, _, cached, _ in REPOSITORIES:
            cached.cache_clear()
            self.addCleanup(cached.cache_clear)

    def test_private_primary_factories_reuse_clients_and_preserve_environment(self):
        uri = "mongodb://ads.private:27017/?replicaSet=team-rs"
        for module, factory, _, adapter in REPOSITORIES:
            for is_test in (True, False):
                with (
                    self.subTest(repository=module.__name__, is_test=is_test),
                    self.settings(ADS_MONGODB_URI=uri, ADS_IS_TEST=is_test),
                    patch.object(module, "MongoClient", return_value=MagicMock()) as create,
                ):
                    repository = factory()
                    self.assertIs(factory(), repository)
                    self.assertIs(type(repository), adapter)
                    self.assertEqual(repository.is_test, is_test)
                    create.assert_called_once()
                    self.assertEqual(create.call_args.args, (uri,))
                    self.assertEqual(create.call_args.kwargs["readPreference"], "primary")

    def test_missing_uri_is_rejected_by_each_factory_before_driver_creation(self):
        for module, factory, _, _ in REPOSITORIES:
            for is_test in (True, False):
                with (
                    self.subTest(repository=module.__name__, is_test=is_test),
                    self.settings(ADS_MONGODB_URI="", ADS_IS_TEST=is_test),
                    patch.object(module, "MongoClient") as create,
                ):
                    with self.assertRaises(DatabaseUnavailable):
                        factory()
                    create.assert_not_called()
