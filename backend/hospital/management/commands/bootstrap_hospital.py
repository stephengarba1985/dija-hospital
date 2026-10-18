from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from hospital.lab_catalogue import seed_tests
from hospital.models import Branch, Department, StaffProfile

DEPARTMENTS = [
    ('Outpatient clinic', 'opd', 'clinical', 'General consultations, follow-up visits and outpatient care.'),
    ('Accident & emergency', 'emergency', 'clinical', 'Triage, resuscitation and urgent medical care.'),
    ('Internal medicine', 'medicine', 'clinical', 'Adult medical care and specialist consultations.'),
    ('Surgery', 'surgery', 'clinical', 'Surgical consultations, procedures and postoperative care.'),
    ('Obstetrics & gynaecology', 'maternity', 'clinical', 'Antenatal, delivery, postnatal and women’s health services.'),
    ('Paediatrics', 'paediatrics', 'clinical', 'Children’s health, newborn care and immunisation.'),
    ('Intensive care', 'icu', 'clinical', 'Monitoring and care for critically ill patients.'),
    ('Orthopaedics', 'orthopaedics', 'clinical', 'Bone, joint and musculoskeletal care.'),
    ('Eye clinic', 'ophthalmology', 'clinical', 'Eye examinations, vision assessment and ophthalmic care.'),
    ('Dental clinic', 'dental', 'clinical', 'Oral health, dental consultations and procedures.'),
    ('Ear, nose & throat', 'ent', 'clinical', 'Specialist ear, nose and throat services.'),
    ('Mental health', 'mental-health', 'clinical', 'Psychiatric consultations and psychological support.'),
    ('Nursing services', 'nursing', 'clinical', 'Ward coordination, nursing care and patient observations.'),
    ('Physiotherapy', 'physiotherapy', 'clinical', 'Rehabilitation, mobility and physical therapy.'),
    ('Community health', 'community', 'clinical', 'Preventive care, outreach and public health services.'),
    ('Laboratory', 'laboratory', 'diagnostics', 'Specimen collection, investigations and laboratory results.'),
    ('Radiology & imaging', 'radiology', 'diagnostics', 'X-rays, ultrasound and diagnostic imaging.'),
    ('Pharmacy', 'pharmacy', 'diagnostics', 'Prescription review, dispensing and medicine stock.'),
    ('Blood bank', 'blood-bank', 'diagnostics', 'Donor services, blood storage and transfusion support.'),
    ('Operating theatre', 'theatre', 'operations', 'Theatre bookings, procedure scheduling and recovery.'),
    ('Medical records', 'records', 'operations', 'Patient registration, identifiers and record administration.'),
    ('Ambulance services', 'ambulance', 'operations', 'Emergency transport and patient transfers.'),
    ('Mortuary', 'mortuary', 'operations', 'Deceased identification, storage and release administration.'),
    ('Nutrition & dietetics', 'nutrition', 'operations', 'Nutritional assessment and hospital meal planning.'),
    ('Infection prevention', 'infection-control', 'operations', 'Infection surveillance, prevention and control.'),
    ('Sterilisation services', 'cssd', 'operations', 'Instrument decontamination, sterilisation and supply.'),
    ('Facilities & maintenance', 'facilities', 'operations', 'Equipment, utilities, housekeeping and laundry.'),
    ('Accounts & billing', 'accounts', 'administration', 'Naira billing, receipts, outstanding balances and finance.'),
    ('NHIA & HMO desk', 'insurance', 'administration', 'Insurance enrolment, authorisations and claims.'),
    ('Human resources', 'hr', 'administration', 'Staff records, rosters, leave and personnel administration.'),
    ('Procurement & stores', 'stores', 'administration', 'Purchasing, suppliers, consumables and stock control.'),
    ('Hospital administration', 'administration', 'administration', 'Hospital oversight, branch configuration and service planning.'),
    ('ICT & health information', 'ict', 'administration', 'System access, information services and reporting.'),
]


class Command(BaseCommand):
    help = 'Create the first branch and department directory. Does not create patients or passwords.'

    def handle(self, *args, **options):
        branch, _ = Branch.objects.get_or_create(code='main', defaults={'name': 'Dija Hospital · Main branch'})
        for name, code, category, description in DEPARTMENTS:
            Department.objects.get_or_create(branch=branch, code=code, defaults={'name': name, 'category': category, 'description': description})
        seed_tests(branch)
        for role, label in StaffProfile.Role.choices:
            Group.objects.get_or_create(name=label)
        self.stdout.write(self.style.SUCCESS(f'Dija Hospital: {Department.objects.filter(branch=branch).count()} departments configured.'))
