# Generated by Django 5.2 on 2025-04-11 17:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chatroom',
            name='id',
            field=models.AutoField(primary_key=True, serialize=False),
        ),
    ]
