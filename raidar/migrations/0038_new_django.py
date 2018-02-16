# Generated by Django 2.0.2 on 2018-02-16 12:59

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('raidar', '0037_make_added_fields_nonnull'),
    ]

    operations = [
        migrations.AlterField(
            model_name='encounter',
            name='uploaded_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_encounters', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='upload',
            name='uploaded_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='unprocessed_uploads', to=settings.AUTH_USER_MODEL),
        ),
    ]
