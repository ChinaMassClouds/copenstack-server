
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "website.settings")

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

#####################
import base64
import datetime
import os

authorization_dir = '/usr/local/authorization/'
if not os.path.exists(authorization_dir):
    os.makedirs(authorization_dir, 0777)
probation_file = authorization_dir + 'probation'
probation_days = 90
if not os.path.exists(probation_file):
    with open(probation_file,'w') as f:
        today = datetime.datetime.now()
        end_day = today + datetime.timedelta(probation_days - 1)
        end_day_str = datetime.datetime.strftime(end_day,'%Y-%m-%d')
        f.write(base64.b64encode(end_day_str))