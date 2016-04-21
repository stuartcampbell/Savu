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
.. module:: base_multi_modal_loader
   :platform: Unix
   :synopsis: Contains a base class from which all multi-modal loaders are \
   derived.

.. moduleauthor:: Nicola Wadeson <scientificsoftware@diamond.ac.uk>

"""

import h5py
import logging
from savu.data.data_structures.data_add_ons import DataMapping

from savu.plugins.loaders.base_multi_modal_loader import BaseMultiModalLoader


class BaseI18MultiModalLoader(BaseMultiModalLoader):
    """
    This class provides a base for all multi-modal loaders
    :param fast_axis: what is the fast axis called. Default:"x".
    :param scan_pattern: what was the scan. Default: ["rotation","x"].
    :param x: where is x in the \
        file. Default:'entry1/raster_counterTimer01/traj1ContiniousX'.
    :param y: where is y in the file. Default:None.
    :param rotation: where is rotation in the \
        file. Default:'entry1/raster_counterTimer01/sc_sample_thetafine'.
    :param monochromator: where is the \
        monochromator. Default: 'entry1/instrument/DCM/energy'.
    """
    def __init__(self, name='BaseI18MultiModalLoader'):
        super(BaseI18MultiModalLoader, self).__init__(name)

    def multi_modal_setup(self, ltype):
        # set up the file handles
        exp = self.exp
        data_obj = exp.create_data_object("in_data", ltype)
        data_obj.backing_file = \
            h5py.File(exp.meta_data.get_meta_data("data_file"), 'r')
        f = data_obj.backing_file
        logging.debug("Creating file '%s' '%s'_entry",
                      data_obj.backing_file.filename, ltype)
        exp.meta_data.set_meta_data("mono_energy",
                                    f[self.parameters['monochromator']])
        x = f[self.parameters['x']].value

        if self.parameters['x'] is not None:
            data_obj.meta_data.set_meta_data("x", x[0, :])
        if self.parameters['y'] is not None:
            y = f[self.parameters['y']].value
            data_obj.meta_data.set_meta_data("y", y)
        if self.parameters['rotation'] is not None:
            rotation_angle = f[self.parameters['rotation']].value
            if rotation_angle.ndim > 1:
                rotation_angle = rotation_angle[:, 0]

                data_obj.meta_data.set_meta_data(
                    "rotation_angle", rotation_angle)
        return data_obj

    def set_motors(self, data_obj, ltype):
        # now lets extract the map, if there is one!
        # to begin with
        data_obj.data_mapping = DataMapping()
        logging.debug("========="+ltype+"=========")
        motors = self.parameters['scan_pattern']
        data_obj.data_mapping.set_axes(self.parameters['scan_pattern'])
        f = data_obj.backing_file
        nAxes = len(data_obj.get_shape())
        print "number of axes"+str(nAxes)
        #logging.debug nAxes
        cts = 0
        chk = 0
        motor_type = []
        labels = []
        fast_axis = self.parameters["fast_axis"]
        print 'my motors are:'+str(motors)
        logging.debug("axes input are:"+str(motors))
        for ii in range(nAxes):
            # find the rotation axis
            print ii
            try:
                data_axis = self.parameters[motors[ii]]# get that out the file
                logging.debug("the data axis is %s" % str(data_axis))
                if motors[ii]=="rotation":
                    data_obj.data_mapping._is_tomo = True
                    motor_type.append('rotation')
                    label = 'rotation_angle'
                    units = 'degrees'
                    logging.debug(ltype + " reader: %s", "is a tomo scan")
                elif motors[ii] in ["x","y"]:
                    cts += 1  # increase the order of the map
                    motor_type.append('translation')
                    if (motors[ii]==fast_axis):
                        label='x'
                    else:
                        label='y'
                    units = 'mm'
            except:
                motor_type.append('None')
                #now the detector axes
                if ltype =='fluo':
                    label = 'energy'
                    units = 'counts'
                elif ltype =='xrd':
                    if chk==0:
                        label = 'detector_x'
                    elif chk==1:
                        label = 'detector_y'
                    units = 'index'
                    chk=chk+1
            labels.append(label+'.'+units)
        if not motors:
            logging.debug("%s reader: No maps found!", ltype)
        #logging.debug labels
        data_obj.set_axis_labels(*tuple(labels))
        data_obj.data_mapping.set_motors(motors)
        data_obj.data_mapping.set_motor_type(motor_type)
        if (cts):
            data_obj.data_mapping._is_map = cts
        else:
            logging.debug("'%s' reader: No translations found!", ltype)
            pass
        logging.debug("axis labels:"+str(labels))
        logging.debug("motor_type:"+str(motor_type))


    def add_patterns_based_on_acquisition(self, data_obj, ltype):
        motor_type = data_obj.data_mapping.get_motor_type()
        dims = range(len(motor_type))
        projection = []
        for item, key in enumerate(motor_type):
            if key == 'translation':
                projection.append(item)
#                 logging.debug projection
            elif key == 'rotation':
                rotation = item

        if data_obj.data_mapping._is_map:
            proj_dir = tuple(projection)
            logging.debug("is a map")
            logging.debug("the proj cores are"+str(proj_dir))
            logging.debug("the proj slices are"+str(tuple(set(dims) - set(proj_dir))))
            data_obj.add_pattern("PROJECTION", core_dir=proj_dir,
                                 slice_dir=tuple(set(dims) - set(proj_dir)))

        if data_obj.data_mapping._is_tomo:
            #rotation and fast axis
            sino_dir = (rotation, proj_dir[-1])
            logging.debug("is a tomo")
            logging.debug("the sino cores are:"+str(sino_dir))
            logging.debug("the sino slices are:"+str(tuple(set(dims) - set(sino_dir))))
            data_obj.add_pattern("SINOGRAM", core_dir=sino_dir,
                                 slice_dir=tuple(set(dims) - set(sino_dir)))
        
        if ltype is 'fluo':
            spec_core = (-1,) # it will always be this
            spec_slice = tuple(dims[:-1])
            logging.debug("is a fluo")
            logging.debug("the fluo cores are:"+str(spec_core))
            logging.debug("the fluo slices are:"+str(spec_slice))
            data_obj.add_pattern("SPECTRUM", core_dir=spec_core,
                                 slice_dir=spec_slice)
        
        
        if ltype is 'xrd':
            diff_core = (-2,-1) # it will always be this
            diff_slice = tuple(dims[:-2])
            logging.debug("is a diffraction")
            logging.debug("the diffraction cores are:"+str(diff_core))
            logging.debug("the diffraction slices are:"+str(diff_slice))
            data_obj.add_pattern("DIFFRACTION", core_dir=diff_core,
                                 slice_dir=diff_slice)
        
