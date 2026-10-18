import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import models
from django.db.models import Q


class Branch(models.Model):
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=20, unique=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Department(models.Model):
    class Category(models.TextChoices):
        CLINICAL = 'clinical', 'Clinical care'
        DIAGNOSTICS = 'diagnostics', 'Diagnostics & treatment'
        OPERATIONS = 'operations', 'Hospital operations'
        ADMINISTRATION = 'administration', 'Administration'

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=30)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.CharField(max_length=250)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['branch', 'code'], name='department_branch_code')]

    def __str__(self):
        return f'{self.name} ({self.branch.code})'


class StaffProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = 'administrator', 'Hospital administrator'
        RECEPTION = 'receptionist', 'Receptionist'
        DOCTOR = 'doctor', 'Doctor'
        NURSE = 'nurse', 'Nurse'
        ACCOUNTS = 'accountant', 'Accountant'
        LAB = 'laboratory', 'Laboratory scientist'
        PHARMACY = 'pharmacist', 'Pharmacist'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hospital_profile')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    role = models.CharField(max_length=20, choices=Role.choices)

    def __str__(self):
        return f'{self.user} · {self.get_role_display()}'


class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hospital_number = models.CharField(max_length=24, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    date_of_birth = models.DateField()
    sex = models.CharField(max_length=12, choices=[('female', 'Female'), ('male', 'Male'), ('other', 'Other')])
    phone = models.CharField(max_length=20, validators=[RegexValidator(r'^\+234[789]\d{9}$', 'Use a Nigerian mobile number, e.g. +2348031234567.')])
    address = models.TextField(blank=True, max_length=500)
    next_of_kin_name = models.CharField(max_length=160, blank=True)
    next_of_kin_phone = models.CharField(max_length=20, blank=True, validators=[RegexValidator(r'^\+234[789]\d{9}$', 'Use a Nigerian mobile number.')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.hospital_number:
            self.hospital_number = f'DH-{uuid.uuid4().hex[:12].upper()}'
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    def __str__(self):
        return f'{self.hospital_number} · {self.full_name}'


class Appointment(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        CHECKED_IN = 'checked_in', 'Checked in'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_at']
        constraints = [models.UniqueConstraint(fields=['patient', 'scheduled_at'], condition=~Q(status='cancelled'), name='patient_active_appointment_slot')]


class Admission(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    ward = models.CharField(max_length=80)
    bed = models.CharField(max_length=20)
    admitted_at = models.DateTimeField(auto_now_add=True)
    discharged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-admitted_at']
        constraints = [
            models.UniqueConstraint(fields=['branch', 'ward', 'bed'], condition=Q(discharged_at__isnull=True), name='one_active_patient_per_bed'),
            models.UniqueConstraint(fields=['patient'], condition=Q(discharged_at__isnull=True), name='one_active_admission_per_patient'),
        ]


class Invoice(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    status = models.CharField(max_length=12, choices=[('unpaid', 'Unpaid'), ('paid', 'Paid')], default='unpaid')
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='positive_invoice_amount')]


class Consultation(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    appointment = models.OneToOneField(Appointment, on_delete=models.PROTECT)
    clinician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    symptoms = models.TextField(max_length=10000)
    examination = models.TextField(blank=True, max_length=10000)
    diagnosis = models.TextField(max_length=5000)
    treatment_plan = models.TextField(max_length=10000)
    allergy_status = models.CharField(max_length=12, choices=[('unknown', 'Not assessed / unknown'), ('none', 'No known allergies'), ('known', 'Known allergies')])
    allergies = models.TextField(blank=True, max_length=2000)
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(25), MaxValueValidator(45)])
    pulse = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(20), MaxValueValidator(250)])
    respiratory_rate = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(100)])
    oxygen_saturation = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    systolic = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(40), MaxValueValidator(300)])
    diastolic = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(20), MaxValueValidator(200)])
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(500)])
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_instructions = models.TextField(blank=True, max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        if self.appointment_id and (self.appointment.branch_id != self.branch_id or self.appointment.patient_id != self.patient_id):
            raise ValidationError('The appointment, patient and consultation must belong to the same branch.')
        if (self.systolic is None) != (self.diastolic is None):
            raise ValidationError('Enter both blood pressure values, or leave both blank.')
        if self.systolic is not None and self.diastolic is not None and self.systolic <= self.diastolic:
            raise ValidationError('Systolic pressure must exceed diastolic pressure.')
        if self.allergy_status == 'known' and not self.allergies.strip():
            raise ValidationError('Describe the known allergies and reactions.')
        if self.allergy_status != 'known' and self.allergies.strip():
            raise ValidationError('Select Known allergies when entering allergy details.')
        if self.follow_up_date and self.follow_up_date < timezone.localdate():
            raise ValidationError('Follow-up cannot be before today.')


class ConsultationAddendum(models.Model):
    consultation = models.ForeignKey(Consultation, on_delete=models.PROTECT, related_name='addenda')
    clinician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    note = models.TextField(max_length=10000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']


class LabTest(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=160)
    specimen_type = models.CharField(max_length=100)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['branch', 'code'], name='lab_test_branch_code')]

    def __str__(self):
        return f'{self.code} · {self.name} ({self.branch.code})'


class LabOrder(models.Model):
    class Status(models.TextChoices):
        REQUESTED = 'requested', 'Requested'
        COLLECTED = 'collected', 'Specimen collected'
        REPORTED = 'reported', 'Reported'
        CANCELLED = 'cancelled', 'Cancelled'

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    consultation = models.ForeignKey(Consultation, on_delete=models.PROTECT, related_name='lab_orders')
    test = models.ForeignKey(LabTest, on_delete=models.PROTECT)
    test_name = models.CharField(max_length=160)
    specimen_type = models.CharField(max_length=100)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='lab_requests')
    indication = models.TextField(max_length=2000)
    priority = models.CharField(max_length=10, choices=[('routine', 'Routine'), ('urgent', 'Urgent')], default='routine')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)
    specimen_id = models.CharField(max_length=100, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='lab_collections')
    cancellation_reason = models.TextField(blank=True, max_length=2000)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='cancelled_lab_orders')

    class Meta:
        ordering = ['-created_at', '-pk']

    def clean(self):
        if self.consultation_id and (self.consultation.branch_id != self.branch_id or self.consultation.patient_id != self.patient_id):
            raise ValidationError('The laboratory order must match the consultation patient and branch.')
        if self.test_id and self.test.branch_id != self.branch_id:
            raise ValidationError('The laboratory test must belong to this branch.')


class LabReport(models.Model):
    order = models.OneToOneField(LabOrder, on_delete=models.PROTECT, related_name='report')
    result_text = models.TextField(max_length=10000)
    reference_info = models.TextField(blank=True, max_length=3000)
    comments = models.TextField(blank=True, max_length=5000)
    signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    signed_at = models.DateTimeField(auto_now_add=True)


class LabReportAddendum(models.Model):
    report = models.ForeignKey(LabReport, on_delete=models.PROTECT, related_name='addenda')
    note = models.TextField(max_length=10000)
    signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    signed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['signed_at', 'pk']


class Medicine(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=160)
    strength = models.CharField(max_length=80)
    form = models.CharField(max_length=80)
    dispensing_unit = models.CharField(max_length=30)
    low_stock_threshold = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name', 'strength', 'pk']
        constraints = [models.UniqueConstraint(fields=['branch', 'code'], name='medicine_branch_code')]

    def __str__(self):
        return f'{self.code} · {self.name} {self.strength} ({self.branch.code})'

    def clean(self):
        if self.pk:
            old = Medicine.objects.get(pk=self.pk)
            identity = ['branch_id', 'code', 'name', 'strength', 'form', 'dispensing_unit']
            if any(getattr(old, field) != getattr(self, field) for field in identity) and (self.batches.exists() or self.prescription_set.exists()):
                raise ValidationError('Medicine identity cannot change after stock or prescribing. Deactivate it and create a separate catalogue entry.')


class MedicineBatch(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name='batches')
    batch_number = models.CharField(max_length=100)
    expiry_date = models.DateField()
    quantity_received = models.PositiveIntegerField(default=0)
    quantity_remaining = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['expiry_date', 'pk']
        constraints = [
            models.UniqueConstraint(fields=['medicine', 'batch_number'], name='medicine_batch_number'),
            models.CheckConstraint(condition=Q(quantity_remaining__gte=0) & Q(quantity_remaining__lte=models.F('quantity_received')), name='valid_batch_balance'),
        ]


class Prescription(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    consultation = models.ForeignKey(Consultation, on_delete=models.PROTECT, related_name='prescriptions')
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT)
    medicine_name = models.CharField(max_length=160)
    strength = models.CharField(max_length=80)
    form = models.CharField(max_length=80)
    dispensing_unit = models.CharField(max_length=30)
    dose = models.CharField(max_length=200)
    route = models.CharField(max_length=100)
    frequency = models.CharField(max_length=200)
    duration = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(1000000)])
    instructions = models.TextField(max_length=5000)
    allergy_status = models.CharField(max_length=12, choices=[('unknown', 'Not assessed / unknown'), ('none', 'No known allergies'), ('known', 'Known allergies')])
    allergies = models.TextField(blank=True, max_length=2000)
    prescribed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='prescriptions_written')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, choices=[('active', 'Active'), ('completed', 'Dispensed'), ('cancelled', 'Cancelled')], default='active')
    cancellation_reason = models.TextField(blank=True, max_length=2000)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='prescriptions_cancelled')

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name='positive_prescription_quantity')]

    def clean(self):
        if self.consultation_id and (self.consultation.branch_id != self.branch_id or self.consultation.patient_id != self.patient_id):
            raise ValidationError('Prescription patient and branch must match the consultation.')
        if self.medicine_id and self.medicine.branch_id != self.branch_id:
            raise ValidationError('Choose a medicine in the current branch.')


class Dispense(models.Model):
    prescription = models.ForeignKey(Prescription, on_delete=models.PROTECT, related_name='dispenses')
    batch = models.ForeignKey(MedicineBatch, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    pharmacist = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name='positive_dispense_quantity')]


class StockMovement(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    batch = models.ForeignKey(MedicineBatch, on_delete=models.PROTECT)
    prescription = models.ForeignKey(Prescription, on_delete=models.PROTECT, null=True, blank=True)
    kind = models.CharField(max_length=12, choices=[('receipt', 'Receipt'), ('dispense', 'Dispense'), ('write_off', 'Write-off')])
    quantity = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    reference = models.CharField(max_length=100, blank=True)
    request_id = models.UUIDField(unique=True, null=True, blank=True)
    note = models.CharField(max_length=500, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['branch', 'reference'], condition=Q(kind='receipt'), name='unique_stock_receipt_reference'),
            models.CheckConstraint(condition=(Q(kind='receipt') & Q(quantity__gt=0)) | (Q(kind__in=['dispense', 'write_off']) & Q(quantity__lt=0)), name='valid_stock_movement_direction'),
        ]


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=40, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
