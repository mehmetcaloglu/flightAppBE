first data generation:
python manage.py runscript create_pilots
python manage.py runscript create_planes


run the server:
daphne -b 0.0.0.0 -p 8000 plane_fleet.asgi:application