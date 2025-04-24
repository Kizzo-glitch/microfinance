from django.contrib import admin

from .models import BorrowerProfile, BorrowerDocuments



# Register your models here.

admin.site.register(BorrowerProfile)
admin.site.register(BorrowerDocuments)


'''@admin.register(BorrowerProfile)
class BorrowerProfileAdmin(admin.ModelAdmin):
	list_display = ['first_name', 'last_name', 'title', 'date_of_birth']

	def get_title_display(self, obj):
		return obj.get_title_display()  # Display the human-readable label

	get_title_display.short_description = 'Title' '''