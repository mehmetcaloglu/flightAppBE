from django.contrib.gis.db import models
from django.contrib.gis.geos import Point


class Pilot(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Plane(models.Model):
    name = models.CharField(max_length=100, unique=True)
    pilot = models.OneToOneField(Pilot, on_delete=models.CASCADE, related_name='plane', null=True, blank=True)
    start_point = models.PointField(srid=4326)  # WGS84 coordinate system
    end_point = models.PointField(srid=4326)
    current_position = models.PointField(srid=4326)
    is_going_to_end = models.BooleanField(default=True)  # True: start->end, False: end->start
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Command(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    plane = models.ForeignKey(Plane, on_delete=models.CASCADE, related_name='commands')
    target_location = models.PointField(srid=4326)  # Command's target point
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Command: {self.plane.name} - {self.status}"

    class Meta:
        ordering = ['-created_at']
