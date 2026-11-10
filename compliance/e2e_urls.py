"""Test-only endpoints. Mounted at /api/e2e/ only when E2E_MODE=true."""

import uuid

from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Country, Organisation, Profile, Region
from .seed import BASELINE_USERS, DEFAULT_PASSWORD, create_user, reset_database
from .serializers import AuthResponseSerializer, me_payload

EXPECTED_MIN_COUNTRIES = 20
EXPECTED_REGIONS = {"EU", "AF", "SA", "NA", "AS", "OC"}


class ResetSerializer(serializers.Serializer):
    sample_data = serializers.BooleanField(default=False)


class UserFactorySerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Profile.Role.choices, default=Profile.Role.ADMIN)
    organisation_id = serializers.IntegerField(
        required=False, help_text="Join an existing organisation. Omit to create a new one."
    )
    organisation_name = serializers.CharField(required=False, max_length=200)


class SeedStatusSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    regions = serializers.IntegerField()
    countries = serializers.IntegerField()
    missing_regions = serializers.ListField(child=serializers.CharField())
    missing_users = serializers.ListField(child=serializers.CharField())


class E2EBase(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


class ResetView(E2EBase):
    @extend_schema(request=ResetSerializer, responses={200: None}, tags=["e2e"])
    def post(self, request):
        s = ResetSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        reset_database(with_sample_data=s.validated_data["sample_data"])
        return Response({"detail": "Database reset to baseline."})


class SeedStatusView(E2EBase):
    """Fail-fast check for a setup project: is the baseline seed loaded?"""

    @extend_schema(responses={200: SeedStatusSerializer, 503: SeedStatusSerializer}, tags=["e2e"])
    def get(self, request):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        region_codes = set(Region.objects.values_list("code", flat=True))
        countries = Country.objects.count()
        missing_users = [u["email"] for u in BASELINE_USERS if not User.objects.filter(username=u["email"]).exists()]
        missing_regions = sorted(EXPECTED_REGIONS - region_codes)
        ok = not missing_regions and not missing_users and countries >= EXPECTED_MIN_COUNTRIES
        body = {
            "ok": ok,
            "regions": len(region_codes),
            "countries": countries,
            "missing_regions": missing_regions,
            "missing_users": missing_users,
        }
        return Response(body, status=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE)


class UserFactoryView(E2EBase):
    """Create a fresh, unique user (and token). Handy for account pools."""

    @extend_schema(request=UserFactorySerializer, responses={201: AuthResponseSerializer}, tags=["e2e"])
    def post(self, request):
        s = UserFactorySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        if "organisation_id" in data:
            org = Organisation.objects.filter(pk=data["organisation_id"]).first()
            if org is None:
                return Response({"organisation_id": ["Organisation not found."]}, status=status.HTTP_400_BAD_REQUEST)
        else:
            org = Organisation.objects.create(name=data.get("organisation_name") or f"E2E Org {uuid.uuid4().hex[:8]}")
        email = f"e2e-{uuid.uuid4().hex[:12]}@qa.test"
        user = create_user(email, data["role"], org)
        token = Token.objects.create(user=user)
        return Response(
            {"token": token.key, "password": DEFAULT_PASSWORD, "user": me_payload(user)},
            status=status.HTTP_201_CREATED,
        )


urlpatterns = [
    path("reset/", ResetView.as_view(), name="e2e-reset"),
    path("seed-status/", SeedStatusView.as_view(), name="e2e-seed-status"),
    path("users/", UserFactoryView.as_view(), name="e2e-users"),
]
