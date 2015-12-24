# -*- coding: utf-8 -*-

import logging.handlers  
import os
from constant import LOG_PATH

class LogRecord():
    """日志模块"""
    _instance = 0
    def __init__(self):
        if os.path.isfile(LOG_PATH):
            size = os.path.getsize(LOG_PATH)
            if size > 1000000:
                size_in_MB = size/1000000.0
                if size_in_MB > 5:
                    os.system("rm -f %s" % LOG_PATH)

        if not os.path.exists(os.path.dirname(LOG_PATH)):
            os.makedirs(os.path.dirname(LOG_PATH))

        handler = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes = 1024*1024, backupCount = 5) # 实例化handler   
        fmt = '%(asctime)s - %(filename)s:%(lineno)s - %(name)s - %(message)s'  
    
        formatter = logging.Formatter(fmt)   # 实例化formatter  
        handler.setFormatter(formatter)      # 为handler添加formatter

        self.logger = logging.getLogger(LOG_PATH)    # 获取名为tst的logger  
        self.logger.addHandler(handler)           # 为logger添加handler  
        self.logger.setLevel(logging.DEBUG)  
        
    def info(self, info):
        self.logger.info(info)  
        
    def error(self, info):
        self.logger.error(info)
        
    def warn(self, info):
        self.logger.warn(info)
        
    @classmethod 
    def instance(cls):
        if (cls._instance == 0):
            cls._instance = LogRecord()
            
        return cls._instance
        
log = LogRecord()
    