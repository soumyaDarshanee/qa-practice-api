from datetime import date, timedelta

from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.db.models import Avg, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import EXPIRING_WINDOW_DAYS, AUDIT_PASS_SCORE, Audit, Certificate, Country, Organisation, Profile, Region, Supplier
from .permissions import IsOrgMember
from .serializers import (
    AuditSerializer,
    AuthResponseSerializer,
    CertificateSerializer,
    CountrySerializer,
    DashboardSerializer,
    LoginSerializer,
    MeSerializer,
    RegionSerializer,
    RegisterSerializer,
    SupplierSerializer,
    me_payload,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Health + auth
# ---------------------------------------------------------------------------
class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses={200: OpenApiTypes.OBJECT}, tags=["health"])
    def get(self, request):
        return Response({"status": "ok"})


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=LoginSerializer, responses={200: AuthResponseSerializer}, tags=["auth"])
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            username=serializer.validated_data["email"].lower(),
            password=serializer.validated_data["password"],
        )
        if user is None or not hasattr(user, "profile"):
            return Response({"detail": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": me_payload(user)})


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=RegisterSerializer, responses={201: AuthResponseSerializer}, tags=["auth"])
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            org = Organisation.objects.create(name=data["organisation_name"])
            user = User.objects.create_user(username=data["email"], email=data["email"], password=data["password"])
            Profile.objects.create(user=user, organisation=org, role=Profile.Role.ADMIN)
        token = Token.objects.create(user=user)
        return Response({"token": token.key, "user": me_payload(user)}, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None}, tags=["auth"])
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsOrgMember]

    @extend_schema(responses={200: MeSerializer}, tags=["auth"])
    def get(self, request):
        return Response(me_payload(request.user))


# ---------------------------------------------------------------------------
# Reference data (read-only)
# ---------------------------------------------------------------------------
@extend_schema_view(list=extend_schema(tags=["reference data"]), retrieve=extend_schema(tags=["reference data"]))
class RegionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer
    pagination_class = None


@extend_schema_view(
    list=extend_schema(
        tags=["reference data"],
        parameters=[OpenApiParameter("region", str, description="Filter by region code, e.g. EU")],
    ),
    retrieve=extend_schema(tags=["reference data"]),
)
class CountryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CountrySerializer
    pagination_class = None

    def get_queryset(self):
        qs = Country.objects.select_related("region")
        region = self.request.query_params.get("region")
        if region:
            qs = qs.filter(region__code__iexact=region)
        return qs


# ---------------------------------------------------------------------------
# Tenant-scoped domain endpoints
# ---------------------------------------------------------------------------
class OrgScopedMixin:
    permission_classes = [IsOrgMember]

    @property
    def organisation(self):
        return self.request.user.profile.organisation


SUPPLIER_ORDERING = {"name", "-name", "created_at", "-created_at", "risk_level", "-risk_level", "status", "-status"}


@extend_schema_view(
    list=extend_schema(
        tags=["suppliers"],
        parameters=[
            OpenApiParameter("search", str, description="Search in name, email and contact name"),
            OpenApiParameter("status", str, enum=Supplier.Status.values),
            OpenApiParameter("risk_level", str, enum=Supplier.RiskLevel.values),
            OpenApiParameter("country", str, description="ISO country code, e.g. NL"),
            OpenApiParameter("ordering", str, enum=sorted(SUPPLIER_ORDERING)),
        ],
    ),
    create=extend_schema(tags=["suppliers"]),
    retrieve=extend_schema(tags=["suppliers"]),
    update=extend_schema(tags=["suppliers"]),
    partial_update=extend_schema(tags=["suppliers"]),
    destroy=extend_schema(tags=["suppliers"]),
)
class SupplierViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = SupplierSerializer

    def get_queryset(self):
        qs = Supplier.objects.filter(organisation=self.organisation).select_related("country")
        params = self.request.query_params
        if search := params.get("search"):
            qs = qs.filter(Q(name__icontains=search) | Q(email__icontains=search) | Q(contact_name__icontains=search))
        if value := params.get("status"):
            qs = qs.filter(status=value)
        if value := params.get("risk_level"):
            qs = qs.filter(risk_level=value)
        if value := params.get("country"):
            qs = qs.filter(country__iso_code__iexact=value)
        ordering = params.get("ordering")
        if ordering in SUPPLIER_ORDERING:
            qs = qs.order_by(ordering, "id")
        return qs

    def perform_create(self, serializer):
        serializer.save(organisation=self.organisation)


def certificate_status_filter(qs, value):
    today = date.today()
    window = today + timedelta(days=EXPIRING_WINDOW_DAYS)
    if value == "expired":
        return qs.filter(expiry_date__lt=today)
    if value == "expiring":
        return qs.filter(expiry_date__gte=today, expiry_date__lte=window)
    if value == "valid":
        return qs.filter(expiry_date__gt=window)
    return qs


@extend_schema_view(
    list=extend_schema(
        tags=["certificates"],
        parameters=[
            OpenApiParameter("supplier", int),
            OpenApiParameter("status", str, enum=["valid", "expiring", "expired"]),
            OpenApiParameter("certificate_type", str, enum=Certificate.CertificateType.values),
        ],
    ),
    create=extend_schema(tags=["certificates"]),
    retrieve=extend_schema(tags=["certificates"]),
    update=extend_schema(tags=["certificates"]),
    partial_update=extend_schema(tags=["certificates"]),
    destroy=extend_schema(tags=["certificates"]),
)
class CertificateViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = CertificateSerializer

    def get_queryset(self):
        qs = Certificate.objects.filter(supplier__organisation=self.organisation).select_related("supplier")
        params = self.request.query_params
        if value := params.get("supplier"):
            qs = qs.filter(supplier_id=value) if value.isdigit() else qs.none()
        if value := params.get("certificate_type"):
            qs = qs.filter(certificate_type=value)
        if value := params.get("status"):
            qs = certificate_status_filter(qs, value)
        return qs


@extend_schema_view(
    list=extend_schema(
        tags=["audits"],
        parameters=[
            OpenApiParameter("supplier", int),
            OpenApiParameter("result", str, enum=["pass", "fail"]),
        ],
    ),
    create=extend_schema(tags=["audits"]),
    retrieve=extend_schema(tags=["audits"]),
    update=extend_schema(tags=["audits"]),
    partial_update=extend_schema(tags=["audits"]),
    destroy=extend_schema(tags=["audits"]),
)
class AuditViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = AuditSerializer

    def get_queryset(self):
        qs = Audit.objects.filter(supplier__organisation=self.organisation).select_related("supplier")
        params = self.request.query_params
        if value := params.get("supplier"):
            qs = qs.filter(supplier_id=value) if value.isdigit() else qs.none()
        result = params.get("result")
        if result == "pass":
            qs = qs.filter(score__gte=AUDIT_PASS_SCORE)
        elif result == "fail":
            qs = qs.filter(score__lt=AUDIT_PASS_SCORE)
        return qs


class DashboardView(OrgScopedMixin, APIView):
    @extend_schema(responses={200: DashboardSerializer}, tags=["dashboard"])
    def get(self, request):
        suppliers = Supplier.objects.filter(organisation=self.organisation)
        certificates = Certificate.objects.filter(supplier__organisation=self.organisation)
        recent_audits = Audit.objects.filter(
            supplier__organisation=self.organisation,
            audit_date__gte=date.today() - timedelta(days=90),
        )
        avg = recent_audits.aggregate(avg=Avg("score"))["avg"]
        return Response(
            {
                "suppliers": {
                    "total": suppliers.count(),
                    **{s: suppliers.filter(status=s).count() for s in Supplier.Status.values},
                },
                "certificates": {
                    "total": certificates.count(),
                    **{s: certificate_status_filter(certificates, s).count() for s in ("valid", "expiring", "expired")},
                },
                "audits": {
                    "last_90_days": recent_audits.count(),
                    "average_score": round(avg, 1) if avg is not None else None,
                },
            }
        )
