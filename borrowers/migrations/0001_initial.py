# Generated by Django 5.1 on 2025-04-30 10:05

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='BorrowerDocuments',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('id_proof', models.FileField(upload_to='documents/id_proof/')),
                ('bank_statement', models.FileField(upload_to='documents/bank_statements/')),
                ('payslip', models.FileField(upload_to='documents/payslips/')),
                ('chief_letter', models.FileField(upload_to='documents/chief_letter/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='BorrowerProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(default='', max_length=100)),
                ('gender', models.CharField(choices=[('', ''), ('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')], default='', max_length=100)),
                ('title', models.CharField(choices=[('', ''), ('Mr', 'Mr.'), ('Ms', 'Ms.'), ('Mrs', 'Mrs.'), ('Dr', 'Dr.'), ('Prof', 'Prof.')], default='', max_length=4)),
                ('date_of_birth', models.CharField(default='', max_length=20)),
                ('id_number', models.CharField(default='', max_length=30)),
                ('marital_status', models.CharField(choices=[('', ''), ('Single', 'Single'), ('Married', 'Married'), ('Divorced', 'Divorced'), ('Widowed', 'Widowed')], default='', max_length=20)),
                ('phone_number', models.CharField(default='', max_length=100)),
                ('email_address', models.CharField(default='', max_length=100)),
                ('employer_name', models.CharField(default='', max_length=100)),
                ('employment_position', models.CharField(default='', max_length=100)),
                ('income', models.DecimalField(decimal_places=2, default=0, max_digits=50)),
                ('position_level', models.CharField(choices=[('', ''), ('entry-level', 'entry-level'), ('intermediate', 'intermediate'), ('senior-level', 'senior-level')], default='', max_length=50)),
                ('home_address', models.CharField(default='', max_length=100)),
                ('employer_address', models.CharField(default='', max_length=100)),
                ('income_type', models.CharField(choices=[('', ''), ('Salary', 'Salary'), ('Wages', 'Wages'), ('Other', 'Other')], default='', max_length=100)),
                ('pay_day', models.PositiveSmallIntegerField(blank=True, help_text='Day of the month you usually receive your salary (1–31).', null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)])),
                ('monthly_expenses', models.CharField(choices=[('', ''), ('Rent', 'Rent'), ('Utilities', 'Utilities'), ('Debt payment', 'Debt payment'), ('Insurence', 'Insurence'), ('Stokvel', 'Stokvel')], default='', max_length=100)),
                ('existing_debts', models.CharField(choices=[('', ''), ('Loans', 'Loans'), ('Credit Cards', 'Credit Cards'), ('Credit Accounts', 'Credit Accounts'), ('No Debts', 'No Debts')], default='', max_length=100)),
                ('credit_score', models.IntegerField(default=300, validators=[django.core.validators.MinValueValidator(300), django.core.validators.MaxValueValidator(850)])),
                ('credit_intend', models.CharField(default='', max_length=100)),
                ('is_over_18', models.BooleanField(default=False)),
                ('agrees_to_terms', models.BooleanField(default=False)),
                ('agrees_to_credit_conditions', models.BooleanField(default=False)),
                ('information_consent', models.BooleanField(default=False)),
            ],
        ),
    ]
