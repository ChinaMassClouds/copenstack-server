from horizon import tables
from openstack_dashboard.dashboards.admin.checkhost import tables as host_tables
from horizon import exceptions
from django.utils.translation import ugettext_lazy as _
from openstack_dashboard.models import apply
from openstack_dashboard import api
from django.utils.datastructures import SortedDict


class IndexView(tables.MultiTableView):
    template_name = 'admin/checkhost/index.html'
    table_classes = (host_tables.CheckHostTable,
                     host_tables.HistoryTable)

    def get_checkhost_data(self):
        """
        check host show
        """
        instances = apply.objects.filter(status='0')
        try:
            flavors = api.nova.flavor_list(self.request)
        except Exception:
            flavors = []
            exceptions.handle(self.request, ignore=True)
        try:
            images, more, prev = api.glance.image_list_detailed(
                self.request)
        except Exception:
            images = []
            exceptions.handle(self.request, ignore=True)
        full_flavors = SortedDict([(str(flavor.id), flavor)
                                   for flavor in flavors])
        image_map = SortedDict([(str(image.id), image)
                                for image in images])
        for instance in instances:
            if instance.image_id in image_map:
                instance.image_name = image_map[instance.image_id].name
            try:
                flavor_id = instance.flavor_id
                if flavor_id in full_flavors:
                    instance.full_flavor = full_flavors[flavor_id]
                else:
                    instance.full_flavor = api.nova.flavor_get(
                        self.request, flavor_id)
            except Exception:
                msg = _('Unable to retrieve instance size information.')
                exceptions.handle(self.request, msg)
        return instances

    def get_history_data(self):
        instances = apply.objects.exclude(status='0')
        try:
            flavors = api.nova.flavor_list(self.request)
        except Exception:
            flavors = []
            exceptions.handle(self.request, ignore=True)
        try:
            images, more, prev = api.glance.image_list_detailed(
                self.request)
        except Exception:
            images = []
            exceptions.handle(self.request, ignore=True)
        full_flavors = SortedDict([(str(flavor.id), flavor)
                                   for flavor in flavors])
        image_map = SortedDict([(str(image.id), image)
                                for image in images])
        for instance in instances:
            if instance.image_id in image_map:
                instance.image_name = image_map[instance.image_id].name
            try:
                flavor_id = instance.flavor_id
                if flavor_id in full_flavors:
                    instance.full_flavor = full_flavors[flavor_id]
                else:
                    instance.full_flavor = api.nova.flavor_get(
                        self.request, flavor_id)
            except Exception:
                msg = _('Unable to retrieve instance size information.')
                exceptions.handle(self.request, msg)
        return instances
