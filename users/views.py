from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model, authenticate
from knox.models import AuthToken

from .serializers import (
    LoginSerializer, RegisterSerializer,
    UserSerializer, UserDetailSerializer, UserWriteSerializer,
    ClientProfileSerializer,
)
from .permissions import IsAdmin

User = get_user_model()


# ============================================================
# Authentification
# ============================================================

class LoginViewset(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            user = authenticate(request, email=email, password=password)

            if user is not None and user.is_active:
                _, token = AuthToken.objects.create(user)
                return Response({
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "role": user.role,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                    },
                    "token": token
                })
            return Response(
                {"error": "Identifiants invalides ou compte désactivé"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RegisterViewset(viewsets.ViewSet):
    """
    Inscription publique — crée uniquement des comptes CLIENT.
    Les vendeurs/admins sont créés par un administrateur via UserViewset.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            _, token = AuthToken.objects.create(user)
            return Response({
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                },
                "token": token
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================================
# Gestion des utilisateurs (admin)
# ============================================================

class UserViewset(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return UserWriteSerializer
        return UserSerializer

    def is_admin(self, user):
        return user.role == 'admin'

    # ----- Liste -----
    def list(self, request):
        if self.is_admin(request.user):
            queryset = User.objects.all().order_by('-created_at')
        else:
            # Les non-admins ne voient que leur propre profil
            queryset = User.objects.filter(id=request.user.id)

        serializer = UserSerializer(queryset, many=True)
        return Response(serializer.data)

    # ----- Création (admin uniquement) -----
    def create(self, request):
        if not self.is_admin(request.user):
            return Response(
                {"error": "Seul un administrateur peut créer des utilisateurs"},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = UserWriteSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ----- Détail -----
    def retrieve(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "Utilisateur non trouvé"}, status=status.HTTP_404_NOT_FOUND)

        if self.is_admin(request.user) or request.user.id == user.id:
            serializer = UserDetailSerializer(user)
            return Response(serializer.data)

        return Response({"error": "Permission refusée"}, status=status.HTTP_403_FORBIDDEN)

    # ----- Mise à jour complète -----
    def update(self, request, pk=None):
        return self._update(request, pk, partial=False)

    # ----- Mise à jour partielle -----
    def partial_update(self, request, pk=None):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, partial):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "Utilisateur non trouvé"}, status=status.HTTP_404_NOT_FOUND)

        # Un client/vendeur ne peut modifier que son profil, et pas son rôle
        if not self.is_admin(request.user):
            if request.user.id != user.id:
                return Response({"error": "Permission refusée"}, status=status.HTTP_403_FORBIDDEN)

            # Empêcher l'élévation de privilèges
            if 'role' in request.data and request.data['role'] != user.role:
                return Response(
                    {"error": "Vous ne pouvez pas modifier votre rôle"},
                    status=status.HTTP_403_FORBIDDEN
                )
            if 'is_staff' in request.data or 'is_superuser' in request.data:
                return Response(
                    {"error": "Vous ne pouvez pas modifier ces champs"},
                    status=status.HTTP_403_FORBIDDEN
                )

            serializer = ClientProfileSerializer(user, data=request.data, partial=True)
        else:
            serializer = UserWriteSerializer(user, data=request.data, partial=partial)

        if serializer.is_valid():
            serializer.save()
            return Response(UserSerializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ----- Suppression (admin uniquement) -----
    def destroy(self, request, pk=None):
        if not self.is_admin(request.user):
            return Response(
                {"error": "Seul un administrateur peut supprimer des utilisateurs"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "Utilisateur non trouvé"}, status=status.HTTP_404_NOT_FOUND)

        if user.id == request.user.id:
            return Response(
                {"error": "Vous ne pouvez pas supprimer votre propre compte"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ----- Actions custom -----
    @action(detail=False, methods=['get'], url_path='clients')
    def list_clients(self, request):
        """Liste tous les clients (admin/vendeur uniquement)"""
        if request.user.role not in ['admin', 'vendeur']:
            return Response({"error": "Permission refusée"}, status=status.HTTP_403_FORBIDDEN)

        clients = User.objects.filter(role='client').order_by('-created_at')
        return Response(UserSerializer(clients, many=True).data)

    @action(detail=False, methods=['get'], url_path='vendeurs')
    def list_vendeurs(self, request):
        """Liste tous les vendeurs (admin uniquement)"""
        if not self.is_admin(request.user):
            return Response({"error": "Permission refusée"}, status=status.HTTP_403_FORBIDDEN)

        vendeurs = User.objects.filter(role='vendeur').order_by('-created_at')
        return Response(UserSerializer(vendeurs, many=True).data)


# ============================================================
# Profil de l'utilisateur connecté
# ============================================================

class ProfileViewset(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserDetailSerializer

    def retrieve(self, request):
        serializer = self.serializer_class(request.user)
        return Response(serializer.data)

    def update(self, request):
        """
        Chaque utilisateur peut mettre à jour son profil,
        mais jamais son rôle ni is_staff/is_superuser.
        """
        forbidden = ['role', 'is_staff', 'is_superuser']
        for field in forbidden:
            if field in request.data:
                return Response(
                    {"error": f"Le champ '{field}' ne peut pas être modifié ici"},
                    status=status.HTTP_403_FORBIDDEN
                )

        serializer = ClientProfileSerializer(
            request.user, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(UserDetailSerializer(request.user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)