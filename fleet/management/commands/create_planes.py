import random
import math
import string
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from fleet.models import Plane, Pilot


class Command(BaseCommand):
    help = '10,000 uçak oluşturur (linear rotalar + 1:1 pilot eşleştirmesi)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=10000,
            help='Oluşturulacak uçak sayısı (default: 10000)'
        )

    def calculate_destination(self, lat, lng, distance_km, bearing_degrees):
        """
        Bir noktadan belirli mesafe ve yön ile hedef koordinatı hesaplar
        """
        R = 6371  # Dünya yarıçapı (km)
        
        lat_rad = math.radians(lat)
        lng_rad = math.radians(lng)
        bearing_rad = math.radians(bearing_degrees)
        
        new_lat_rad = math.asin(
            math.sin(lat_rad) * math.cos(distance_km / R) +
            math.cos(lat_rad) * math.sin(distance_km / R) * math.cos(bearing_rad)
        )
        
        new_lng_rad = lng_rad + math.atan2(
            math.sin(bearing_rad) * math.sin(distance_km / R) * math.cos(lat_rad),
            math.cos(distance_km / R) - math.sin(lat_rad) * math.sin(new_lat_rad)
        )
        
        new_lat = math.degrees(new_lat_rad)
        new_lng = math.degrees(new_lng_rad)
        
        # Longitude normalleştir (-180, 180)
        new_lng = ((new_lng + 180) % 360) - 180
        
        return new_lat, new_lng

    def haversine_distance(self, lat1, lng1, lat2, lng2):
        """
        İki koordinat arasındaki mesafeyi hesaplar (km)
        """
        R = 6371  # Dünya yarıçapı (km)
        
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        
        a = (math.sin(dlat / 2) ** 2 + 
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
             math.sin(dlng / 2) ** 2)
        
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c

    def spherical_interpolation(self, lat1, lng1, lat2, lng2, progress):
        """
        İki nokta arasında spherical interpolation (SLERP) yapar
        Dünya'nın küresel yapısını dikkate alır
        """
        # Koordinatları radyan'a çevir
        lat1_rad = math.radians(lat1)
        lng1_rad = math.radians(lng1)
        lat2_rad = math.radians(lat2)
        lng2_rad = math.radians(lng2)
        
        # İki nokta arasındaki angular distance hesapla
        d = 2 * math.asin(math.sqrt(
            math.sin((lat2_rad - lat1_rad) / 2) ** 2 + 
            math.cos(lat1_rad) * math.cos(lat2_rad) * 
            math.sin((lng2_rad - lng1_rad) / 2) ** 2
        ))
        
        # Eğer çok yakın noktalarsa, basit linear interpolation yap
        if d < 1e-6:
            result_lat = lat1 + (lat2 - lat1) * progress
            result_lng = lng1 + (lng2 - lng1) * progress
            return result_lat, result_lng
        
        # Spherical interpolation parametreleri
        A = math.sin((1 - progress) * d) / math.sin(d)
        B = math.sin(progress * d) / math.sin(d)
        
        # 3D Cartesian koordinatlarına çevir
        x1 = math.cos(lat1_rad) * math.cos(lng1_rad)
        y1 = math.cos(lat1_rad) * math.sin(lng1_rad)
        z1 = math.sin(lat1_rad)
        
        x2 = math.cos(lat2_rad) * math.cos(lng2_rad)
        y2 = math.cos(lat2_rad) * math.sin(lng2_rad)
        z2 = math.sin(lat2_rad)
        
        # Interpolated 3D point
        x = A * x1 + B * x2
        y = A * y1 + B * y2
        z = A * z1 + B * z2
        
        # Geri lat/lng'ye çevir
        result_lat = math.degrees(math.atan2(z, math.sqrt(x*x + y*y)))
        result_lng = math.degrees(math.atan2(y, x))
        
        return result_lat, result_lng

    def generate_linear_route(self):
        """
        Linear rota oluşturur: start -> current -> end
        """
        # 1. Start point (dünya genelinde random)
        start_lat = random.uniform(-85, 85)  # Kutupları biraz exclude
        start_lng = random.uniform(-180, 180)
        
        # 2. End point (start'tan 400-2000km mesafede)
        distance = random.uniform(400, 2000)
        bearing = random.uniform(0, 360)
        end_lat, end_lng = self.calculate_destination(start_lat, start_lng, distance, bearing)
        
        # 3. Current position (spherical interpolation ile)
        progress = random.uniform(0, 1)  # 0=start'ta, 1=end'te
        current_lat, current_lng = self.spherical_interpolation(
            start_lat, start_lng, end_lat, end_lng, progress
        )
        
        return {
            'start': Point(start_lng, start_lat, srid=4326),
            'end': Point(end_lng, end_lat, srid=4326),
            'current': Point(current_lng, current_lat, srid=4326)
        }

    def handle(self, *args, **options):
        count = options['count']
        
        self.stdout.write(f'{count} uçak oluşturuluyor...')
        
        # Pilot kontrolü
        pilot_count = Pilot.objects.count()
        if pilot_count < count:
            self.stdout.write(
                self.style.ERROR(f'Yetersiz pilot! {pilot_count} pilot var, {count} gerekli.')
            )
            return
        
        # Mevcut uçakları temizle
        existing_count = Plane.objects.count()
        if existing_count > 0:
            self.stdout.write(f'Mevcut {existing_count} uçak siliniyor...')
            Plane.objects.all().delete()
        
        # Pilotları al ve karıştır
        self.stdout.write('Pilotlar hazırlanıyor...')
        all_pilots = list(Pilot.objects.all())
        random.shuffle(all_pilots)
        
        # Uçak listesi
        planes_to_create = []
        
        self.stdout.write('Uçaklar ve rotalar oluşturuluyor...')
        
        for i in range(count):
            # Uçak adı: AB-0001 formatında (2 random harf + numara)
            random_prefix = ''.join(random.choices(string.ascii_uppercase, k=2))
            plane_name = f"{random_prefix}-{i+1:04d}"
            
            # Linear rota oluştur
            route = self.generate_linear_route()
            
            # Uçak oluştur
            plane = Plane(
                name=plane_name,
                pilot=all_pilots[i],  # 1:1 eşleştirme
                start_point=route['start'],
                end_point=route['end'],
                current_position=route['current']
            )
            
            planes_to_create.append(plane)
            
            # Progress göstergesi (her 1000'de bir)
            if (i + 1) % 1000 == 0:
                self.stdout.write(f'  {i + 1} / {count} hazırlandı...')
        # Bulk create (veritabanına toplu insert)
        self.stdout.write('Veritabanına kaydediliyor...')
        
        import time
        start_time = time.time()
        
        Plane.objects.bulk_create(planes_to_create, batch_size=500)
        
        end_time = time.time()
        duration = end_time - start_time
        
        self.stdout.write(
            self.style.SUCCESS(f'Başarıyla {count} uçak {duration:.2f} saniyede db ye yazıldı!')
        )
        
        # Örnekler göster
        sample_planes = Plane.objects.select_related('pilot').order_by('?')[:3]
        self.stdout.write('\nÖrnek uçaklar:')
        for plane in sample_planes:
            distance = self.haversine_distance(
                plane.start_point.y, plane.start_point.x,
                plane.end_point.y, plane.end_point.x
            )
            self.stdout.write(
                f'  - {plane.name} (Pilot: {plane.pilot.name}) - Rota: {distance:.1f}km'
            ) 