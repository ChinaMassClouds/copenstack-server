#!/usr/bin/env python
#-*- coding: utf-8 -*-
#create:2015-8-5 by zhangdebo
from dbbase import database
from config import Paths
import os
import time

    
def startUpgrade():
    db = database()

    # 查出所有sql文件
    sqlpath = Paths().src_dir + '/utils/db/upgrades/'
    sqlfiles = os.listdir(sqlpath)
    
    # 遍历sql文件，过滤出在升级记录表不存在的sql文件
    hist = [s['sqlfile'] for s in db.select_fetchall("select sqlfile from db_upgrade_hist")]

    to_up = []
    for s in sqlfiles:
        if s not in hist:
            to_up.append(s)
    # 按顺序执行sql文件，每执行成功一个，记录到升级记录表
    if to_up:
        to_up.sort()
        upgrade_time = time.strftime("%Y-%m-%d %H:%M:%S")
        for f in to_up:
            of = open(sqlpath + f,'r')
            sql = ''
            for line in of.readlines():
                arr = line.split()
                if not arr or arr[0].startswith('--'):
                    continue
                sql += line
                if arr[-1].endswith(';'):
                    db.execute(sql)
                    sql = ''
            histsql = "insert into db_upgrade_hist(sqlfile,upgrade_date) values('%s','%s')" % (f,upgrade_time)
            db.execute(histsql)
                
                