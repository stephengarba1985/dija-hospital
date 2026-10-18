import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, Client
from django.utils import timezone

from . import tests as core_tests
from .models import (Branch, Department, Patient, Appointment, Consultation, StaffProfile, Medicine,
    MedicineBatch, Prescription, Dispense, StockMovement, AuditEvent)


class PharmacyWorkflowTests(TestCase):
    act_as = core_tests.HospitalWorkflowTests.act_as
    post = core_tests.HospitalWorkflowTests.post

    @classmethod
    def setUpTestData(cls):
        core_tests.HospitalWorkflowTests.setUpTestData.__func__(cls)
        cls.users['pharmacist'] = User.objects.create_user('pharmacist', password='Synthetic-test-password-729!')
        StaffProfile.objects.create(user=cls.users['pharmacist'], branch=cls.branch, role='pharmacist')
        cls.medicine = Medicine.objects.create(branch=cls.branch, code='synthetic', name='Synthetic training medicine',
            strength='Dummy strength', form='Dummy formulation', dispensing_unit='units', low_stock_threshold=5)
        cls.other_medicine = Medicine.objects.create(branch=cls.other, code='synthetic', name='Other synthetic medicine',
            strength='Dummy strength', form='Dummy formulation', dispensing_unit='units')
        cls.appointment = Appointment.objects.create(branch=cls.branch, patient=cls.patient, department=cls.department,
            scheduled_at=timezone.now(), status='completed')
        cls.consultation = Consultation.objects.create(branch=cls.branch, patient=cls.patient, appointment=cls.appointment,
            clinician=cls.users['doctor'], symptoms='Synthetic history', diagnosis='Synthetic assessment', treatment_plan='Synthetic plan',
            allergy_status='known', allergies='Synthetic allergy record for testing')

    def setUp(self):
        self.act_as('doctor')
        self.data = {'consultation_id':self.consultation.pk, 'medicine_id':self.medicine.pk,
            'dose':'Synthetic dose', 'route':'Synthetic route', 'frequency':'Synthetic schedule',
            'duration':'Synthetic duration', 'quantity':'10', 'instructions':'Software test only', 'review_confirmed':True}

    def prescribe(self):
        self.act_as('doctor')
        response=self.post('pharmacy/', self.data)
        self.assertEqual(response.status_code,201,response.content)
        return response.json()['id']

    def receive(self, amount=20, reference=None, batch='SYNTHETIC-01'):
        self.act_as('pharmacist')
        response=self.post('pharmacy/receive/', {'medicine_id':self.medicine.pk,'quantity':str(amount),
            'batch_number':batch,'expiry_date':(timezone.localdate()+timedelta(days=100)).isoformat(),
            'reference':reference or str(uuid.uuid4())})
        self.assertEqual(response.status_code,201,response.content)
        return response.json()['batch_id']

    def fill(self, prescription, batch, amount=4, key=None):
        self.act_as('pharmacist')
        return self.post(f'pharmacy/{prescription}/dispense/', {'batch_id':batch,'quantity':str(amount),
            'review_confirmed':True,'request_id':str(key or uuid.uuid4())})

    def test_permissions_and_minimal_pharmacy_patient_access(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/pharmacy/').status_code,401)
        for role in ['receptionist','accountant','laboratory']:
            self.act_as(role)
            self.assertEqual(self.client.get('/api/pharmacy/').status_code,403)
        for role in ['nurse','pharmacist']:
            self.act_as(role)
            self.assertEqual(self.post('pharmacy/',self.data).status_code,403)
        self.act_as('pharmacist')
        self.assertEqual(self.client.get('/api/consultations/').status_code,403)
        self.assertEqual(self.client.get('/api/patients/').status_code,403)
        self.assertEqual(self.client.get('/api/patient-options/').status_code,403)
        self.act_as('doctor')
        for path in ['pharmacy/receive/','pharmacy/batches/','pharmacy/movements/']:
            response=self.post(path,{}) if path.endswith('receive/') else self.client.get('/api/'+path)
            self.assertEqual(response.status_code,403)

    def test_prescription_snapshots_medicine_allergies_and_actor(self):
        self.data.update(patient_id=str(self.foreign_patient.pk), prescribed_by=self.users['nurse'].pk,
            allergies='Spoofed allergy text', medicine_name='Spoofed name')
        pk=self.prescribe()
        record=Prescription.objects.get(pk=pk)
        self.assertEqual(record.patient,self.patient)
        self.assertEqual(record.prescribed_by,self.users['doctor'])
        self.assertEqual(record.allergies,'Synthetic allergy record for testing')
        self.assertEqual(record.medicine_name,'Synthetic training medicine')
        self.assertTrue(AuditEvent.objects.filter(action='prescription.sign',object_id=str(pk)).exists())
        self.act_as('pharmacist')
        detail=self.client.get(f'/api/pharmacy/{pk}/').json()
        self.assertEqual(detail['allergy_status'],'known')
        self.assertNotIn('phone',detail)
        self.assertNotIn('symptoms',detail)

    def test_prescribing_rejects_invalid_quantity_missing_instructions_and_unreviewed_entry(self):
        for values in [{'quantity':'0'},{'quantity':'-1'},{'quantity':'2.5'},{'quantity':True},
                       {'quantity':'NaN'},{'quantity':'Infinity'},{'quantity':'1000001'},
                       {'dose':' '},{'route':''},{'instructions':[]},{'review_confirmed':'true'}]:
            with self.subTest(values=values):
                self.assertEqual(self.post('pharmacy/',{**self.data,**values}).status_code,400)
        self.medicine.active=False
        self.medicine.save()
        self.assertEqual(self.post('pharmacy/',self.data).status_code,400)
        self.assertEqual(Prescription.objects.count(),0)

    def test_stock_receipts_are_unique_preserve_batch_expiry_and_add_to_balance(self):
        batch_id=self.receive(reference='TEST-RECEIPT-01')
        result=self.post('pharmacy/receive/',{'medicine_id':self.medicine.pk,'quantity':'20','batch_number':'SYNTHETIC-01',
            'expiry_date':(timezone.localdate()+timedelta(days=100)).isoformat(),'reference':'TEST-RECEIPT-01'})
        self.assertEqual(result.status_code,409)
        self.assertEqual(MedicineBatch.objects.get(pk=batch_id).quantity_remaining,20)
        self.receive(amount=7,reference='TEST-RECEIPT-02')
        self.assertEqual(MedicineBatch.objects.get(pk=batch_id).quantity_remaining,27)
        result=self.post('pharmacy/receive/',{'medicine_id':self.medicine.pk,'quantity':'5','batch_number':'SYNTHETIC-01',
            'expiry_date':(timezone.localdate()+timedelta(days=200)).isoformat(),'reference':'TEST-RECEIPT-03'})
        self.assertEqual(result.status_code,400)
        self.assertEqual(StockMovement.objects.filter(kind='receipt').count(),2)

    def test_stock_receipts_reject_expired_and_zero_stock(self):
        self.act_as('pharmacist')
        data={'medicine_id':self.medicine.pk,'quantity':'10','batch_number':'A','expiry_date':timezone.localdate().isoformat(),'reference':'A'}
        self.assertEqual(self.post('pharmacy/receive/',data).status_code,400)
        data.update(expiry_date=(timezone.localdate()+timedelta(days=10)).isoformat(),quantity='0')
        self.assertEqual(self.post('pharmacy/receive/',data).status_code,400)
        self.assertFalse(MedicineBatch.objects.exists())

    def test_partial_and_full_dispensing_preserve_history_and_stock_ledger(self):
        pk=self.prescribe()
        batch=self.receive()
        self.assertEqual(self.fill(pk,batch,4).status_code,201)
        self.assertEqual(Prescription.objects.get(pk=pk).status,'active')
        self.assertEqual(self.fill(pk,batch,6).status_code,201)
        self.assertEqual(Prescription.objects.get(pk=pk).status,'completed')
        self.assertEqual(MedicineBatch.objects.get(pk=batch).quantity_remaining,10)
        self.assertEqual(StockMovement.objects.filter(kind='dispense').count(),2)
        self.assertEqual(self.fill(pk,batch,1).status_code,409)
        detail=self.client.get(f'/api/pharmacy/{pk}/').json()
        self.assertEqual(detail['dispensed_quantity'],10)
        self.assertEqual(detail['unfilled_quantity'],0)
        self.assertEqual(detail['dispenses'][0]['pharmacist'],'pharmacist')

    def test_retried_dispensing_request_does_not_deduct_stock_twice(self):
        pk=self.prescribe()
        batch=self.receive()
        key=uuid.uuid4()
        self.assertEqual(self.fill(pk,batch,10,key).status_code,201)
        self.assertEqual(self.fill(pk,batch,10,key).status_code,200)
        self.assertEqual(self.fill(pk,batch,9,key).status_code,409)
        self.assertEqual(MedicineBatch.objects.get(pk=batch).quantity_remaining,10)
        self.assertEqual(Dispense.objects.count(),1)

    def test_expired_wrong_medicine_overfill_and_inactive_stock_are_blocked(self):
        pk=self.prescribe()
        batch=self.receive(amount=3)
        self.assertEqual(self.fill(pk,batch,4).status_code,400)
        self.assertEqual(self.fill(pk,batch,11).status_code,400)
        MedicineBatch.objects.filter(pk=batch).update(expiry_date=timezone.localdate())
        self.assertEqual(self.fill(pk,batch,1).status_code,400)
        self.assertEqual(self.client.get('/api/pharmacy/batches/?available=1').json()['count'],0)
        MedicineBatch.objects.filter(pk=batch).update(expiry_date=timezone.localdate()+timedelta(days=100))
        self.medicine.active=False
        self.medicine.save()
        self.assertEqual(self.fill(pk,batch,1).status_code,400)
        inactive=self.client.get('/api/pharmacy/medicines/').json()['results'][0]
        self.assertEqual(inactive['available'],0)
        self.assertEqual(Dispense.objects.count(),0)

    def test_cancellation_after_partial_fill_does_not_restock_dispensed_medicine(self):
        pk=self.prescribe()
        batch=self.receive()
        self.assertEqual(self.fill(pk,batch,3).status_code,201)
        self.assertEqual(self.post(f'pharmacy/{pk}/cancel/',{'reason':'Synthetic correction'}).status_code,403)
        self.act_as('doctor')
        self.assertEqual(self.post(f'pharmacy/{pk}/cancel/',{'reason':' '}).status_code,400)
        self.assertEqual(self.post(f'pharmacy/{pk}/cancel/',{'reason':'Synthetic correction'}).status_code,200)
        self.assertEqual(self.fill(pk,batch,1).status_code,409)
        self.assertEqual(MedicineBatch.objects.get(pk=batch).quantity_remaining,17)
        self.assertEqual(Dispense.objects.count(),1)

    def test_write_off_requires_reason_records_ledger_and_handles_retries(self):
        batch=self.receive()
        data={'quantity':'5','reason':'Synthetic damaged stock','request_id':str(uuid.uuid4())}
        self.assertEqual(self.post(f'pharmacy/batches/{batch}/write-off/',data).status_code,200)
        self.assertEqual(self.post(f'pharmacy/batches/{batch}/write-off/',data).status_code,200)
        self.assertEqual(MedicineBatch.objects.get(pk=batch).quantity_remaining,15)
        self.assertEqual(StockMovement.objects.filter(kind='write_off').count(),1)
        self.assertEqual(self.post(f'pharmacy/batches/{batch}/write-off/',{**data,'quantity':'30','request_id':str(uuid.uuid4())}).status_code,400)

    def test_branch_scoping_and_wrong_medicine_batches(self):
        self.assertEqual(self.post('pharmacy/',{**self.data,'medicine_id':self.other_medicine.pk}).status_code,400)
        pk=self.prescribe()
        other_batch=MedicineBatch.objects.create(branch=self.other,medicine=self.other_medicine,batch_number='OTHER',
            expiry_date=timezone.localdate()+timedelta(days=100),quantity_received=20,quantity_remaining=20)
        self.assertEqual(self.fill(pk,other_batch.pk,1).status_code,400)
        profile=StaffProfile.objects.get(user=self.users['pharmacist'])
        profile.branch=self.other
        profile.save()
        self.assertEqual(self.client.get('/api/pharmacy/').json()['count'],0)
        self.assertEqual(self.client.get(f'/api/pharmacy/{pk}/').status_code,404)
        self.assertEqual(self.fill(pk,other_batch.pk,1).status_code,404)

    def test_medicine_identity_cannot_change_after_stock_or_prescribing(self):
        self.receive()
        self.medicine.strength='Different identity'
        with self.assertRaises(ValidationError):
            self.medicine.full_clean()
        self.medicine.refresh_from_db()
        self.medicine.active=False
        self.medicine.full_clean()
        self.medicine.save()

    def test_stock_availability_excludes_expiring_today_and_tracks_low_stock(self):
        batch=self.receive(amount=5)
        response=self.client.get('/api/pharmacy/medicines/').json()['results'][0]
        self.assertEqual(response['available'],5)
        self.assertTrue(response['low_stock'])
        MedicineBatch.objects.filter(pk=batch).update(expiry_date=timezone.localdate())
        self.assertEqual(self.client.get('/api/pharmacy/medicines/').json()['results'][0]['available'],0)

    def test_review_confirmation_and_csrf_are_required(self):
        pk=self.prescribe()
        batch=self.receive()
        self.assertEqual(self.post(f'pharmacy/{pk}/dispense/',{'quantity':'1','batch_id':batch,'request_id':str(uuid.uuid4())}).status_code,400)
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.users['doctor'])
        self.assertEqual(client.post('/api/pharmacy/',json.dumps(self.data),content_type='application/json').status_code,403)


class ConcurrentDispensingTests(TransactionTestCase):
    def test_two_prescriptions_cannot_oversell_one_batch(self):
        branch=Branch.objects.create(name='Synthetic race branch',code='race')
        department=Department.objects.create(branch=branch,name='Synthetic clinic',code='clinic',category='clinical',description='Test')
        user=User.objects.create_user('synthetic-race-pharmacist')
        StaffProfile.objects.create(user=user,branch=branch,role='pharmacist')
        patient=Patient.objects.create(branch=branch,first_name='Synthetic',last_name='Race',date_of_birth='2000-01-01',sex='female',phone='+2348031234567')
        appointment=Appointment.objects.create(branch=branch,patient=patient,department=department,scheduled_at=timezone.now())
        consultation=Consultation.objects.create(branch=branch,patient=patient,appointment=appointment,clinician=user,
            symptoms='Test',diagnosis='Test',treatment_plan='Test',allergy_status='unknown')
        medicine=Medicine.objects.create(branch=branch,code='test',name='Synthetic test',strength='Dummy',form='Dummy',dispensing_unit='units')
        batch=MedicineBatch.objects.create(branch=branch,medicine=medicine,batch_number='RACE',expiry_date=timezone.localdate()+timedelta(days=10),quantity_received=10,quantity_remaining=10)
        records=[Prescription.objects.create(branch=branch,patient=patient,consultation=consultation,medicine=medicine,
            medicine_name=medicine.name,strength='Dummy',form='Dummy',dispensing_unit='units',dose='Dummy',route='Dummy',
            frequency='Dummy',duration='Dummy',quantity=8,instructions='Synthetic test only',allergy_status='unknown',prescribed_by=user) for _ in range(2)]
        def dispense_one(pk):
            close_old_connections()
            try:
                client=Client()
                client.force_login(User.objects.get(pk=user.pk))
                return client.post(f'/api/pharmacy/{pk}/dispense/',json.dumps({'batch_id':batch.pk,'quantity':'8','review_confirmed':True,'request_id':str(uuid.uuid4())}),content_type='application/json').status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(dispense_one,[r.pk for r in records]))
        self.assertEqual(sorted(outcomes),[201,400])
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_remaining,2)
        self.assertEqual(Dispense.objects.count(),1)
