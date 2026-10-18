import uuid
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.utils import timezone

from .models import Medicine, MedicineBatch, Prescription, Dispense, StockMovement, Consultation
from .views import endpoint, scoped, related, body, audit, role_for

PRESCRIBERS = {'administrator', 'doctor'}
PHARMACY = {'administrator', 'pharmacist'}


def allow(request, roles):
    if role_for(request.user) not in roles:
        return JsonResponse({'error': 'Your staff role cannot perform this pharmacy action.'}, status=403)


def text(data, key):
    value = data.get(key, '')
    if not isinstance(value, str):
        raise ValidationError('Text fields must contain text.')
    return value.strip()


def quantity(value, zero=False):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValidationError('Enter a whole-number quantity.')
    number = Decimal(str(value))
    if not number.is_finite() or number != number.to_integral_value() or number < (0 if zero else 1) or number > 1000000:
        raise ValidationError('Enter a whole-number quantity between %s and 1000000.' % (0 if zero else 1))
    return int(number)


def person(user):
    return (user.get_full_name() or user.username) if user else None


def medicine_json(medicine):
    available = (medicine.batches.filter(expiry_date__gt=timezone.localdate()).aggregate(total=Sum('quantity_remaining'))['total'] or 0) if medicine.active else 0
    return {'id': medicine.pk, 'code': medicine.code, 'name': medicine.name, 'strength': medicine.strength,
        'form': medicine.form, 'dispensing_unit': medicine.dispensing_unit, 'active': medicine.active,
        'available': available, 'low_stock_threshold': medicine.low_stock_threshold,
        'low_stock': available <= medicine.low_stock_threshold}


@endpoint(['GET', 'POST'], 'pharmacy')
def medicines(request):
    if request.method == 'POST':
        error = allow(request, PHARMACY)
        if error is not None:
            return error
        data = body(request)
        record = Medicine(branch=request.branch, **{f: text(data, f) for f in ['code', 'name', 'strength', 'form', 'dispensing_unit']},
            low_stock_threshold=quantity(data.get('low_stock_threshold', '0'), zero=True))
        record.full_clean()
        record.save()
        audit(request, 'medicine.create', record)
        return JsonResponse(medicine_json(record), status=201)
    records = scoped(Medicine, request)
    if role_for(request.user) not in PHARMACY or request.GET.get('active') == '1':
        records = records.filter(active=True)
    query = request.GET.get('q', '')[:120]
    if query:
        records = records.filter(Q(name__icontains=query) | Q(code__icontains=query) | Q(strength__icontains=query))
    page = max(1, int(request.GET.get('page', 1)))
    audit(request, 'medicines.read')
    return JsonResponse({'count': records.count(), 'results': [medicine_json(m) for m in records[(page-1)*30:page*30]]})


@endpoint(['GET'], 'pharmacy')
def batches(request):
    error = allow(request, PHARMACY)
    if error is not None:
        return error
    records = scoped(MedicineBatch, request).select_related('medicine')
    if request.GET.get('medicine'):
        records = records.filter(medicine_id=int(request.GET['medicine']))
    if request.GET.get('available') == '1':
        records = records.filter(expiry_date__gt=timezone.localdate(), quantity_remaining__gt=0, medicine__active=True)
    page = max(1, int(request.GET.get('page', 1)))
    audit(request, 'medicine_batches.read')
    return JsonResponse({'count': records.count(), 'results': [{'id': b.pk, 'medicine_id': b.medicine_id,
        'medicine_name': b.medicine.name, 'strength': b.medicine.strength, 'dispensing_unit': b.medicine.dispensing_unit,
        'batch_number': b.batch_number, 'expiry_date': b.expiry_date.isoformat(), 'quantity_remaining': b.quantity_remaining,
        'quantity_received': b.quantity_received, 'expired': b.expiry_date <= timezone.localdate()} for b in records[(page-1)*30:page*30]]})


@endpoint(['POST'], 'pharmacy')
def receive_stock(request):
    error = allow(request, PHARMACY)
    if error is not None:
        return error
    data = body(request)
    medicine = scoped(Medicine, request).select_for_update().filter(pk=data['medicine_id']).first()
    if not medicine or not medicine.active:
        raise ValidationError('Choose an active medicine from your branch.')
    amount = quantity(data.get('quantity'))
    expiry = date.fromisoformat(data['expiry_date'])
    if expiry <= timezone.localdate():
        raise ValidationError('Stock must expire after today. Enter the exact expiry date, not a month alone.')
    batch_number, reference = text(data, 'batch_number'), text(data, 'reference')
    if not batch_number or not reference:
        raise ValidationError('Enter a batch number and a unique receipt reference for this stock entry.')
    if scoped(StockMovement, request).filter(kind='receipt', reference=reference).exists():
        return JsonResponse({'error': 'This receipt reference has already been recorded; stock was not added again.'}, status=409)
    batch = scoped(MedicineBatch, request).select_for_update().filter(medicine=medicine, batch_number=batch_number).first()
    if batch is None:
        batch = MedicineBatch(branch=request.branch, medicine=medicine, batch_number=batch_number, expiry_date=expiry)
    elif batch.expiry_date != expiry:
        raise ValidationError('This batch already has a different expiry date. Verify the label before receiving stock.')
    batch.quantity_received += amount
    batch.quantity_remaining += amount
    batch.full_clean()
    batch.save()
    movement = StockMovement(branch=request.branch, batch=batch, kind='receipt', quantity=amount,
        balance_after=batch.quantity_remaining, reference=reference, note=text(data, 'note'), actor=request.user)
    movement.full_clean()
    movement.save()
    audit(request, 'stock.receive', movement)
    return JsonResponse({'batch_id': batch.pk, 'balance': batch.quantity_remaining}, status=201)


@endpoint(['POST'], 'pharmacy')
def write_off(request, pk):
    error = allow(request, PHARMACY)
    if error is not None:
        return error
    batch = scoped(MedicineBatch, request).select_for_update().filter(pk=pk).first()
    if batch is None:
        return JsonResponse({'error': 'Stock batch not found.'}, status=404)
    data = body(request)
    amount, reason = quantity(data.get('quantity')), text(data, 'reason')
    request_id = uuid.UUID(str(data.get('request_id', '')))
    previous = StockMovement.objects.filter(request_id=request_id).first()
    if previous:
        if previous.branch_id == request.branch.pk and previous.batch_id == batch.pk and previous.kind == 'write_off' and previous.quantity == -amount and previous.note == reason:
            return JsonResponse({'ok': True, 'already_recorded': True})
        return JsonResponse({'error': 'This stock-action reference has already been used.'}, status=409)
    if not reason:
        raise ValidationError('Enter the reason for removing stock.')
    if amount > batch.quantity_remaining:
        raise ValidationError('Cannot remove more than the recorded batch balance.')
    batch.quantity_remaining -= amount
    batch.save(update_fields=['quantity_remaining'])
    movement = StockMovement(branch=request.branch, batch=batch, kind='write_off', quantity=-amount,
        balance_after=batch.quantity_remaining, note=reason, actor=request.user, request_id=request_id)
    movement.full_clean()
    movement.save()
    audit(request, 'stock.write_off', movement)
    return JsonResponse({'ok': True})


def prescription_json(record, detail=False):
    dispensed = record.dispenses.aggregate(total=Sum('quantity'))['total'] or 0
    result = {'id': record.pk, 'patient_name': record.patient.full_name, 'hospital_number': record.patient.hospital_number,
        'consultation_id': record.consultation_id, 'medicine_id': record.medicine_id, 'medicine_name': record.medicine_name,
        'strength': record.strength, 'form': record.form, 'dispensing_unit': record.dispensing_unit,
        'quantity': record.quantity, 'dispensed_quantity': dispensed, 'unfilled_quantity': record.quantity-dispensed,
        'status': record.status, 'prescribed_by': person(record.prescribed_by), 'created_at': record.created_at.isoformat()}
    if detail:
        result.update({f: getattr(record, f) for f in ['dose', 'route', 'frequency', 'duration', 'instructions', 'allergy_status', 'allergies', 'cancellation_reason']})
        result['cancelled_by'] = person(record.cancelled_by)
        result['cancelled_at'] = record.cancelled_at.isoformat() if record.cancelled_at else None
        result['dispenses'] = [{'id': d.pk, 'quantity': d.quantity, 'batch_number': d.batch.batch_number,
            'expiry_date': d.batch.expiry_date.isoformat(), 'pharmacist': person(d.pharmacist), 'created_at': d.created_at.isoformat()}
            for d in record.dispenses.select_related('batch', 'pharmacist').all()]
    return result


@endpoint(['GET', 'POST'], 'pharmacy')
def prescriptions(request):
    if request.method == 'POST':
        error = allow(request, PRESCRIBERS)
        if error is not None:
            return error
        data = body(request)
        if data.get('review_confirmed') is not True:
            raise ValidationError('Review and confirm the prescription before signing.')
        consultation = related(Consultation, data['consultation_id'], request)
        medicine = related(Medicine, data['medicine_id'], request)
        if not medicine.active:
            raise ValidationError('Choose an active medicine.')
        record = Prescription(branch=request.branch, patient=consultation.patient, consultation=consultation,
            medicine=medicine, medicine_name=medicine.name, strength=medicine.strength, form=medicine.form,
            dispensing_unit=medicine.dispensing_unit, quantity=quantity(data.get('quantity')),
            prescribed_by=request.user, allergy_status=consultation.allergy_status, allergies=consultation.allergies,
            **{f: text(data, f) for f in ['dose', 'route', 'frequency', 'duration', 'instructions']})
        record.full_clean()
        record.save()
        audit(request, 'prescription.sign', record)
        return JsonResponse({'id': record.pk}, status=201)
    records = scoped(Prescription, request).select_related('patient', 'prescribed_by')
    query = request.GET.get('q', '')[:120]
    if query:
        records = records.filter(Q(patient__first_name__icontains=query) | Q(patient__last_name__icontains=query)
            | Q(patient__hospital_number__icontains=query) | Q(medicine_name__icontains=query))
    if request.GET.get('status'):
        if request.GET['status'] not in {'active', 'completed', 'cancelled'}:
            raise ValidationError('Choose a valid prescription status.')
        records = records.filter(status=request.GET['status'])
    page = max(1, int(request.GET.get('page', 1)))
    audit(request, 'prescriptions.read')
    return JsonResponse({'count': records.count(), 'results': [prescription_json(r) for r in records[(page-1)*20:page*20]]})


@endpoint(['GET'], 'pharmacy')
def prescription_detail(request, pk):
    record = scoped(Prescription, request).select_related('patient', 'prescribed_by', 'cancelled_by').filter(pk=pk).first()
    if record is None:
        return JsonResponse({'error': 'Prescription not found.'}, status=404)
    audit(request, 'prescription.read', record)
    return JsonResponse(prescription_json(record, detail=True))


@endpoint(['POST'], 'pharmacy')
def dispense(request, pk):
    error = allow(request, PHARMACY)
    if error is not None:
        return error
    record = scoped(Prescription, request).select_for_update().filter(pk=pk).first()
    if record is None:
        return JsonResponse({'error': 'Prescription not found.'}, status=404)
    data = body(request)
    if data.get('review_confirmed') is not True:
        raise ValidationError('Confirm patient, allergies, prescription and batch checks before dispensing.')
    amount, request_id = quantity(data.get('quantity')), uuid.UUID(str(data.get('request_id', '')))
    previous = Dispense.objects.filter(request_id=request_id).first()
    if previous:
        if previous.prescription_id == record.pk and str(previous.batch_id) == str(data.get('batch_id')) and previous.quantity == amount:
            return JsonResponse({'id': previous.pk, 'already_recorded': True})
        return JsonResponse({'error': 'This dispensing reference was already used for another entry.'}, status=409)
    if record.status != 'active':
        return JsonResponse({'error': 'Only an active prescription can be dispensed.'}, status=409)
    batch = scoped(MedicineBatch, request).select_for_update().filter(pk=data['batch_id'], medicine_id=record.medicine_id).first()
    if batch is None:
        raise ValidationError('Select a batch for the prescribed medicine from your branch.')
    if batch.expiry_date <= timezone.localdate() or not batch.medicine.active:
        raise ValidationError('Do not dispense expired, expiring-today or inactive medicine stock.')
    filled = record.dispenses.aggregate(total=Sum('quantity'))['total'] or 0
    if amount > record.quantity-filled or amount > batch.quantity_remaining:
        raise ValidationError('Quantity exceeds the unfilled prescription or available batch balance.')
    entry = Dispense(prescription=record, batch=batch, quantity=amount, pharmacist=request.user, request_id=request_id)
    entry.full_clean()
    entry.save()
    batch.quantity_remaining -= amount
    batch.save(update_fields=['quantity_remaining'])
    if filled + amount == record.quantity:
        record.status = 'completed'
        record.save(update_fields=['status'])
    movement = StockMovement(branch=request.branch, batch=batch, prescription=record, kind='dispense',
        quantity=-amount, balance_after=batch.quantity_remaining, actor=request.user)
    movement.full_clean()
    movement.save()
    audit(request, 'prescription.dispense', entry)
    return JsonResponse({'id': entry.pk}, status=201)


@endpoint(['POST'], 'pharmacy')
def cancel_prescription(request, pk):
    error = allow(request, PRESCRIBERS)
    if error is not None:
        return error
    record = scoped(Prescription, request).select_for_update().filter(pk=pk).first()
    if record is None:
        return JsonResponse({'error': 'Prescription not found.'}, status=404)
    if record.status != 'active':
        return JsonResponse({'error': 'Only an active prescription can be cancelled.'}, status=409)
    reason = text(body(request), 'reason')
    if not reason:
        raise ValidationError('Enter the reason for cancelling the unfilled prescription quantity.')
    record.cancellation_reason, record.cancelled_by, record.cancelled_at = reason, request.user, timezone.now()
    record.status = 'cancelled'
    record.full_clean()
    record.save(update_fields=['cancellation_reason', 'cancelled_by', 'cancelled_at', 'status'])
    audit(request, 'prescription.cancel', record)
    return JsonResponse({'ok': True})


@endpoint(['GET'], 'pharmacy')
def movements(request):
    error = allow(request, PHARMACY)
    if error is not None:
        return error
    records = scoped(StockMovement, request).select_related('batch__medicine', 'actor')
    if request.GET.get('medicine'):
        records = records.filter(batch__medicine_id=int(request.GET['medicine']))
    page = max(1, int(request.GET.get('page', 1)))
    audit(request, 'stock_movements.read')
    return JsonResponse({'count': records.count(), 'results': [{'id': m.pk, 'kind': m.kind, 'quantity': m.quantity,
        'balance_after': m.balance_after, 'medicine_name': m.batch.medicine.name, 'batch_number': m.batch.batch_number,
        'reference': m.reference, 'note': m.note, 'actor': person(m.actor), 'prescription_id': m.prescription_id,
        'created_at': m.created_at.isoformat()} for m in records[(page-1)*30:page*30]]})
