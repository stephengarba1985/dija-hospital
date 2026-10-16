from django.contrib import admin
from .models import Branch, Department, StaffProfile, Patient, Appointment, Admission, Invoice, AuditEvent, Consultation, ConsultationAddendum

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['hospital_number', 'first_name', 'last_name', 'branch']
    search_fields = ['hospital_number', 'first_name', 'last_name']
    readonly_fields = ['hospital_number', 'created_at']

@admin.register(StaffProfile)
class StaffAdmin(admin.ModelAdmin):
    list_display = ['user', 'branch', 'role']
    list_filter = ['branch', 'role']

@admin.register(AuditEvent)
class AuditAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'actor', 'branch', 'action', 'object_type', 'object_id']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

# The administration console is for trusted superusers only. Branch staff use the scoped API.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser
admin.site.register([Branch, Department, Appointment, Admission, Invoice])


@admin.register(Consultation, ConsultationAddendum)
class SignedClinicalRecordAdmin(admin.ModelAdmin):
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
