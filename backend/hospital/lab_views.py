from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone

from .models import Consultation, LabTest, LabOrder, LabReport, LabReportAddendum
from .views import endpoint, scoped, related, body, audit, role_for

ORDER_ROLES = {'administrator', 'doctor'}
LAB_ROLES = {'administrator', 'laboratory'}


def name(user):
    return (user.get_full_name() or user.username) if user else None


def text(data, key):
    value = data.get(key, '')
    if not isinstance(value, str):
        raise ValidationError('Text fields must contain text.')
    return value.strip()


def denied(request, roles):
    if role_for(request.user) not in roles:
        return JsonResponse({'error': 'Your staff role cannot perform this laboratory action.'}, status=403)


def order_query(request):
    return scoped(LabOrder, request).select_related('patient', 'requested_by', 'collected_by', 'cancelled_by', 'report__signed_by')


def order_json(order, detail=False):
    result = {'id': order.pk, 'patient_name': order.patient.full_name, 'hospital_number': order.patient.hospital_number,
        'consultation_id': order.consultation_id, 'test_name': order.test_name, 'specimen_type': order.specimen_type,
        'status': order.status, 'priority': order.priority, 'created_at': order.created_at.isoformat(),
        'requested_by': name(order.requested_by)}
    if detail:
        result.update(indication=order.indication, specimen_id=order.specimen_id,
            collected_at=order.collected_at.isoformat() if order.collected_at else None,
            collected_by=name(order.collected_by), cancellation_reason=order.cancellation_reason,
            cancelled_at=order.cancelled_at.isoformat() if order.cancelled_at else None,
            cancelled_by=name(order.cancelled_by), report=None)
        if hasattr(order, 'report'):
            report = order.report
            result['report'] = {'result_text': report.result_text, 'reference_info': report.reference_info,
                'comments': report.comments, 'signed_by': name(report.signed_by), 'signed_at': report.signed_at.isoformat(),
                'addenda': [{'id': a.pk, 'note': a.note, 'signed_by': name(a.signed_by), 'signed_at': a.signed_at.isoformat()}
                    for a in report.addenda.select_related('signed_by').all()]}
    return result


@endpoint(['GET'], 'laboratory')
def catalogue(request):
    return JsonResponse({'results': list(scoped(LabTest, request).filter(active=True).values('id', 'code', 'name', 'specimen_type'))})


@endpoint(['GET', 'POST'], 'laboratory')
def orders(request):
    if request.method == 'POST':
        error = denied(request, ORDER_ROLES)
        if error is not None:
            return error
        data = body(request)
        consultation = related(Consultation, data['consultation_id'], request)
        test = related(LabTest, data['lab_test_id'], request)
        if not test.active:
            raise ValidationError('Choose an active laboratory test.')
        order = LabOrder(branch=request.branch, patient=consultation.patient, consultation=consultation,
            test=test, test_name=test.name, specimen_type=test.specimen_type, requested_by=request.user,
            indication=text(data, 'indication'), priority=text(data, 'priority') or 'routine')
        order.full_clean()
        order.save()
        audit(request, 'lab_order.create', order)
        return JsonResponse({'id': order.pk}, status=201)
    records = order_query(request)
    query = request.GET.get('q', '').strip()[:120]
    if query:
        records = records.filter(Q(patient__first_name__icontains=query) | Q(patient__last_name__icontains=query)
            | Q(patient__hospital_number__icontains=query) | Q(test_name__icontains=query))
    status = request.GET.get('status')
    if status:
        if status not in LabOrder.Status.values:
            raise ValidationError('Choose a valid laboratory status.')
        records = records.filter(status=status)
    if request.GET.get('consultation'):
        records = records.filter(consultation_id=int(request.GET['consultation']))
    page = max(1, int(request.GET.get('page', 1)))
    audit(request, 'lab_orders.read')
    return JsonResponse({'count': records.count(), 'results': [order_json(o) for o in records[(page-1)*20:page*20]]})


@endpoint(['GET'], 'laboratory')
def detail(request, pk):
    order = order_query(request).filter(pk=pk).first()
    if order is None:
        return JsonResponse({'error': 'Laboratory request not found.'}, status=404)
    audit(request, 'lab_order.read', order)
    return JsonResponse(order_json(order, detail=True))


def locked_order(request, pk):
    # Lock only the order row: nullable report joins must not participate in FOR UPDATE.
    return scoped(LabOrder, request).select_for_update().filter(pk=pk).first()


def missing():
    return JsonResponse({'error': 'Laboratory request not found.'}, status=404)


@endpoint(['POST'], 'laboratory')
def collect(request, pk):
    error = denied(request, LAB_ROLES)
    if error is not None:
        return error
    order = locked_order(request, pk)
    if order is None:
        return missing()
    if order.status != 'requested':
        return JsonResponse({'error': 'Only requested tests can have a specimen collected.'}, status=409)
    data = body(request)
    if data.get('identity_verified') is not True:
        raise ValidationError('Confirm the patient and specimen identity before collection.')
    order.specimen_id = text(data, 'specimen_id')
    if not order.specimen_id:
        raise ValidationError('Enter the specimen label or identifier.')
    order.status, order.collected_at, order.collected_by = 'collected', timezone.now(), request.user
    order.full_clean()
    order.save(update_fields=['specimen_id', 'status', 'collected_at', 'collected_by'])
    audit(request, 'lab_order.collect', order)
    return JsonResponse({'ok': True})


@endpoint(['POST'], 'laboratory')
def report(request, pk):
    error = denied(request, LAB_ROLES)
    if error is not None:
        return error
    order = locked_order(request, pk)
    if order is None:
        return missing()
    if order.status != 'collected':
        return JsonResponse({'error': 'Results can only be signed after specimen collection and before reporting.'}, status=409)
    data = body(request)
    if data.get('review_confirmed') is not True:
        raise ValidationError('Review and confirm the report before signing.')
    record = LabReport(order=order, result_text=text(data, 'result_text'), reference_info=text(data, 'reference_info'),
        comments=text(data, 'comments'), signed_by=request.user)
    record.full_clean()
    record.save()
    order.status = 'reported'
    order.save(update_fields=['status'])
    audit(request, 'lab_report.sign', record)
    return JsonResponse({'id': record.pk}, status=201)


@endpoint(['POST'], 'laboratory')
def cancel(request, pk):
    error = denied(request, ORDER_ROLES)
    if error is not None:
        return error
    order = locked_order(request, pk)
    if order is None:
        return missing()
    if order.status != 'requested':
        return JsonResponse({'error': 'Only requests without a collected specimen can be cancelled.'}, status=409)
    order.cancellation_reason = text(body(request), 'cancellation_reason')
    if not order.cancellation_reason:
        raise ValidationError('Enter the reason for cancellation.')
    order.status, order.cancelled_at, order.cancelled_by = 'cancelled', timezone.now(), request.user
    order.full_clean()
    order.save(update_fields=['status', 'cancelled_at', 'cancelled_by', 'cancellation_reason'])
    audit(request, 'lab_order.cancel', order)
    return JsonResponse({'ok': True})


@endpoint(['POST'], 'laboratory')
def addendum(request, pk):
    error = denied(request, LAB_ROLES)
    if error is not None:
        return error
    order = locked_order(request, pk)
    if order is None:
        return missing()
    if order.status != 'reported':
        return JsonResponse({'error': 'Only a signed laboratory report can receive an addendum.'}, status=409)
    data = body(request)
    if data.get('review_confirmed') is not True:
        raise ValidationError('Confirm the addendum is ready to sign.')
    record = LabReportAddendum(report=order.report, note=text(data, 'note'), signed_by=request.user)
    record.full_clean()
    record.save()
    audit(request, 'lab_report.addendum', record)
    return JsonResponse({'id': record.pk}, status=201)
