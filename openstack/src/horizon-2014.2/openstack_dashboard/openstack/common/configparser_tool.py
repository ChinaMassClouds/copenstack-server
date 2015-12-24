def getOption(cfgparser,section,option):
    if cfgparser.has_option(section,option):
        return cfgparser.get(section,option)
    return ''

def setOption(cfgparser,section,option,value):
    if not cfgparser.has_section(section):
        cfgparser.add_section(section)
    cfgparser.set(section, option, value)