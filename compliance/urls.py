from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("regions", views.RegionViewSet, basename="region")
router.register("countries", views.CountryViewSet, basename="country")
router.register("suppliers", views.SupplierViewSet, basename="supplier")
router.register("certificates", views.CertificateViewSet, basename="certificate")
router.register("audits", views.AuditViewSet, basename="audit")

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    *router.urls,
]
