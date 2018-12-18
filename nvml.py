# encoding: utf-8

# project
from checks import AgentCheck

# psutil
import psutil

# pynvml
import pynvml

import os
import pwd
import docker

__version__ = '0.1.4'
__author__ = 'Takashi NAGAI, Alejandro Ferrari'


class NvmlCheck(AgentCheck):

    def _dict2list(self, tags={}):
        return [u"{k}:{v}".format(k=k, v=v) for k, v in tags.items()]

    def get_process_owner(self, pid):
        try:
            proc = os.stat("/proc/%d" % int(pid))
            uid = proc.st_uid
            return pwd.getpwuid(uid)[0]
        except OSError:
            return None

    def get_container_name(self, pid):
        try:
            content = ""
            with open("/proc/%d/cgroup" % int(pid)) as f:
                content = f.readline().rstrip()
            content = content.split(":")[-1]
            content = content.split("/")[-1]
            docker_info = docker.from_env().containers.get(content)
            return docker_info.name, docker_info.image.tags[-1]
        except:
            return None, None

    def check(self, instance):
        pynvml.nvmlInit()

        msg_list = []
        gpus_in_use = 0
        try:
            deviceCount = pynvml.nvmlDeviceGetCount()
        except:
            deviceCount = 0
        for device_id in xrange(deviceCount):
            handle = pynvml.nvmlDeviceGetHandleByIndex(device_id)
            name = pynvml.nvmlDeviceGetName(handle)
            tags = dict(name="{}-{}".format(name, device_id))
            d_tags = self._dict2list(tags)
            # temperature info
            try:
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                self.gauge('nvml.temp', temp, tags=d_tags)
            except pynvml.NVMLError as err:
                msg_list.append(u'nvmlDeviceGetTemperature:{}'.format(err))
            # memory info
            try:
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                self.gauge('nvml.mem.total', mem.total, tags=d_tags)
                self.gauge('nvml.mem.used', mem.used, tags=d_tags)
                self.gauge('nvml.mem.free', mem.free, tags=d_tags)
            except pynvml.NVMLError as err:
                msg_list.append(u'nvmlDeviceGetMemoryInfo:{}'.format(err))
            # utilization GPU/Memory info
            try:
                util_rate = pynvml.nvmlDeviceGetUtilizationRates(handle)
                self.gauge('nvml.util.gpu', util_rate.gpu, tags=d_tags)
                self.gauge('nvml.util.memory', util_rate.memory, tags=d_tags)
                gpus_in_use += 1 if util_rate.memory > 50.0 else 0
            except pynvml.NVMLError as err:
                msg_list.append(u'nvmlDeviceGetUtilizationRates:{}'.format(err))
            # utilization Encoder info
            try:
                util_encoder = pynvml.nvmlDeviceGetEncoderUtilization(handle)
                self.log.debug('nvml.util.encoder %s' % long(util_encoder[0]))
                self.gauge('nvml.util.encoder', long(util_encoder[0]), tags=d_tags)
            except pynvml.NVMLError as err:
                msg_list.append(u'nvmlDeviceGetEncoderUtilization:{}'.format(err))
            # utilization Decoder info
            try:
                util_decoder = pynvml.nvmlDeviceGetDecoderUtilization(handle)
                self.log.debug('nvml.util.decoder %s' % long(util_decoder[0]))
                self.gauge('nvml.util.decoder', long(util_decoder[0]), tags=d_tags)
            except pynvml.NVMLError as err:
                msg_list.append(u'nvmlDeviceGetDecoderUtilization:{}'.format(err))
            # Compute running processes
            try:
                cps = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
                self.gauge('nvml.process.count', len(cps), d_tags)
                for ps in cps:
                    p_tags = tags.copy()
                    p_tags['pid'] = ps.pid
                    p_tags['pname'] = pynvml.nvmlSystemGetProcessName(ps.pid)
                    p_tags['puser'] = self.get_process_owner(ps.pid)
                    docker_name, docker_image = self.get_container_name(ps.pid)
                    p_tags['docker_image'] = docker_image
                    p_tags['docker_name'] = docker_name
                    p_tags = self._dict2list(p_tags)
                    print p_tags
                    self.gauge('nvml.process.used_gpu_memory', ps.usedGpuMemory, tags=p_tags)
            except pynvml.NVMLError as err:
                msg_list.append(u'nvmlDeviceGetComputeRunningProcesses:{}'.format(err))
        self.gauge('nvml.gpus_in_use_count', gpus_in_use)
        if msg_list:
            status = AgentCheck.CRITICAL
            msg = u','.join(msg_list)
        else:
            status = AgentCheck.OK
            msg = u'Ok'
        pynvml.nvmlShutdown()

        self.service_check('nvml.check', status, message=msg)


