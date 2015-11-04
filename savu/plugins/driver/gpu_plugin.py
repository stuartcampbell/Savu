# Copyright 2014 Diamond Light Source Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
.. module:: gpu_plugin
   :platform: Unix
   :synopsis: Base class for all plugins which use a GPU on the target machine

.. moduleauthor:: Mark Basham <scientificsoftware@diamond.ac.uk>

"""
import logging


class GpuPlugin(object):
    """
    The base class from which all plugins should inherit.
    """

    def __init__(self):
        super(GpuPlugin, self).__init__()

    def run_plugin(self, exp, transport):

        expInfo = exp.meta_data
        processes = expInfo.get_meta_data("processes")
        process = expInfo.get_meta_data("process")

        count = 0
        gpu_processes = []
        for i in ["GPU" in i for i in processes]:
            if i:
                gpu_processes.append(count)
                count += 1
            else:
                gpu_processes.append(-1)
        if gpu_processes[process] >= 0:
            logging.debug("Running the CPU Process %i", process)
            new_processes = [i for i in processes if "GPU" in i]

            logging.debug("Pre-processing")

            self.pre_process()

            logging.debug("Main processing: process %s", self.__class__)
            #self.process(exp, new_processes, cpu_processes[process])
            transport.process(self)

            exp.barrier()
            logging.debug("Post-processing")
            self.post_process()

            self.clean_up()

        logging.debug("Not Running the task as not GPU")
        return

    def process(self, data, output, processes, plugin):
        """
        This method is called after the plugin has been created by the
        pipeline framework

        :param data: The input data object.
        :type data: savu.data.structures
        :param data: The output data object
        :type data: savu.data.structures
        :param processes: The number of processes which will be doing the work
        :type path: int
        :param path: The specific process which we are
        :type path: int
        """
        logging.error("process needs to be implemented for proc %i of %i :" +
                      " input is %s and output is %s",
                      plugin, processes, data.__class__, output.__class__)
        raise NotImplementedError("process needs to be implemented")
