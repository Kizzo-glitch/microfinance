
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework.permissions import AllowAny

from django.conf import settings
from django.conf.urls.static import static



schema_view = get_schema_view(
	openapi.Info(
		title="Microfinance API",
		default_version='v1',
		description="API documentation for the Microfinance app",
	),
	public=True,
	permission_classes=[AllowAny],
)

urlpatterns = [
	path('admin/', admin.site.urls),
	path('', include('micro.urls')),
	path('lenders/', include('lenders.urls')),
	path('borrowers/', include('borrowers.urls')),

	path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
	path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
	path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
