from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Audit, Certificate, Country, Organisation, Profile, Region, Supplier

User = get_user_model()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    organisation_name = serializers.CharField(max_length=200)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value


class OrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = ["id", "name"]


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Profile.Role.choices)
    organisation = OrganisationSerializer()


class AuthResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = MeSerializer()


def me_payload(user) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.profile.role,
        "organisation": {"id": user.profile.organisation.id, "name": user.profile.organisation.name},
    }


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ["id", "code", "name"]


class CountrySerializer(serializers.ModelSerializer):
    region = RegionSerializer(read_only=True)

    class Meta:
        model = Country
        fields = ["id", "iso_code", "name", "region"]


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------
class SupplierSerializer(serializers.ModelSerializer):
    country = serializers.SlugRelatedField(slug_field="iso_code", queryset=Country.objects.all())
    country_name = serializers.CharField(source="country.name", read_only=True)
    certificate_count = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "email",
            "contact_name",
            "country",
            "country_name",
            "status",
            "risk_level",
            "certificate_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        # Uniqueness per organisation is checked in validate_name, because the
        # organisation is not a writable field.
        validators = []

    def get_certificate_count(self, obj) -> int:
        return obj.certificates.count()

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        org = self.context["request"].user.profile.organisation
        qs = Supplier.objects.filter(organisation=org, name__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A supplier with this name already exists.")
        return value


class SupplierRefField(serializers.PrimaryKeyRelatedField):
    """Only lets you pick suppliers from your own organisation."""

    def get_queryset(self):
        request = self.context.get("request")
        if request is None or not hasattr(request.user, "profile"):
            return Supplier.objects.none()
        return Supplier.objects.filter(organisation=request.user.profile.organisation)


class CertificateSerializer(serializers.ModelSerializer):
    supplier = SupplierRefField()
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    certificate_type_display = serializers.CharField(source="get_certificate_type_display", read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Certificate
        fields = [
            "id",
            "supplier",
            "supplier_name",
            "certificate_type",
            "certificate_type_display",
            "certificate_number",
            "issue_date",
            "expiry_date",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        validators = []

    def validate(self, attrs):
        issue = attrs.get("issue_date", getattr(self.instance, "issue_date", None))
        expiry = attrs.get("expiry_date", getattr(self.instance, "expiry_date", None))
        if issue and expiry and expiry <= issue:
            raise serializers.ValidationError({"expiry_date": "Expiry date must be after the issue date."})

        supplier = attrs.get("supplier", getattr(self.instance, "supplier", None))
        number = attrs.get("certificate_number", getattr(self.instance, "certificate_number", None))
        if supplier and number:
            qs = Certificate.objects.filter(supplier=supplier, certificate_number=number)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"certificate_number": "This supplier already has a certificate with this number."}
                )
        return attrs


class AuditSerializer(serializers.ModelSerializer):
    supplier = SupplierRefField()
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    score = serializers.IntegerField(min_value=0, max_value=100)
    result = serializers.CharField(read_only=True)

    class Meta:
        model = Audit
        fields = ["id", "supplier", "supplier_name", "audit_date", "auditor", "score", "result", "notes", "created_at"]
        read_only_fields = ["id", "created_at"]


class DashboardSerializer(serializers.Serializer):
    suppliers = serializers.DictField(child=serializers.IntegerField())
    certificates = serializers.DictField(child=serializers.IntegerField())
    audits = serializers.DictField()
