from horizon import tables
from django.utils.translation import ugettext_lazy as _
import datetime

class LogFilterAction(tables.FilterAction):
    filter_field = 'user_name'



class LogTable(tables.DataTable):
    create_date = tables.Column("create_date", verbose_name=_("Time"),
                                filters=(lambda x:datetime.datetime.strftime(x,'%Y-%m-%d %H:%M:%S'),))
    user_name = tables.Column("user_name", verbose_name=_("Name"))
    roel_name = tables.Column("role_name", verbose_name=_("Role"))
    message = tables.Column("message", verbose_name=_("Message"))

    class Meta:
        name = "log"
        verbose_name = _("Log")
        table_actions = (LogFilterAction,)

    def get_columns(self):
        self.columns['multi_select'].attrs = {'class':'hide'}
        return self.columns.values()