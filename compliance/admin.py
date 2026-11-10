from django.contrib import admin

from .models import Audit, Certificate, Country, Organisation, Profile, Region, Supplier

admin.site.register([Region, Country, Organisation, Profile, Supplier, Certificate, Audit])
