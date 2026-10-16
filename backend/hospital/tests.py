import json
from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.utils import timezone
from .models import Branch, Department, Patient, StaffProfile, Appointment, Admission, Invoice, AuditEvent


class HospitalWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name='Dija Main', code='main')
        cls.other = Branch.objects.create(name='Future branch', code='future')
        cls.department = Department.objects.create(branch=cls.branch, name='Outpatient', code='opd', category='clinical', description='General care')
        cls.other_department = Department.objects.create(branch=cls.other, name='Outpatient', code='opd', category='clinical', description='General care')
        cls.users = {}
        for role in ['administrator', 'receptionist', 'doctor', 'nurse', 'accountant', 'laboratory']:
            user = User.objects.create_user(username=role, password='Synthetic-test-password-729!')
            StaffProfile.objects.create(user=user, branch=cls.branch, role=role)
            cls.users[role] = user
        cls.patient = Patient.objects.create(branch=cls.branch, first_name='Synthetic', last_name='Patient', date_of_birth='1990-01-01', sex='female', phone='+2348031234567')
        cls.foreign_patient = Patient.objects.create(branch=cls.other, first_name='Other', last_name='Branch', date_of_birth='1990-01-01', sex='male', phone='+2348031234568')

    def act_as(self, role):
        self.client.force_login(self.users[role])

    def post(self, path, payload):
        return self.client.post('/api/'+path, json.dumps(payload), content_type='application/json')

    def patch(self, path, payload=None):
        return self.client.patch('/api/'+path, json.dumps(payload or {}), content_type='application/json')

    def test_anonymous_cannot_read_records(self):
        for path in ['patients/', 'appointments/', 'admissions/', 'invoices/', 'dashboard/', 'departments/']:
            self.assertEqual(self.client.get('/api/'+path).status_code, 401)

    def test_session_login_and_logout_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        token = client.get('/api/session/').json()['csrfToken']
        payload = json.dumps({'username': 'receptionist', 'password': 'Synthetic-test-password-729!'})
        self.assertEqual(client.post('/api/login/', payload, content_type='application/json').status_code, 403)
        result = client.post('/api/login/', payload, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['user']['role'], 'receptionist')
        token = result.json()['csrfToken']
        self.assertEqual(client.get('/api/patients/').status_code, 200)
        self.assertEqual(client.post('/api/logout/', HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(client.get('/api/patients/').status_code, 401)

    def test_registration_normalizes_nigerian_phone_and_creates_audit(self):
        self.act_as('receptionist')
        result = self.post('patients/', {'first_name':'Test', 'last_name':'Person', 'date_of_birth':'2001-02-03', 'sex':'male', 'phone':'0803 123 4569'})
        self.assertEqual(result.status_code, 201, result.content)
        self.assertEqual(result.json()['phone'], '+2348031234569')
        self.assertTrue(result.json()['hospital_number'].startswith('DH-'))
        self.assertTrue(AuditEvent.objects.filter(action='patient.create', actor=self.users['receptionist']).exists())

    def test_registration_rejects_future_birthdate_and_invalid_phone(self):
        self.act_as('receptionist')
        base = {'first_name':'Test', 'last_name':'Person', 'date_of_birth':'2001-01-01', 'sex':'male', 'phone':'not-a-phone'}
        self.assertEqual(self.post('patients/', base).status_code, 400)
        base.update(phone='08031234567', date_of_birth='2999-01-01')
        self.assertEqual(self.post('patients/', base).status_code, 400)

    def test_branch_scope_cannot_be_overridden_by_staff(self):
        self.act_as('receptionist')
        result = self.client.get(f'/api/patients/?branch={self.other.id}').json()
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['results'][0]['id'], str(self.patient.pk))
        departments = self.client.get('/api/departments/').json()['results']
        self.assertEqual([d['id'] for d in departments], [self.department.id])

    def appointment_payload(self):
        return {'patient_id': str(self.patient.pk), 'department_id': self.department.pk, 'scheduled_at': (timezone.now()+timedelta(days=1)).isoformat()}

    def test_appointment_rejects_foreign_branch_and_past_times(self):
        self.act_as('receptionist')
        data = self.appointment_payload()
        data['patient_id'] = str(self.foreign_patient.pk)
        self.assertEqual(self.post('appointments/', data).status_code, 400)
        data = self.appointment_payload()
        data['department_id'] = self.other_department.pk
        self.assertEqual(self.post('appointments/', data).status_code, 400)
        data = self.appointment_payload()
        data['scheduled_at'] = (timezone.now()-timedelta(days=1)).isoformat()
        self.assertEqual(self.post('appointments/', data).status_code, 400)

    def test_appointment_workflow_and_role_boundaries(self):
        self.act_as('receptionist')
        result = self.post('appointments/', self.appointment_payload())
        self.assertEqual(result.status_code, 201, result.content)
        pk = result.json()['id']
        self.assertEqual(self.patch(f'appointments/{pk}/', {'status':'completed'}).status_code, 400)
        self.assertEqual(self.patch(f'appointments/{pk}/', {'status':'checked_in'}).status_code, 200)
        self.assertEqual(self.patch(f'appointments/{pk}/', {'status':'completed'}).status_code, 403)
        self.act_as('doctor')
        self.assertEqual(self.patch(f'appointments/{pk}/', {'status':'completed'}).status_code, 200)
        self.assertEqual(self.patch(f'appointments/{pk}/', {'status':'scheduled'}).status_code, 400)

    def test_admission_prevents_duplicate_beds_and_requires_doctor_for_discharge(self):
        self.act_as('nurse')
        data = {'patient_id':str(self.patient.pk), 'department_id':self.department.pk, 'ward':'Medical', 'bed':'m-01'}
        result = self.post('admissions/', data)
        self.assertEqual(result.status_code, 201, result.content)
        second = Patient.objects.create(branch=self.branch, first_name='Second', last_name='Test', date_of_birth='2000-01-01', sex='male', phone='+2348031234569')
        data['patient_id'] = str(second.pk)
        self.assertEqual(self.post('admissions/', data).status_code, 400)
        pk = result.json()['id']
        self.assertEqual(self.patch(f'admissions/{pk}/').status_code, 403)
        self.act_as('doctor')
        self.assertEqual(self.patch(f'admissions/{pk}/').status_code, 200)
        self.act_as('nurse')
        self.assertEqual(self.post('admissions/', data).status_code, 201)

    def test_billing_permissions_validation_and_paid_transition(self):
        self.act_as('receptionist')
        self.assertEqual(self.client.get('/api/invoices/').status_code, 403)
        self.act_as('accountant')
        self.assertEqual(self.client.get('/api/patients/').status_code, 403)
        self.assertEqual(self.client.get('/api/admissions/').status_code, 403)
        data = {'patient_id':str(self.patient.pk), 'description':'Consultation', 'amount':'-1'}
        self.assertEqual(self.post('invoices/', data).status_code, 400)
        data['amount'] = '5000.25'
        result = self.post('invoices/', data)
        self.assertEqual(result.status_code, 201, result.content)
        pk = result.json()['id']
        self.assertEqual(self.client.get('/api/dashboard/').json()['stats']['outstanding'], '5000.25')
        self.assertEqual(self.patch(f'invoices/{pk}/').status_code, 200)
        self.assertEqual(self.patch(f'invoices/{pk}/').status_code, 400)
        self.assertTrue(AuditEvent.objects.filter(action='invoice.mark_paid', object_id=str(pk)).exists())

    def test_unauthorized_roles_receive_no_patient_details(self):
        self.act_as('laboratory')
        self.assertEqual(self.client.get('/api/patients/').status_code, 403)
        data = self.client.get('/api/dashboard/').json()
        self.assertEqual(data['patients'], [])
        self.assertEqual(data['appointments'], [])
        self.assertIsNone(data['stats']['outstanding'])

    def test_read_access_is_audited_without_patient_values(self):
        self.act_as('doctor')
        self.client.get('/api/patients/')
        event = AuditEvent.objects.get(action='patients.read')
        self.assertEqual(event.branch, self.branch)
        self.assertEqual(event.object_id, '')

    def test_unassigned_account_is_not_allowed(self):
        user = User.objects.create_user(username='unassigned', password='Synthetic-test-password-729!')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/api/dashboard/').status_code, 403)
