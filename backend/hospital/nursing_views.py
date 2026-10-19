import uuid
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Admission, InpatientRecord, InpatientAddendum, MedicationAdministration, Prescription, Dispense
from .views import endpoint, scoped, body, audit, role_for

NURSES = {'administrator', 'nurse'}
DOCTORS = {'administrator', 'doctor'}
VITALS = ['temperature', 'pulse', 'respiratory_rate', 'oxygen_saturation', 'systolic', 'diastolic', 'pain_score']
KINDS = ['observation', 'nursing_note', 'care_plan', 'ward_round']


def text(data, key):
    value = data.get(key, '')
    if not isinstance(value, str):
        raise ValidationError('Clinical text must contain text.')
    return value.strip()


def actor(user):
    return user.get_full_name() or user.username


def denied(request, kind):
    roles = DOCTORS if kind == 'ward_round' else NURSES
    if role_for(request.user) not in roles:
        return JsonResponse({'error': 'This clinical entry must be recorded by the appropriate doctor or nurse.'}, status=403)


def admission_json(record):
    return {'id': record.pk, 'patient_name': record.patient.full_name, 'hospital_number': record.patient.hospital_number,
        'ward': record.ward, 'bed': record.bed, 'department': record.department.name,
        'admitted_at': record.admitted_at.isoformat(), 'discharged_at': record.discharged_at.isoformat() if record.discharged_at else None}


def admission_for(request, pk, write=False):
    records = scoped(Admission, request)
    if write:
        records = records.select_for_update()
    return records.filter(pk=pk).first()


def missing():
    return JsonResponse({'error': 'Admission or clinical record not found.'}, status=404)


def event_time(value, admission):
    stamp = parse_datetime(value) if isinstance(value, str) else None
    if not stamp or timezone.is_naive(stamp) or stamp > timezone.now() or stamp < admission.admitted_at:
        raise ValidationError('Use an actual WAT time during this admission, not before admission or in the future.')
    if admission.discharged_at and stamp > admission.discharged_at:
        raise ValidationError('The event time cannot be after discharge.')
    return stamp


def require_active(admission):
    if admission.discharged_at:
        raise ValidationError('This admission is discharged. Existing records remain readable; use an addendum for corrections.')


def addenda_json(record):
    return [{'id': a.pk, 'note': a.note, 'recorded_by': actor(a.recorded_by), 'recorded_at': a.recorded_at.isoformat()}
        for a in record.addenda.select_related('recorded_by').all()]


def care_json(record):
    return {'id': record.pk, 'kind': record.kind, 'occurred_at': record.occurred_at.isoformat(), 'content': record.content,
        'goals': record.goals, 'interventions': record.interventions, 'review_date': record.review_date.isoformat() if record.review_date else None,
        'vitals': {key: str(getattr(record, key)) if getattr(record, key) is not None else None for key in VITALS},
        'recorded_by': actor(record.recorded_by), 'recorded_at': record.recorded_at.isoformat(), 'addenda': addenda_json(record)}


@endpoint(['GET'], 'nursing')
def admissions(request):
    records = scoped(Admission, request).select_related('patient', 'department')
    state = request.GET.get('state', 'active')
    if state not in {'active', 'discharged', 'all'}:
        raise ValidationError('Choose an active, discharged or all-admissions filter.')
    if state != 'all':
        records = records.filter(discharged_at__isnull=state == 'active')
    query = request.GET.get('q', '')[:120]
    if query:
        records = records.filter(Q(patient__first_name__icontains=query) | Q(patient__last_name__icontains=query)
            | Q(patient__hospital_number__icontains=query) | Q(ward__icontains=query) | Q(bed__icontains=query))
    page = max(1, int(request.GET.get('page', 1)))
    audit(request, 'nursing_admissions.read')
    return JsonResponse({'count': records.count(), 'results': [admission_json(a) for a in records.order_by('-admitted_at', '-pk')[(page-1)*20:page*20]]})


@endpoint(['GET'], 'nursing')
def admission_detail(request, pk):
    admission = admission_for(request, pk)
    if admission is None:
        return missing()
    audit(request, 'nursing_admission.read', admission)
    return JsonResponse(admission_json(admission))


@endpoint(['GET', 'POST'], 'nursing')
def records(request, pk):
    admission = admission_for(request, pk, write=request.method == 'POST')
    if admission is None:
        return missing()
    if request.method == 'POST':
        data = body(request)
        kind = text(data, 'kind')
        if kind not in KINDS:
            raise ValidationError('Choose a valid clinical record type.')
        error = denied(request, kind)
        if error is not None:
            return error
        require_active(admission)
        if data.get('review_confirmed') is not True:
            raise ValidationError('Review the clinical entry before signing.')
        stamp = event_time(data.get('occurred_at'), admission)
        values = {field: text(data, field) for field in ['content', 'goals', 'interventions']}
        for field in VITALS:
            value = data.get(field)
            if value is None or value == '':
                values[field] = None
                continue
            if kind != 'observation' or isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValidationError('Vital signs belong in an observation record and must be numeric.')
            number = Decimal(str(value))
            if not number.is_finite() or (field != 'temperature' and number != number.to_integral_value()):
                raise ValidationError('Enter finite measurements; counts, pressures and pain scores must be whole numbers.')
            values[field] = number
        if kind != 'care_plan' and (values['goals'] or values['interventions'] or data.get('review_date')):
            raise ValidationError('Goals, interventions and review dates belong in care plans.')
        review_date = date.fromisoformat(data['review_date']) if data.get('review_date') else None
        if review_date and review_date < timezone.localdate(stamp):
            raise ValidationError('A review date cannot precede the care plan.')
        record = InpatientRecord(branch=request.branch, admission=admission, kind=kind, occurred_at=stamp,
            recorded_by=request.user, review_date=review_date, **values)
        record.full_clean()
        record.save()
        audit(request, 'inpatient_record.sign', record)
        return JsonResponse({'id': record.pk}, status=201)
    kind = request.GET.get('kind', 'observation')
    if kind not in KINDS:
        raise ValidationError('Choose a valid record type.')
    entries = scoped(InpatientRecord, request).filter(admission=admission, kind=kind).select_related('recorded_by')
    page = max(1, int(request.GET.get('page', 1)))
    audit(request, 'inpatient_records.read', admission)
    return JsonResponse({'count': entries.count(), 'results': [care_json(r) for r in entries[(page-1)*20:page*20]]})


@endpoint(['POST'], 'nursing')
def addendum(request, pk, record_type, record_id):
    admission = admission_for(request, pk)
    if admission is None:
        return missing()
    model = InpatientRecord if record_type == 'care' else MedicationAdministration
    record = scoped(model, request).filter(admission=admission, pk=record_id).first()
    if record is None:
        return missing()
    error = denied(request, record.kind if record_type == 'care' else 'medication')
    if error is not None:
        return error
    data = body(request)
    if data.get('review_confirmed') is not True:
        raise ValidationError('Review the addendum before signing.')
    correction = InpatientAddendum(recorded_by=request.user, note=text(data, 'note'),
        **{('care_record' if record_type == 'care' else 'medication_record'): record})
    correction.full_clean()
    correction.save()
    audit(request, 'inpatient_record.addendum', correction)
    return JsonResponse({'id': correction.pk}, status=201)


@endpoint(['GET'], 'nursing')
def medication_options(request, pk):
    admission = admission_for(request, pk)
    if admission is None:
        return missing()
    query = request.GET.get('q', '')[:120]
    prescriptions = scoped(Prescription, request).filter(patient=admission.patient, status__in=['active', 'completed'])
    if query:
        prescriptions = prescriptions.filter(medicine_name__icontains=query)
    results = []
    for prescription in prescriptions[:30]:
        supplies = []
        for d in prescription.dispenses.select_related('batch').all():
            used = MedicationAdministration.objects.filter(dispense=d, outcome='given').aggregate(total=Sum('quantity_used'))['total'] or Decimal('0')
            supplies.append({'id': d.pk, 'batch_number': d.batch.batch_number, 'expiry_date': d.batch.expiry_date.isoformat(),
                'available': str(Decimal(d.quantity)-used), 'dispensed_at': d.created_at.isoformat()})
        results.append({'id': prescription.pk, 'medicine': prescription.medicine_name, 'strength': prescription.strength,
            'form': prescription.form, 'dose': prescription.dose, 'route': prescription.route, 'frequency': prescription.frequency,
            'duration': prescription.duration, 'instructions': prescription.instructions, 'dispensing_unit': prescription.dispensing_unit,
            'allergy_status': prescription.allergy_status, 'allergies': prescription.allergies, 'dispenses': supplies})
    audit(request, 'inpatient_prescriptions.read', admission)
    return JsonResponse({'results': results})


def medication_json(record):
    p = record.prescription
    return {'id': record.pk, 'prescription_id': p.pk, 'medicine': p.medicine_name, 'strength': p.strength,
        'route': p.route, 'dispensing_unit': p.dispensing_unit, 'scheduled_at': record.scheduled_at.isoformat(),
        'occurred_at': record.occurred_at.isoformat(), 'outcome': record.outcome, 'dose_given': record.dose_given,
        'quantity_used': str(record.quantity_used) if record.quantity_used is not None else None, 'reason': record.reason,
        'batch_number': record.dispense.batch.batch_number if record.dispense_id else None,
        'recorded_by': actor(record.recorded_by), 'recorded_at': record.recorded_at.isoformat(), 'addenda': addenda_json(record)}


@endpoint(['GET', 'POST'], 'nursing')
def medications(request, pk):
    admission = admission_for(request, pk, write=request.method == 'POST')
    if admission is None:
        return missing()
    if request.method == 'GET':
        records = scoped(MedicationAdministration, request).filter(admission=admission).select_related('prescription', 'dispense__batch', 'recorded_by')
        page = max(1, int(request.GET.get('page', 1)))
        audit(request, 'medication_administrations.read', admission)
        return JsonResponse({'count': records.count(), 'results': [medication_json(r) for r in records[(page-1)*20:page*20]]})
    error = denied(request, 'medication')
    if error is not None:
        return error
    data = body(request)
    if data.get('review_confirmed') is not True:
        raise ValidationError('Confirm identity, current allergies, prescription and this admission before signing.')
    request_id = uuid.UUID(str(data.get('request_id', '')))
    scheduled = event_time(data.get('scheduled_at'), admission)
    occurred = event_time(data.get('occurred_at'), admission)
    outcome, dose, reason = text(data, 'outcome'), text(data, 'dose_given'), text(data, 'reason')
    if outcome not in {'given', 'not_given', 'refused', 'withheld'}:
        raise ValidationError('Choose a valid administration outcome.')
    amount = Decimal(str(data.get('quantity_used'))) if data.get('quantity_used') not in (None, '') else None
    if amount is not None and (not amount.is_finite() or amount < Decimal('0.001') or amount > Decimal('1000000') or amount.as_tuple().exponent < -3):
        raise ValidationError('Enter a positive quantity in dispensing units, with no more than three decimal places.')
    previous = scoped(MedicationAdministration, request).filter(request_id=request_id).first()
    if previous:
        same = previous.admission_id == admission.pk and str(previous.prescription_id) == str(data.get('prescription_id')) and previous.outcome == outcome and previous.scheduled_at == scheduled and previous.occurred_at == occurred and previous.dose_given == dose and previous.reason == reason and previous.quantity_used == amount and str(previous.dispense_id or '') == str(data.get('dispense_id') or '')
        if same:
            return JsonResponse({'id': previous.pk, 'already_recorded': True})
        return JsonResponse({'error': 'This administration reference was already used for a different entry.'}, status=409)
    require_active(admission)
    prescription = scoped(Prescription, request).select_for_update().filter(pk=data['prescription_id'], patient=admission.patient).first()
    if prescription is None or prescription.status == 'cancelled':
        raise ValidationError('Choose a current prescription for this admission’s patient.')
    if scoped(MedicationAdministration, request).filter(admission=admission, prescription=prescription, scheduled_at=scheduled, outcome='given').exists():
        return JsonResponse({'error': 'A given dose is already recorded for this prescription and administration slot. Use an addendum for documentation corrections.'}, status=409)
    if scheduled < prescription.created_at or occurred < prescription.created_at:
        raise ValidationError('Administration times cannot precede the prescription.')
    supply = None
    if outcome == 'given':
        if not prescription.medicine.active:
            raise ValidationError('This medicine is inactive. Ask the clinical/pharmacy team to review it.')
        if not dose or amount is None:
            raise ValidationError('Record the actual dose and quantity used from dispensed supplies.')
        supply = Dispense.objects.select_for_update().filter(pk=data.get('dispense_id'), prescription=prescription).first()
        if supply is None or supply.created_at > occurred or supply.batch.expiry_date <= timezone.localdate(occurred):
            raise ValidationError('Choose a matching, previously dispensed supply that was not expired at administration.')
        used = MedicationAdministration.objects.filter(dispense=supply, outcome='given').aggregate(total=Sum('quantity_used'))['total'] or Decimal('0')
        if amount > Decimal(supply.quantity)-used:
            raise ValidationError('Quantity exceeds the remaining quantity in this dispensed supply.')
    elif not reason or dose or amount is not None or data.get('dispense_id'):
        raise ValidationError('For a dose not given, enter a reason and leave dose, quantity and dispensed supply blank.')
    record = MedicationAdministration(branch=request.branch, admission=admission, prescription=prescription, dispense=supply,
        scheduled_at=scheduled, occurred_at=occurred, outcome=outcome, dose_given=dose, quantity_used=amount,
        reason=reason, recorded_by=request.user, request_id=request_id)
    record.full_clean()
    record.save()
    audit(request, 'medication_administration.sign', record)
    return JsonResponse({'id': record.pk}, status=201)
