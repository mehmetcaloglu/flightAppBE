import random
import string
from django.core.management.base import BaseCommand
from fleet.models import Pilot


class Command(BaseCommand):
    help = '10,000 pilot oluşturur (4 karakterli random isimlerle)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=10000,
            help='Oluşturulacak pilot sayısı (default: 10000)'
        )

    def handle(self, *args, **options):
        count = options['count']
        
        self.stdout.write(f'{count} pilot oluşturuluyor...')
        
        # Mevcut pilotları temizle (opsiyonel)
        existing_count = Pilot.objects.count()
        if existing_count > 0:
            self.stdout.write(f'Mevcut {existing_count} pilot siliniyor...')
            Pilot.objects.all().delete()
        
        # Pilot listesi
        pilots_to_create = []
        used_names = set()  # Duplicate isimleri önlemek için
        
        # Random karakter seti (rakam + harf)
        characters = string.ascii_uppercase + string.digits  # A-Z + 0-9
        
        self.stdout.write('Random pilot isimleri oluşturuluyor...')
        
        while len(pilots_to_create) < count:
            # 4 karakterli random isim oluştur
            name = ''.join(random.choices(characters, k=4))
            
            # Duplicate kontrolü
            if name not in used_names:
                used_names.add(name)
                pilots_to_create.append(Pilot(name=name))
                
                # Progress göstergesi (her 1000'de bir)
                if len(pilots_to_create) % 1000 == 0:
                    self.stdout.write(f'  {len(pilots_to_create)} / {count} hazırlandı...')
        
        # Bulk create (veritabanına toplu insert)
        self.stdout.write('Veritabanına kaydediliyor...')
        Pilot.objects.bulk_create(pilots_to_create, batch_size=1000)
        
        self.stdout.write(
            self.style.SUCCESS(f'Başarıyla {count} pilot oluşturuldu!')
        )
        
        # Örnekler göster
        sample_pilots = Pilot.objects.order_by('?')[:5]  # Random 5 pilot
        self.stdout.write('\nÖrnek pilotlar:')
        for pilot in sample_pilots:
            self.stdout.write(f'  - {pilot.name} (ID: {pilot.id})') 