import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
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


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=40, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
