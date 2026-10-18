from django.urls import path
from . import views, lab_views

urlpatterns = [
    path('laboratory/', lab_views.orders),
    path('laboratory/tests/', lab_views.catalogue),
    path('laboratory/<int:pk>/', lab_views.detail),
    path('laboratory/<int:pk>/collect/', lab_views.collect),
    path('laboratory/<int:pk>/report/', lab_views.report),
    path('laboratory/<int:pk>/cancel/', lab_views.cancel),
    path('laboratory/<int:pk>/addenda/', lab_views.addendum),
    path('consultations/', views.consultations),
    path('consultations/<int:pk>/', views.consultation_detail),
    path('consultations/<int:pk>/addenda/', views.consultation_addendum),
    path('session/', views.session), path('login/', views.login), path('logout/', views.logout),
    path('dashboard/', views.dashboard), path('departments/', views.departments),
    path('patients/', views.patients), path('patient-options/', views.patient_options),
    path('appointments/', views.appointments), path('appointments/<int:pk>/', views.appointment_update),
    path('admissions/', views.admissions), path('admissions/<int:pk>/', views.discharge),
    path('invoices/', views.invoices), path('invoices/<int:pk>/', views.invoice_paid),
]
