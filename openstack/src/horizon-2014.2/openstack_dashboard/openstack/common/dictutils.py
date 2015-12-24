import uuid

class Dict2Object:
    def __init__(self, **entries):
        self.id = None
        self.__dict__.update(entries)
        
def DictList2ObjectList(dicList,id_key = None):
    objList = []
    for dic in dicList:
        if not dic.get('id'):
            if id_key and dic.get(id_key):
                dic['id'] = dic.get(id_key)
            else:
                dic['id'] = uuid.uuid4()
        objList.append(Dict2Object(**dic))
    return objList