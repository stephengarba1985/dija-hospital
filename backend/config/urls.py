from django.contrib import admin
from django.urls import path, include

urlpatterns = [path('admin/', admin.site.urls), path('api/', include('hospital.urls'))]
admin.site.site_header = 'Dija Hospital · Administration'
admin.site.site_title = 'Hospital administration'
