# This file is part of cloud-init. See LICENSE file for license information.

"""Azure Cloud image Base class."""

from tests.cloud_tests import LOG

from ..images import Image
from .snapshot import AzureCloudSnapshot


class AzureCloudImage(Image):
    """Azure Cloud backed image."""

    platform_name = 'azurecloud'

    def __init__(self, platform, config, image_id):
        """Set up image.

        @param platform: platform object
        @param config: image configuration
        @param image_id: image id used to boot instance
        """
        super(AzureCloudImage, self).__init__(platform, config)
        self._img_instance = None
        self.image_id = image_id

    @property
    def _instance(self):
        """Internal use only, returns a running instance"""
        if not self._img_instance:
            self._img_instance = self.platform.create_instance(
                self.properties, self.config, self.features,
                self.image_id, user_data=None)
            self._img_instance.start(wait=True, wait_for_cloud_init=True)
        return self._img_instance

    def destroy(self):
        """Delete the instance used to create a custom image."""
        if self._img_instance:
            LOG.debug('Deleting backing instance %s',
                      self._img_instance.vm_name)
            delete_vm = self.platform.compute_client.virtual_machines.delete(
                self.platform.resource_group.name, self._img_instance.vm_name)
            delete_vm.wait()

        super(AzureCloudImage, self).destroy()

    def _execute(self, *args, **kwargs):
        """Execute command in image, modifying image."""
        LOG.debug('executing commands on image')
        self._instance.start(wait=True)
        return self._instance._execute(*args, **kwargs)

    def push_file(self, local_path, remote_path):
        """Copy file at 'local_path' to instance at 'remote_path'."""
        LOG.debug('pushing file to image')
        return self._instance.push_file(local_path, remote_path)

    def run_script(self, *args, **kwargs):
        """Run script in image, modifying image.

        @return_value: script output
        """
        LOG.debug('running script on image')
        self._instance.start()
        return self._instance.run_script(*args, **kwargs)

    def snapshot(self):
        """ Create snapshot (image) of instance, wait until done.

        If no instance has been booted, base image is returned.
        Otherwise runs the clean script, deallocates, generalizes
        and creates custom image from instance.
        """
        LOG.debug('creating snapshot of image')
        if not self._img_instance:
            LOG.debug('No existing image, snapshotting base image')
            return AzureCloudSnapshot(self.platform, self.properties,
                                      self.config, self.features,
                                      self._instance.vm_name,
                                      delete_on_destroy=False)

        LOG.debug('creating snapshot from instance: %s', self._img_instance)
        if self.config.get('boot_clean_script'):
            self._img_instance.run_script(self.config.get('boot_clean_script'))

        LOG.debug('deallocating instance %s', self._instance.vm_name)
        deallocate = self.platform.compute_client.virtual_machines.deallocate(
            self.platform.resource_group.name, self._instance.vm_name)
        deallocate.wait()

        LOG.debug('generalizing instance %s', self._instance.vm_name)
        self.platform.compute_client.virtual_machines.generalize(
            self.platform.resource_group.name, self._instance.vm_name)

        image_params = {
            "location": self.platform.location,
            "properties": {
                "sourceVirtualMachine": {
                    "id": self._img_instance.instance.id
                }
            }
        }
        LOG.debug('updating resource group image %s', self._instance.vm_name)
        self.platform.compute_client.images.create_or_update(
            self.platform.resource_group.name, self._instance.vm_name,
            image_params)

        LOG.debug('destroying self')
        self.destroy()

        LOG.debug('snapshot complete')
        return AzureCloudSnapshot(self.platform, self.properties, self.config,
                                  self.features, self._instance.vm_name)

# vi: ts=4 expandtab
