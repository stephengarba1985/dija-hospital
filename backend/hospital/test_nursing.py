import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, Client
from django.utils import timezone

from . import tests as core_tests
from .models import (Admission, Appointment, Consultation, Medicine, MedicineBatch, Prescription, Dispense,
    InpatientRecord, InpatientAddendum, MedicationAdministration, AuditEvent, StaffProfile)


class NursingWorkflowTests(TestCase):
    act_as = core_tests.HospitalWorkflowTests.act_as
    post = core_tests.HospitalWorkflowTests.post
    patch = core_tests.HospitalWorkflowTests.patch

    @classmethod
    def setUpTestData(cls):
        core_tests.HospitalWorkflowTests.setUpTestData.__func__(cls)
        medicine = Medicine.objects.create(branch=cls.branch,code='synthetic-care',name='Synthetic care medicine',strength='Dummy',form='Dummy',dispensing_unit='units')
        cls.batch = MedicineBatch.objects.create(branch=cls.branch,medicine=medicine,batch_number='CARE-TEST',
            expiry_date=timezone.localdate()+timedelta(days=100),quantity_received=25,quantity_remaining=20)
        appointment=Appointment.objects.create(branch=cls.branch,patient=cls.patient,department=cls.department,scheduled_at=timezone.now(),status='completed')
        consultation=Consultation.objects.create(branch=cls.branch,patient=cls.patient,appointment=appointment,clinician=cls.users['doctor'],
            symptoms='Synthetic',diagnosis='Synthetic',treatment_plan='Synthetic',allergy_status='unknown')
        cls.prescription=Prescription.objects.create(branch=cls.branch,patient=cls.patient,consultation=consultation,medicine=medicine,
            medicine_name=medicine.name,strength='Dummy',form='Dummy',dispensing_unit='units',dose='Synthetic dose',route='Synthetic route',
            frequency='Synthetic schedule',duration='Synthetic duration',quantity=5,instructions='Synthetic only',allergy_status='unknown',prescribed_by=cls.users['doctor'],status='completed')
        cls.supply=Dispense.objects.create(prescription=cls.prescription,batch=cls.batch,quantity=5,pharmacist=cls.users['administrator'],request_id=uuid.uuid4())
        cls.admission=Admission.objects.create(branch=cls.branch,patient=cls.patient,department=cls.department,ward='Synthetic ward',bed='A1')
        cls.other_admission=Admission.objects.create(branch=cls.other,patient=cls.foreign_patient,department=cls.other_department,ward='Foreign ward',bed='B1')

    def setUp(self):
        self.act_as('nurse')

    def observation(self, **values):
        return {'kind':'observation','occurred_at':timezone.now().isoformat(),'temperature':'36.7','review_confirmed':True,**values}

    def administration(self, **values):
        stamp=timezone.now().isoformat()
        return {'prescription_id':self.prescription.pk,'dispense_id':self.supply.pk,'scheduled_at':stamp,'occurred_at':stamp,
            'outcome':'given','dose_given':'Synthetic actual dose','quantity_used':'1.000','review_confirmed':True,'request_id':str(uuid.uuid4()),**values}

    def test_access_boundaries_and_branch_scope(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/nursing/').status_code,401)
        for role in ['receptionist','accountant','laboratory']:
            self.act_as(role)
            self.assertEqual(self.client.get('/api/nursing/').status_code,403)
        self.act_as('nurse')
        self.assertEqual(self.client.get(f'/api/nursing/?branch={self.other.pk}').json()['count'],1)
        for suffix in ['', 'records/', 'medications/', 'prescriptions/']:
            self.assertEqual(self.client.get(f'/api/nursing/{self.other_admission.pk}/{suffix}').status_code,404)
        self.assertEqual(self.post(f'nursing/{self.other_admission.pk}/records/',self.observation()).status_code,404)

    def test_observation_validates_values_and_preserves_zero(self):
        response=self.post(f'nursing/{self.admission.pk}/records/',self.observation(pain_score='0',systolic='120',diastolic='80'))
        self.assertEqual(response.status_code,201,response.content)
        result=self.client.get(f'/api/nursing/{self.admission.pk}/records/').json()['results'][0]
        self.assertEqual(result['vitals']['pain_score'],'0')
        self.assertIsNone(result['vitals']['pulse'])
        self.assertEqual(result['recorded_by'],'nurse')
        self.assertTrue(AuditEvent.objects.filter(action='inpatient_record.sign',object_id=str(response.json()['id'])).exists())
        for values in [{'temperature':''},{'temperature':'NaN'},{'pulse':'75.5'},{'oxygen_saturation':'101'},
                       {'systolic':'120'},{'systolic':'80','diastolic':'120'},{'pain_score':'11'},{'pulse':True},
                       {'occurred_at':(timezone.now()+timedelta(hours=1)).isoformat()},
                       {'occurred_at':(self.admission.admitted_at-timedelta(seconds=1)).isoformat()}]:
            self.assertEqual(self.post(f'nursing/{self.admission.pk}/records/',self.observation(**values)).status_code,400)

    def test_nursing_plans_notes_and_doctor_rounds_have_distinct_write_roles(self):
        for kind in ['nursing_note','care_plan']:
            payload=self.observation(kind=kind,temperature='',content='Synthetic entry',goals='Synthetic goal' if kind=='care_plan' else '',interventions='Synthetic intervention' if kind=='care_plan' else '')
            self.assertEqual(self.post(f'nursing/{self.admission.pk}/records/',payload).status_code,201)
        invalid=self.observation(kind='care_plan',temperature='',content='Plan')
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/records/',invalid).status_code,400)
        round_data=self.observation(kind='ward_round',temperature='',content='Synthetic ward round')
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/records/',round_data).status_code,403)
        self.act_as('doctor')
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/records/',round_data).status_code,201)
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/records/',self.observation()).status_code,403)
        self.assertEqual(self.client.get(f'/api/nursing/{self.admission.pk}/records/?kind=care_plan').status_code,200)

    def test_discharge_closes_new_entries_but_allows_dated_corrections(self):
        response=self.post(f'nursing/{self.admission.pk}/records/',self.observation())
        pk=response.json()['id']
        self.admission.discharged_at=timezone.now()
        self.admission.save()
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/records/',self.observation()).status_code,400)
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',self.administration()).status_code,400)
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/records/{pk}/addenda/',{'note':'Synthetic correction','review_confirmed':True}).status_code,201)
        result=self.client.get(f'/api/nursing/{self.admission.pk}/records/').json()['results'][0]
        self.assertEqual(result['vitals']['temperature'],'36.7')
        self.assertEqual(result['addenda'][0]['note'],'Synthetic correction')
        self.assertEqual(self.patch(f'nursing/{self.admission.pk}/records/',{}).status_code,405)
        self.assertEqual(self.client.get('/api/nursing/?state=discharged').json()['count'],1)

    def test_medication_given_uses_dispensed_supply_without_second_stock_deduction(self):
        result=self.post(f'nursing/{self.admission.pk}/medications/',self.administration(quantity_used='0.500'))
        self.assertEqual(result.status_code,201,result.content)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_remaining,20)
        detail=self.client.get(f'/api/nursing/{self.admission.pk}/medications/').json()['results'][0]
        self.assertEqual(detail['quantity_used'],'0.500')
        self.assertEqual(detail['batch_number'],'CARE-TEST')
        options=self.client.get(f'/api/nursing/{self.admission.pk}/prescriptions/').json()['results'][0]
        self.assertEqual(Decimal(options['dispenses'][0]['available']),Decimal('4.5'))

    def test_given_dose_idempotency_duplicate_slot_and_no_silent_overwrite(self):
        payload=self.administration()
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',payload).status_code,201)
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',payload).status_code,200)
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',{**payload,'request_id':str(uuid.uuid4())}).status_code,409)
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',{**payload,'dose_given':'Different'}).status_code,409)
        self.assertEqual(MedicationAdministration.objects.count(),1)

    def test_not_given_can_be_followed_by_late_given_for_same_slot(self):
        payload=self.administration(outcome='refused',dispense_id='',dose_given='',quantity_used='',reason='Synthetic refusal')
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',payload).status_code,201)
        later={**self.administration(),'scheduled_at':payload['scheduled_at']}
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',later).status_code,201)
        self.assertEqual(MedicationAdministration.objects.count(),2)
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',{**payload,'request_id':str(uuid.uuid4())}).status_code,409)

    def test_missing_reason_unconfirmed_and_invalid_quantities_are_rejected(self):
        for values in [{'quantity_used':'0'},{'quantity_used':'NaN'},{'quantity_used':'0.0001'}, {'quantity_used':'6'},
                       {'review_confirmed':False},{'dispense_id':''},{'dose_given':''},
                       {'outcome':'withheld','dose_given':'','quantity_used':'','dispense_id':'','reason':''},
                       {'outcome':'not_given','reason':'Synthetic'}]:
            self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',self.administration(**values)).status_code,400)
        self.assertEqual(MedicationAdministration.objects.count(),0)

    def test_expired_cancelled_or_wrong_patient_supplies_cannot_be_administered(self):
        self.batch.expiry_date=timezone.localdate()
        self.batch.save()
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',self.administration()).status_code,400)
        self.batch.expiry_date=timezone.localdate()+timedelta(days=10)
        self.batch.save()
        self.prescription.status='cancelled'
        self.prescription.save()
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',self.administration()).status_code,400)
        self.prescription.status='completed'
        self.prescription.patient=self.foreign_patient
        self.prescription.save()
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',self.administration()).status_code,400)

    def test_doctor_reads_medication_record_but_cannot_sign_administration(self):
        self.act_as('doctor')
        self.assertEqual(self.client.get(f'/api/nursing/{self.admission.pk}/medications/').status_code,200)
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/',self.administration()).status_code,403)

    def test_medication_addenda_preserve_consumed_supply(self):
        result=self.post(f'nursing/{self.admission.pk}/medications/',self.administration())
        pk=result.json()['id']
        self.assertEqual(self.post(f'nursing/{self.admission.pk}/medications/{pk}/addenda/',{'note':'Synthetic documentation correction','review_confirmed':True}).status_code,201)
        self.assertEqual(MedicationAdministration.objects.get(pk=pk).quantity_used,Decimal('1'))
        self.assertEqual(InpatientAddendum.objects.count(),1)

    def test_nursing_writes_have_csrf_protection(self):
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.users['nurse'])
        self.assertEqual(client.post(f'/api/nursing/{self.admission.pk}/records/',json.dumps(self.observation()),content_type='application/json').status_code,403)


class ConcurrentNursingTests(TransactionTestCase):
    def test_two_requests_cannot_record_same_given_dose(self):
        NursingWorkflowTests.setUpTestData.__func__(self.__class__)
        payload={'prescription_id':self.prescription.pk,'dispense_id':self.supply.pk,'outcome':'given','dose_given':'Synthetic',
            'quantity_used':'1','scheduled_at':timezone.now().isoformat(),'occurred_at':timezone.now().isoformat(),'review_confirmed':True}
        def submit(_):
            close_old_connections()
            try:
                client=Client()
                client.force_login(User.objects.get(pk=self.users['nurse'].pk))
                return client.post(f'/api/nursing/{self.admission.pk}/medications/',json.dumps({**payload,'request_id':str(uuid.uuid4())}),content_type='application/json').status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(submit,range(2)))
        self.assertEqual(sorted(results),[201,409])
        self.assertEqual(MedicationAdministration.objects.count(),1)
