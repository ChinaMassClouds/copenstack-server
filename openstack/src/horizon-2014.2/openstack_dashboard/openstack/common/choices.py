CHOICES_VIRTUAL_TYPE = [('vcenter','VMware vCenter'),
                        ('cserver','Massclouds cCenter')]

CSERVER_TEMPLATES_BLACK_LIST = ['Blank']

def translate(enum,code):
    for i in enum:
        if i[0] == code:
            return i[1]
    return code

_translate = translate