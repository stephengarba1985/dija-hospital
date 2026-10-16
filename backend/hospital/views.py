import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from .models import Branch, Department, Patient, Appointment, Admission, Invoice, AuditEvent, Consultation, ConsultationAddendum

ROLES = {
    'consultations': {'administrator', 'doctor', 'nurse'},
    'patients': {'administrator', 'receptionist', 'doctor', 'nurse'},
    'appointments': {'administrator', 'receptionist', 'doctor', 'nurse'},
    'admissions': {'administrator', 'doctor', 'nurse'},
    'invoices': {'administrator', 'accountant'},
}


def role_for(user):
    if user.is_superuser:
        return 'administrator'
    profile = getattr(user, 'hospital_profile', None)
    return profile.role if profile else None


def branch_for(request):
    if request.user.is_superuser:
        branch_id = request.GET.get('branch')
        return Branch.objects.filter(active=True, **({'id': branch_id} if branch_id else {})).order_by('id').first()
    profile = getattr(request.user, 'hospital_profile', None)
    return profile.branch if profile and profile.branch.active else None


def audit(request, action, obj=None):
    AuditEvent.objects.create(actor=request.user, branch=request.branch, action=action,
        object_type=obj.__class__.__name__ if obj is not None else '', object_id=str(obj.pk) if obj is not None else '')


def endpoint(methods, resource=None):
    def decorate(fn):
        @require_http_methods(methods)
        @wraps(fn)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({'error': 'Please sign in to continue.'}, status=401)
            if not role_for(request.user):
                return JsonResponse({'error': 'Ask your administrator to assign a staff role and branch.'}, status=403)
            if resource and role_for(request.user) not in ROLES[resource]:
                return JsonResponse({'error': 'Your staff role does not have access to this module.'}, status=403)
            try:
                request.branch = branch_for(request)
                if request.branch is None:
                    return JsonResponse({'error': 'No active branch is assigned.'}, status=403)
                with transaction.atomic():
                    return fn(request, *args, **kwargs)
            except (ValueError, TypeError, KeyError, InvalidOperation, ValidationError) as exc:
                message = '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Check the supplied fields and try again.'
                return JsonResponse({'error': message}, status=400)
            except IntegrityError:
                return JsonResponse({'error': 'This record conflicts with an existing appointment, admission, or occupied bed.'}, status=409)
        return wrapped
    return decorate


def body(request):
    data = json.loads(request.body or '{}')
    if not isinstance(data, dict):
        raise ValueError('Expected an object')
    return data


def scoped(model, request):
    return model.objects.filter(branch=request.branch)


def related(model, pk, request):
    obj = scoped(model, request).filter(pk=pk).first()
    if obj is None:
        raise ValidationError('Select a record from your current branch.')
    return obj


def patient_json(p):
    return {'id': str(p.pk), 'hospital_number': p.hospital_number, 'name': p.full_name,
        'first_name': p.first_name, 'last_name': p.last_name, 'date_of_birth': p.date_of_birth.isoformat(),
        'sex': p.sex, 'phone': p.phone, 'created_at': p.created_at.isoformat()}


def appointment_json(a):
    return {'id': a.pk, 'patient_id': str(a.patient_id), 'patient_name': a.patient.full_name,
        'hospital_number': a.patient.hospital_number, 'department': a.department.name,
        'department_id': a.department_id, 'scheduled_at': a.scheduled_at.isoformat(), 'status': a.status}


def session_response(request):
    user = request.user
    payload = {'csrfToken': get_token(request), 'user': None}
    if user.is_authenticated:
        role = role_for(user)
        branch = branch_for(request)
        payload['user'] = {'name': user.get_full_name() or user.username, 'username': user.username,
            'role': role, 'branch': {'id': branch.pk, 'name': branch.name} if branch else None,
            'modules': [key for key, values in ROLES.items() if role in values]}
    response = JsonResponse(payload)
    response['Cache-Control'] = 'no-store'
    return response


@require_http_methods(['GET'])
def session(request):
    return session_response(request)


@require_http_methods(['POST'])
def login(request):
    # Development rate limit. Use a shared cache and reverse-proxy limits in production.
    key = f'login-attempts:{request.META.get("REMOTE_ADDR", "unknown")}'
    attempts = cache.get(key, 0)
    if attempts >= 10:
        return JsonResponse({'error': 'Too many attempts. Try again in 15 minutes.'}, status=429)
    try:
        data = body(request)
        user = authenticate(request, username=data.get('username', ''), password=data.get('password', ''))
    except (ValueError, TypeError):
        user = None
    if user is None:
        cache.set(key, attempts + 1, 900)
        return JsonResponse({'error': 'The username or password is incorrect.'}, status=401)
    if not role_for(user):
        return JsonResponse({'error': 'A hospital staff role must be assigned before signing in.'}, status=403)
    cache.delete(key)
    auth_login(request, user)
    request.branch = branch_for(request)
    audit(request, 'session.login')
    return session_response(request)


@require_http_methods(['POST'])
def logout(request):
    if request.user.is_authenticated:
        request.branch = branch_for(request)
        audit(request, 'session.logout')
    auth_logout(request)
    return JsonResponse({'ok': True})


@endpoint(['GET'])
def departments(request):
    return JsonResponse({'results': list(scoped(Department, request).filter(active=True).values('id', 'name', 'code', 'category', 'description'))})


@endpoint(['GET'])
def dashboard(request):
    role = role_for(request.user)
    today = timezone.localdate()
    appointments = scoped(Appointment, request).filter(scheduled_at__date=today).select_related('patient', 'department')
    access = role in ROLES['patients']
    audit(request, 'dashboard.read')
    return JsonResponse({
        'branch': request.branch.name,
        'date': today.isoformat(),
        'stats': {
            'patients': scoped(Patient, request).count(),
            'new_patients': scoped(Patient, request).filter(created_at__date=today).count(),
            'appointments': appointments.count(),
            'checked_in': appointments.filter(status='checked_in').count(),
            'admitted': scoped(Admission, request).filter(discharged_at__isnull=True).count(),
            'departments': scoped(Department, request).filter(active=True).count(),
            'outstanding': str(scoped(Invoice, request).filter(status='unpaid').aggregate(total=Sum('amount'))['total'] or 0) if role in ROLES['invoices'] else None,
        },
        'appointments': [appointment_json(a) for a in appointments[:6]] if access else [],
        'patients': [patient_json(p) for p in scoped(Patient, request)[:5]] if access else [],
        'department_activity': [{'name': d.name, 'count': appointments.filter(department=d).count()} for d in scoped(Department, request).filter(category='clinical')[:8]],
    })


def normalize_phone(value):
    value = re.sub(r'[\s()-]', '', str(value or ''))
    return '+234' + value[1:] if value.startswith('0') and len(value) == 11 else value


@endpoint(['GET', 'POST'], 'patients')
def patients(request):
    if request.method == 'POST':
        if role_for(request.user) not in {'administrator', 'receptionist', 'nurse'}:
            return JsonResponse({'error': 'Only registration staff can register a patient.'}, status=403)
        data = body(request)
        dob = date.fromisoformat(data['date_of_birth'])
        if dob > timezone.localdate() or dob.year < 1900:
            raise ValidationError('Enter a valid date of birth between 1900 and today.')
        patient = Patient(branch=request.branch, first_name=str(data['first_name']).strip(),
            last_name=str(data['last_name']).strip(), date_of_birth=dob, sex=data['sex'],
            phone=normalize_phone(data['phone']), address=data.get('address', ''),
            next_of_kin_name=data.get('next_of_kin_name', ''), next_of_kin_phone=normalize_phone(data.get('next_of_kin_phone', '')))
        patient.hospital_number = f'DH-{patient.id.hex[:12].upper()}'
        patient.full_clean()
        patient.save()
        audit(request, 'patient.create', patient)
        return JsonResponse(patient_json(patient), status=201)
    query = request.GET.get('q', '').strip()[:120]
    records = scoped(Patient, request)
    if query:
        records = records.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(hospital_number__icontains=query) | Q(phone__icontains=query))
    page = max(1, int(request.GET.get('page', 1)))
    audit(request, 'patients.read')
    return JsonResponse({'count': records.count(), 'results': [patient_json(p) for p in records[(page-1)*20:page*20]]})


@endpoint(['GET', 'POST'], 'appointments')
def appointments(request):
    if request.method == 'POST':
        data = body(request)
        patient = related(Patient, data['patient_id'], request)
        department = related(Department, data['department_id'], request)
        scheduled = parse_datetime(data['scheduled_at'])
        if not scheduled or timezone.is_naive(scheduled) or scheduled < timezone.now():
            raise ValidationError('Choose a future appointment time with a timezone.')
        if not department.active or department.category != 'clinical':
            raise ValidationError('Choose an active clinical department.')
        appointment = Appointment(branch=request.branch, patient=patient, department=department, scheduled_at=scheduled)
        appointment.full_clean()
        appointment.save()
        audit(request, 'appointment.create', appointment)
        return JsonResponse(appointment_json(appointment), status=201)
    records = scoped(Appointment, request).select_related('patient', 'department')
    if request.GET.get('for_consultation') == '1':
        records = records.filter(status='checked_in', consultation__isnull=True)
    if request.GET.get('date'):
        records = records.filter(scheduled_at__date=date.fromisoformat(request.GET['date']))
    audit(request, 'appointments.read')
    return JsonResponse({'results': [appointment_json(a) for a in records.order_by('-scheduled_at')[:100]]})


@endpoint(['PATCH'], 'appointments')
def appointment_update(request, pk):
    appointment = scoped(Appointment, request).select_for_update().select_related('patient', 'department').filter(pk=pk).first()
    if not appointment:
        return JsonResponse({'error': 'Appointment not found.'}, status=404)
    status = body(request).get('status')
    transitions = {'scheduled': {'checked_in', 'cancelled'}, 'checked_in': {'completed', 'cancelled'}}
    if status not in transitions.get(appointment.status, set()):
        raise ValidationError('This appointment cannot move to that status.')
    if status == 'completed' and role_for(request.user) not in {'administrator', 'doctor', 'nurse'}:
        return JsonResponse({'error': 'Clinical staff must complete the appointment.'}, status=403)
    appointment.status = status
    appointment.save(update_fields=['status'])
    audit(request, f'appointment.{status}', appointment)
    return JsonResponse(appointment_json(appointment))


@endpoint(['GET', 'POST'], 'admissions')
def admissions(request):
    if request.method == 'POST':
        data = body(request)
        department = related(Department, data['department_id'], request)
        if not department.active or department.category != 'clinical':
            raise ValidationError('Choose an active clinical department.')
        record = Admission(branch=request.branch, patient=related(Patient, data['patient_id'], request),
            department=department, ward=str(data['ward']).strip(), bed=str(data['bed']).strip().upper())
        record.full_clean()
        record.save()
        audit(request, 'admission.create', record)
        return JsonResponse({'id': record.pk}, status=201)
    records = scoped(Admission, request).select_related('patient', 'department')
    audit(request, 'admissions.read')
    return JsonResponse({'results': [{'id': a.pk, 'patient_name': a.patient.full_name,
        'hospital_number': a.patient.hospital_number, 'department': a.department.name, 'ward': a.ward,
        'bed': a.bed, 'admitted_at': a.admitted_at.isoformat(), 'discharged_at': a.discharged_at.isoformat() if a.discharged_at else None} for a in records[:100]]})


@endpoint(['PATCH'], 'admissions')
def discharge(request, pk):
    if role_for(request.user) not in {'administrator', 'doctor'}:
        return JsonResponse({'error': 'A doctor or administrator must authorize discharge.'}, status=403)
    record = scoped(Admission, request).select_for_update().filter(pk=pk).first()
    if not record:
        return JsonResponse({'error': 'Admission not found.'}, status=404)
    if record.discharged_at:
        raise ValidationError('This patient has already been discharged.')
    record.discharged_at = timezone.now()
    record.save(update_fields=['discharged_at'])
    audit(request, 'admission.discharge', record)
    return JsonResponse({'ok': True})


@endpoint(['GET', 'POST'], 'invoices')
def invoices(request):
    if request.method == 'POST':
        data = body(request)
        invoice = Invoice(branch=request.branch, patient=related(Patient, data['patient_id'], request),
            description=str(data['description']).strip(), amount=Decimal(str(data['amount'])))
        invoice.full_clean()
        invoice.save()
        audit(request, 'invoice.create', invoice)
        return JsonResponse({'id': invoice.pk}, status=201)
    records = scoped(Invoice, request).select_related('patient')
    audit(request, 'invoices.read')
    return JsonResponse({'results': [{'id': i.pk, 'patient_name': i.patient.full_name, 'hospital_number': i.patient.hospital_number,
        'description': i.description, 'amount': str(i.amount), 'status': i.status, 'created_at': i.created_at.isoformat()} for i in records[:100]]})


@endpoint(['PATCH'], 'invoices')
def invoice_paid(request, pk):
    invoice = scoped(Invoice, request).select_for_update().filter(pk=pk).first()
    if not invoice:
        return JsonResponse({'error': 'Invoice not found.'}, status=404)
    if invoice.status == 'paid':
        raise ValidationError('This invoice is already paid.')
    invoice.status, invoice.paid_at = 'paid', timezone.now()
    invoice.save(update_fields=['status', 'paid_at'])
    audit(request, 'invoice.mark_paid', invoice)
    return JsonResponse({'ok': True})


@endpoint(['GET'])
def patient_options(request):
    if role_for(request.user) not in set().union(*ROLES.values()):
        return JsonResponse({'error': 'Access denied.'}, status=403)
    query = request.GET.get('q', '')[:120]
    records = scoped(Patient, request)
    if query:
        records = records.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(hospital_number__icontains=query))
    audit(request, 'patient_options.read')
    return JsonResponse({'results': [{'id': str(p.pk), 'name': p.full_name, 'hospital_number': p.hospital_number} for p in records[:50]]})


CONSULTATION_TEXT = ['symptoms', 'examination', 'diagnosis', 'treatment_plan', 'allergy_status', 'allergies', 'follow_up_instructions']
CONSULTATION_NUMBERS = ['temperature', 'pulse', 'respiratory_rate', 'oxygen_saturation', 'systolic', 'diastolic', 'weight']


def consultation_json(record, detail=False):
    result = {'id': record.pk, 'patient_name': record.patient.full_name, 'patient_id': str(record.patient_id),
        'hospital_number': record.patient.hospital_number, 'department': record.appointment.department.name,
        'appointment_id': record.appointment_id, 'clinician': record.clinician.get_full_name() or record.clinician.username,
        'created_at': record.created_at.isoformat()}
    if detail:
        result.update({field: getattr(record, field) for field in CONSULTATION_TEXT})
        result['vitals'] = {field: str(getattr(record, field)) if getattr(record, field) is not None else None for field in CONSULTATION_NUMBERS}
        result['follow_up_date'] = record.follow_up_date.isoformat() if record.follow_up_date else None
        result['addenda'] = [{'id': a.pk, 'note': a.note, 'clinician': a.clinician.get_full_name() or a.clinician.username,
            'created_at': a.created_at.isoformat()} for a in record.addenda.select_related('clinician').all()]
    return result


@endpoint(['GET', 'POST'], 'consultations')
def consultations(request):
    if request.method == 'POST':
        if role_for(request.user) not in {'doctor', 'administrator'}:
            return JsonResponse({'error': 'A doctor or administrator must sign consultation notes.'}, status=403)
        data = body(request)
        appointment = scoped(Appointment, request).select_for_update().filter(pk=data['appointment_id']).first()
        if appointment is None:
            return JsonResponse({'error': 'Appointment not found in your branch.'}, status=404)
        if appointment.status != 'checked_in' or Consultation.objects.filter(appointment=appointment).exists():
            raise ValidationError('Select a checked-in appointment without an existing consultation.')
        values = {}
        for field in CONSULTATION_TEXT:
            value = data.get(field, '')
            if not isinstance(value, str):
                raise ValidationError('Clinical text fields must contain text.')
            values[field] = value.strip()
        for field in CONSULTATION_NUMBERS:
            value = data.get(field)
            if value is None or value == '':
                values[field] = None
                continue
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValidationError('Enter numeric vital signs.')
            number = Decimal(str(value))
            if not number.is_finite() or (field not in {'temperature', 'weight'} and number != number.to_integral_value()):
                raise ValidationError('Enter finite numeric values; counts and pressures must be whole numbers.')
            values[field] = number
        values['follow_up_date'] = date.fromisoformat(data['follow_up_date']) if data.get('follow_up_date') else None
        record = Consultation(branch=request.branch, patient=appointment.patient, appointment=appointment,
            clinician=request.user, **values)
        record.full_clean()
        record.save()
        appointment.status = 'completed'
        appointment.save(update_fields=['status'])
        audit(request, 'consultation.sign', record)
        audit(request, 'appointment.completed', appointment)
        return JsonResponse({'id': record.pk}, status=201)
    records = scoped(Consultation, request).select_related('patient', 'appointment__department', 'clinician')
    query = request.GET.get('q', '').strip()[:120]
    if query:
        records = records.filter(Q(patient__first_name__icontains=query) | Q(patient__last_name__icontains=query) | Q(patient__hospital_number__icontains=query))
    page = max(1, int(request.GET.get('page', 1)))
    audit(request, 'consultations.read')
    return JsonResponse({'count': records.count(), 'results': [consultation_json(c) for c in records[(page-1)*20:page*20]]})


@endpoint(['GET'], 'consultations')
def consultation_detail(request, pk):
    record = scoped(Consultation, request).select_related('patient', 'appointment__department', 'clinician').filter(pk=pk).first()
    if record is None:
        return JsonResponse({'error': 'Consultation not found.'}, status=404)
    audit(request, 'consultation.read', record)
    return JsonResponse(consultation_json(record, detail=True))


@endpoint(['POST'], 'consultations')
def consultation_addendum(request, pk):
    if role_for(request.user) not in {'doctor', 'administrator'}:
        return JsonResponse({'error': 'Only doctors and administrators can add clinical addenda.'}, status=403)
    record = scoped(Consultation, request).filter(pk=pk).first()
    if record is None:
        return JsonResponse({'error': 'Consultation not found.'}, status=404)
    note = body(request).get('note', '')
    if not isinstance(note, str):
        raise ValidationError('Enter a text addendum.')
    addendum = ConsultationAddendum(consultation=record, clinician=request.user, note=note.strip())
    addendum.full_clean()
    addendum.save()
    audit(request, 'consultation.addendum', addendum)
    return JsonResponse({'id': addendum.pk}, status=201)
