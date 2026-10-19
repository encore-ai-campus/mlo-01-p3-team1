from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from backend.common.models import FeedbackEvent
from backend.common.admin_roles import assign_role


@override_settings(LOCAL_DEMO=False)
class ExclusionHistoryRevisionTests(TestCase):
    def setUp(self):
        user=get_user_model().objects.create_user('history-reviewer',is_staff=True)
        assign_role(user, 'OPS_ADMIN')
        self.client.force_login(user)
        self.at=timezone.now()-timedelta(seconds=1)
        self.exclusion=self.event('ffffffff-ffff-4fff-8fff-ffffffffffff','TRACK_EXCLUDED',1,self.at)
        self.cancellation=self.event('00000000-0000-4000-8000-000000000000','TRACK_EXCLUSION_CANCELLED',2,self.at)

    def event(self,event_id,kind,revision,at):
        return FeedbackEvent.objects.create(event_id=event_id,event_type=kind,owner_id='fixture-owner',
            family_id='fixture-family',track_id='fixture-track',payload={'revision':revision},occurred_at=at,is_test=True)

    def test_equal_timestamps_show_cancellation_and_filter_by_revision(self):
        detail=self.client.get('/api/admin/feedback/exclusions/'+self.cancellation.pk)
        self.assertEqual(detail.status_code,200,detail.content)
        self.assertEqual(detail.json()['state'],'CANCELLED')
        cancelled=self.client.get('/api/admin/feedback/exclusions',{'state':'CANCELLED'}).json()
        self.assertEqual(len(cancelled['items']),2)
        self.assertTrue(all(item['state']=='CANCELLED' for item in cancelled['items']))
        self.assertEqual(self.client.get('/api/admin/feedback/exclusions',{'state':'EXCLUDED'}).json()['items'],[])

    def test_current_revision_wins_over_clock_order_and_as_of_preserves_history(self):
        self.event('11111111-1111-4111-8111-111111111111','TRACK_EXCLUDED',3,self.at-timedelta(seconds=1))
        detail=self.client.get('/api/admin/feedback/exclusions/'+self.cancellation.pk).json()
        self.assertEqual(detail['state'],'EXCLUDED')
        FeedbackEvent.objects.filter(pk=self.cancellation.pk).update(occurred_at=self.at+timedelta(seconds=2))
        rows=self.client.get('/api/admin/feedback/exclusions',{'as_of':self.at.isoformat()}).json()['items']
        self.assertTrue(all(item['state']=='EXCLUDED' for item in rows))
