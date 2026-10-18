import json
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.utils import timezone

from . import tests as core_tests
from .lab_catalogue import seed_tests
from .models import Appointment, Consultation, LabTest, LabOrder, LabReport, AuditEvent, StaffProfile


class LaboratoryWorkflowTests(TestCase):
    act_as = core_tests.HospitalWorkflowTests.act_as
    post = core_tests.HospitalWorkflowTests.post
    patch = core_tests.HospitalWorkflowTests.patch

    @classmethod
    def setUpTestData(cls):
        core_tests.HospitalWorkflowTests.setUpTestData.__func__(cls)
        seed_tests(cls.branch)
        seed_tests(cls.other)
        cls.lab_test = LabTest.objects.filter(branch=cls.branch, code='fbc').get()
        cls.other_test = LabTest.objects.filter(branch=cls.other, code='fbc').get()
        for branch, patient, department, attribute in [
            (cls.branch, cls.patient, cls.department, 'consultation'),
            (cls.other, cls.foreign_patient, cls.other_department, 'foreign_consultation'),
        ]:
            appointment = Appointment.objects.create(branch=branch, patient=patient, department=department,
                scheduled_at=timezone.now(), status='completed')
            record = Consultation.objects.create(branch=branch, patient=patient, appointment=appointment,
                clinician=cls.users['doctor'], symptoms='Synthetic symptoms', diagnosis='Synthetic assessment',
                treatment_plan='Synthetic plan', allergy_status='unknown')
            setattr(cls, attribute, record)

    def setUp(self):
        self.act_as('doctor')
        self.data = {'consultation_id': self.consultation.pk, 'lab_test_id': self.lab_test.pk,
            'indication': 'Synthetic investigation request', 'priority': 'routine'}

    def create_order(self):
        result = self.post('laboratory/', self.data)
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()['id']

    def collect_order(self, pk):
        self.act_as('laboratory')
        response = self.post(f'laboratory/{pk}/collect/', {'specimen_id': 'SYNTHETIC-SAMPLE-01', 'identity_verified': True})
        self.assertEqual(response.status_code, 200, response.content)

    def report_order(self, pk):
        result = self.post(f'laboratory/{pk}/report/', {'result_text': 'Synthetic laboratory observations; not clinical data',
            'reference_info': 'Synthetic reference information', 'review_confirmed': True})
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()['id']

    def test_anonymous_and_nonclinical_roles_cannot_access_lab_records(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/laboratory/').status_code, 401)
        self.assertEqual(self.client.get('/api/laboratory/tests/').status_code, 401)
        for role in ['receptionist', 'accountant']:
            self.act_as(role)
            self.assertEqual(self.client.get('/api/laboratory/').status_code, 403)
            self.assertEqual(self.post('laboratory/', self.data).status_code, 403)
            self.assertNotIn('laboratory', self.client.get('/api/session/').json()['user']['modules'])
        self.act_as('laboratory')
        self.assertIn('laboratory', self.client.get('/api/session/').json()['user']['modules'])
        self.assertEqual(self.client.get('/api/consultations/').status_code, 403)
        self.assertEqual(self.client.get('/api/patients/').status_code, 403)
        self.assertEqual(self.client.get('/api/patient-options/').status_code, 403)

    def test_order_uses_consultation_patient_branch_and_authenticated_requester(self):
        self.data.update(patient_id=str(self.foreign_patient.pk), branch_id=self.other.pk,
            requested_by=self.users['laboratory'].pk)
        pk = self.create_order()
        order = LabOrder.objects.get(pk=pk)
        self.assertEqual(order.patient, self.patient)
        self.assertEqual(order.branch, self.branch)
        self.assertEqual(order.requested_by, self.users['doctor'])
        self.lab_test.name = 'Updated catalogue name'
        self.lab_test.save()
        detail = self.client.get(f'/api/laboratory/{pk}/').json()
        self.assertEqual(detail['test_name'], 'Full blood count')
        self.assertEqual(detail['requested_by'], 'doctor')

    def test_order_rejects_inactive_foreign_tests_missing_indication_and_foreign_consultations(self):
        for values in [{'lab_test_id': self.other_test.pk}, {'consultation_id': self.foreign_consultation.pk},
                       {'indication': '  '}, {'indication': []}, {'priority': 'invalid'}]:
            with self.subTest(values=values):
                self.assertEqual(self.post('laboratory/', {**self.data, **values}).status_code, 400)
        self.lab_test.active = False
        self.lab_test.save()
        self.assertEqual(self.post('laboratory/', self.data).status_code, 400)
        self.assertEqual(LabOrder.objects.count(), 0)

    def test_separate_order_collection_reporting_roles(self):
        pk = self.create_order()
        self.assertEqual(self.post(f'laboratory/{pk}/collect/', {}).status_code, 403)
        self.assertEqual(self.post(f'laboratory/{pk}/report/', {}).status_code, 403)
        self.assertEqual(self.post(f'laboratory/{pk}/addenda/', {}).status_code, 403)
        self.act_as('nurse')
        self.assertEqual(self.client.get(f'/api/laboratory/{pk}/').status_code, 200)
        for action in ['collect', 'report', 'cancel', 'addenda']:
            self.assertEqual(self.post(f'laboratory/{pk}/{action}/', {}).status_code, 403)
        self.assertEqual(self.post('laboratory/', self.data).status_code, 403)
        self.act_as('laboratory')
        self.assertEqual(self.post('laboratory/', self.data).status_code, 403)
        self.assertEqual(self.post(f'laboratory/{pk}/cancel/', {}).status_code, 403)

    def test_collection_and_report_require_review_and_do_not_partially_change_state(self):
        pk = self.create_order()
        self.act_as('laboratory')
        self.assertEqual(self.post(f'laboratory/{pk}/report/', {'result_text':'Synthetic'}).status_code, 409)
        for payload in [{'specimen_id':'A'}, {'identity_verified':True}, {'specimen_id':'A', 'identity_verified':'true'}]:
            self.assertEqual(self.post(f'laboratory/{pk}/collect/', payload).status_code, 400)
        self.assertEqual(LabOrder.objects.get(pk=pk).status, 'requested')
        self.collect_order(pk)
        for payload in [{'result_text':'Synthetic'}, {'result_text':'  ', 'review_confirmed':True}]:
            self.assertEqual(self.post(f'laboratory/{pk}/report/', payload).status_code, 400)
        self.assertEqual(LabOrder.objects.get(pk=pk).status, 'collected')
        self.assertFalse(LabReport.objects.filter(order_id=pk).exists())
        report_id = self.report_order(pk)
        order = LabOrder.objects.get(pk=pk)
        self.assertEqual(order.status, 'reported')
        self.assertEqual(order.collected_by, self.users['laboratory'])
        self.assertEqual(order.report.signed_by, self.users['laboratory'])
        self.assertTrue(AuditEvent.objects.filter(action='lab_report.sign', object_id=str(report_id), branch=self.branch).exists())
        self.assertEqual(self.post(f'laboratory/{pk}/report/', {'result_text':'Overwrite', 'review_confirmed':True}).status_code, 409)
        self.assertEqual(self.post(f'laboratory/{pk}/collect/', {'specimen_id':'Other', 'identity_verified':True}).status_code, 409)
        self.assertNotIn('result_text', self.client.get('/api/laboratory/').json()['results'][0])

    def test_cancellation_preserves_reason_and_blocks_processing(self):
        pk = self.create_order()
        self.assertEqual(self.post(f'laboratory/{pk}/cancel/', {'cancellation_reason':' '}).status_code, 400)
        self.assertEqual(self.post(f'laboratory/{pk}/cancel/', {'cancellation_reason':'Synthetic duplicate request'}).status_code, 200)
        order = LabOrder.objects.get(pk=pk)
        self.assertEqual(order.status,'cancelled')
        self.assertEqual(order.cancelled_by,self.users['doctor'])
        self.act_as('laboratory')
        self.assertEqual(self.post(f'laboratory/{pk}/collect/', {'specimen_id':'A','identity_verified':True}).status_code, 409)
        self.assertEqual(self.post(f'laboratory/{pk}/report/', {'result_text':'Synthetic','review_confirmed':True}).status_code, 409)

    def test_collected_requests_cannot_be_cancelled(self):
        pk = self.create_order()
        self.collect_order(pk)
        self.act_as('doctor')
        self.assertEqual(self.post(f'laboratory/{pk}/cancel/', {'cancellation_reason':'Synthetic'}).status_code, 409)

    def test_signed_report_addenda_do_not_overwrite_results(self):
        pk = self.create_order()
        self.collect_order(pk)
        self.assertEqual(self.post(f'laboratory/{pk}/addenda/', {'note':'Synthetic','review_confirmed':True}).status_code, 409)
        self.report_order(pk)
        self.assertEqual(self.patch(f'laboratory/{pk}/', {'result_text':'Overwrite'}).status_code, 405)
        self.assertEqual(self.post(f'laboratory/{pk}/addenda/', {'note':'  ', 'review_confirmed':True}).status_code, 400)
        self.assertEqual(self.post(f'laboratory/{pk}/addenda/', {'note':'Synthetic correction'}).status_code, 400)
        self.assertEqual(self.post(f'laboratory/{pk}/addenda/', {'note':'Synthetic correction','review_confirmed':True}).status_code, 201)
        self.act_as('doctor')
        detail = self.client.get(f'/api/laboratory/{pk}/').json()
        self.assertEqual(detail['report']['result_text'], 'Synthetic laboratory observations; not clinical data')
        self.assertEqual(detail['report']['addenda'][0]['note'], 'Synthetic correction')
        self.assertEqual(detail['report']['addenda'][0]['signed_by'], 'laboratory')

    def test_branch_boundaries_apply_to_every_lab_action(self):
        pk = self.create_order()
        self.act_as('laboratory')
        profile = StaffProfile.objects.get(user=self.users['laboratory'])
        profile.branch = self.other
        profile.save()
        self.assertEqual(self.client.get('/api/laboratory/').json()['count'],0)
        self.assertEqual(self.client.get(f'/api/laboratory/{pk}/').status_code,404)
        for action in ['collect','report','addenda']:
            self.assertEqual(self.post(f'laboratory/{pk}/{action}/',{}).status_code,404)
        ids=[t['id'] for t in self.client.get('/api/laboratory/tests/').json()['results']]
        self.assertNotIn(self.lab_test.pk,ids)

    def test_search_status_filter_pagination_and_audit(self):
        for _ in range(23):
            self.create_order()
        result = self.client.get('/api/laboratory/?q=Synthetic&status=requested').json()
        self.assertEqual(result['count'],23)
        self.assertEqual(len(result['results']),20)
        self.assertEqual(len(self.client.get('/api/laboratory/?page=2').json()['results']),3)
        self.assertEqual(self.client.get('/api/laboratory/?status=collected').json()['count'],0)
        self.assertEqual(self.client.get('/api/laboratory/?status=invalid').status_code,400)
        self.assertTrue(AuditEvent.objects.filter(action='lab_orders.read',actor=self.users['doctor'],object_id='').exists())

    def test_catalogue_seed_preserves_customisation(self):
        self.lab_test.name='Hospital-customised test'
        self.lab_test.active=False
        self.lab_test.save()
        seed_tests(self.branch)
        self.lab_test.refresh_from_db()
        self.assertEqual(self.lab_test.name,'Hospital-customised test')
        self.assertFalse(self.lab_test.active)
        self.assertEqual(LabTest.objects.filter(branch=self.branch).count(),5)

    def test_lab_writes_retain_csrf_protection(self):
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.users['doctor'])
        self.assertEqual(client.post('/api/laboratory/',json.dumps(self.data),content_type='application/json').status_code,403)
