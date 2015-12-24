# Copyright 2012 Nebula, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from django.core.urlresolvers import reverse_lazy

from openstack_dashboard.dashboards.project.applydisk \
    import tables as project_tables
from horizon import tables
from openstack_dashboard.dashboards.project.applydisk \
    import forms as project_forms
from horizon import forms
from horizon import exceptions
from openstack_dashboard.usage import quotas
from openstack_dashboard.models import applydisk


class IndexView(tables.DataTableView):
    table_class = project_tables.VolumesTable
    template_name = 'project/applydisk/index.html'

    def get_data(self):
        return applydisk.objects.filter(user_name=self.request.user.username).exclude(status='5')



class CreateView(forms.ModalFormView):
    form_class = project_forms.CreateForm
    template_name = 'project/applydisk/create.html'
    success_url = reverse_lazy('horizon:project:applydisk:index')

    def get_context_data(self, **kwargs):
        context = super(CreateView, self).get_context_data(**kwargs)
        try:
            context['usages'] = quotas.tenant_limit_usages(self.request)
        except Exception:
            exceptions.handle(self.request)
        return context

