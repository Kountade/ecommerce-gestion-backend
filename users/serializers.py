# serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import CustomUser

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class RegisterSerializer(serializers.ModelSerializer):
    """
    Inscription publique : le rôle 'client' est forcé.
    Impossible de créer un admin ou vendeur via cet endpoint.
    """
    class Meta:
        model = User
        fields = ('id', 'email', 'password', 'first_name', 'last_name', 'phone_number')
        extra_kwargs = {
            'password': {'write_only': True, 'min_length': 8},
        }

    def create(self, validated_data):
        # Sécurité : rôle client forcé à l'inscription publique
        validated_data['role'] = 'client'
        return User.objects.create_client(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    """Sérialiseur de lecture pour la liste des utilisateurs."""
    class Meta:
        model = User
        fields = (
            'id', 'email', 'username', 'role',
            'first_name', 'last_name',
            'phone_number', 'is_active', 'profile_picture', 'created_at'
        )
        read_only_fields = fields


class UserDetailSerializer(serializers.ModelSerializer):
    """Sérialiseur de lecture détaillée."""
    class Meta:
        model = User
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'last_login', 'is_superuser')


class UserWriteSerializer(serializers.ModelSerializer):
    """
    Sérialiseur pour la création/modification d'utilisateurs par un admin.
    """
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = [
            'email', 'password', 'username', 'role',
            'first_name', 'last_name', 'phone_number',
            'address', 'birthday', 'is_active',
            'is_staff', 'is_superuser',
        ]
        extra_kwargs = {
            'role': {'required': False},
            'is_staff': {'required': False},
            'is_superuser': {'required': False},
        }

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        role = validated_data.get('role', 'vendeur')

        # Ajuster is_staff/is_superuser en fonction du rôle
        if role == 'admin':
            validated_data.setdefault('is_staff', True)
            validated_data.setdefault('is_superuser', True)
        else:
            validated_data.setdefault('is_staff', False)
            validated_data.setdefault('is_superuser', False)

        user = User.objects.create_user(password=password, **validated_data)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        new_role = validated_data.get('role', instance.role)

        user = super().update(instance, validated_data)

        # Synchroniser is_staff / is_superuser avec le rôle
        if new_role == 'admin':
            user.is_staff = True
            user.is_superuser = True
        else:
            user.is_staff = False
            user.is_superuser = False

        if password:
            user.set_password(password)

        user.save()
        return user


class ClientProfileSerializer(serializers.ModelSerializer):
    """
    Sérialiseur dédié aux clients pour qu'ils puissent mettre à jour
    uniquement leurs infos personnelles (pas le rôle ni is_staff).
    """
    class Meta:
        model = User
        fields = (
            'id', 'email', 'username',
            'first_name', 'last_name',
            'phone_number', 'address', 'birthday', 'profile_picture',
        )
        read_only_fields = ('id', 'email')