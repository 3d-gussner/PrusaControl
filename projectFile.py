# -*- coding: utf-8 -*-
from copy import deepcopy

__author__ = 'Tibor Vavra'

import ast
import logging
from abc import ABCMeta, abstractmethod
from io import StringIO
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.cElementTree as ET
import os
#import io

import numpy
from io import BytesIO
import stl

from stl.mesh import Mesh

from sceneData import ModelTypeStl, MultiModel

fileExtension = 'prusa'


class ProjectFile(object):

    def __init__(self, scene, filename=""):
        if filename:
            self.scene_xml = None
            self.scene = scene

            #TODO:check which version is scene.xml version and according to chose class to read project file
            self.version = Version_1_0()
            self.version.load(scene, filename)
        else:
            self.version = Version_1_0()
            self.scene = scene

    def save(self, filename):
        self.version.save(self.scene, filename)


class VersionAbstract(object):
    __metaclass__ = ABCMeta

    def __init__(self):
        pass

    @abstractmethod
    def check_version(self, filename):
        return False

    @abstractmethod
    def get_version(self):
        return "Abstract version"

    @abstractmethod
    def load(self, scene, filename):
        logging.debug("This is abstract version class load function")
        return False

    @abstractmethod
    def save(self, scene, filename):
        logging.debug("This is abstract version class save function")
        return False


class Version_1_0(VersionAbstract):

    def __init__(self):
        self.xmlFilename = 'scene.xml'

    def check_version(self, filename):
        return True

    def get_version(self):
        return "1.0"

    def load(self, scene, filename):
        #open zipfile
        with ZipFile(filename, 'r') as openedZipfile:
            tree = ET.fromstring(openedZipfile.read(self.xmlFilename))
            version = tree.find('version').text
            if self.get_version() == version:
                logging.debug("Ano, soubor je stejna verze jako knihovna pro jeho nacitani. Pokracujeme")
            else:
                logging.debug("Problem, tuto verzi neumim nacitat.")
                return False
            models = tree.find('models')
            models_data = []
            for model in models.findall('model'):
                model_data = {}
                model_data['file_name'] = model.get('name')
                if model.find('extruder'):
                    print("je tam extruder")
                    model_data['extruder'] = ast.literal_eval(model.find('extruder').text)
                if model.find('group'):
                    print("je tam group")
                    model_data['group'] = ast.literal_eval(model.find('group').text)
                model_data['normalization'] = ast.literal_eval(model.find('normalization').text)
                model_data['position'] = ast.literal_eval(model.find('position').text)
                model_data['rotation'] = ast.literal_eval(model.find('rotation').text)
                model_data['scale'] = ast.literal_eval(model.find('scale').text)
                models_data.append(model_data)

            #scene.models = []
            models_groups = {}
            groups_properties = {}
            for m in models_data:
                print(str(m))
                logging.debug("Jmeno souboru je: " + m['file_name'])

                tmp = scene.controller.app_config.tmp_place
                model_filename = tmp + m['file_name']
                openedZipfile.extract(m['file_name'], tmp)

                mesh = Mesh.from_file(filename=model_filename)
                os.remove(model_filename)

                #mesh = Mesh.from_file(filename="", fh=openedZipfile.open(m['file_name']))
                if 'group' in m:
                    model = ModelTypeStl.load_from_mesh(mesh, filename=m['file_name'], normalize=not m['normalization'])
                else:
                    model = ModelTypeStl.load_from_mesh(mesh, filename=m['file_name'], normalize=not m['normalization'])
                if 'extruder' in m:
                    model.extruder = int(m['extruder'])

                if 'group' in m:
                    print("group")
                    model.is_multipart_model = True
                    if m['group'] in models_groups:
                        models_groups[m['group']].append(model)
                    else:
                        models_groups[m['group']] = []
                        models_groups[m['group']].append(model)

                    groups_properties[m['group']]['pos'] = numpy.array(m['position'])
                    groups_properties[m['group']]['rot'] = numpy.array(m['rotation']) *0.1
                    groups_properties[m['group']]['scale'] = numpy.array(m['scale'])

                else:
                    print("ne group")
                    model.rot = numpy.array(m['rotation'])
                    model.pos = numpy.array(m['position'])
                    model.pos *= 0.1
                    model.scale = numpy.array(m['scale'])
                    model.update_min_max()
                    model.parent = scene

                scene.models.append(model)

            for group in models_groups:
                print("Vytvarim multimodel")
                print("List modelu: " +str(models_groups[group]))

                mm = MultiModel(models_groups[group], scene)
                mm.pos = groups_properties[group]['pos']
                mm.rot = groups_properties[group]['rot']
                mm.scale = groups_properties[group]['scale']
                scene.multipart_models.append(mm)



    def save(self, scene, filename):
        printing_space =  scene.controller.printing_parameters.get_printer_parameters(scene.controller.actual_printer)
        zero = numpy.array(printing_space['printing_space'], dtype=float)
        zero *= -0.5
        zero[2] = 0.
        #print(str(zero))
        #create zipfile
        with ZipFile(filename, 'w', ZIP_DEFLATED) as zip_fh:
            #create xml file describing scene
            root = ET.Element("scene")
            ET.SubElement(root, "version").text=self.get_version()
            ET.SubElement(root, "zero").text = str(zero.tolist())
            models_tag = ET.SubElement(root, "models")


            for model in scene.models:
                if model.isVisible and not model.is_wipe_tower:
                    if model.is_multipart_model:
                        model_tmp = model.multipart_parent
                        pos = deepcopy(model.pos)
                        pos += model_tmp.pos
                        pos *= 10.
                        model_element = ET.SubElement(models_tag, "model", name=model.filename)
                        ET.SubElement(model_element, "extruder").text = str(model.extruder)
                        if model.is_multipart_model:
                            ET.SubElement(model_element, "group").text = str(model.multipart_parent.group_id)
                        ET.SubElement(model_element, "normalization").text = str(model.normalization_flag)
                        ET.SubElement(model_element, "position").text = str(pos.tolist())
                        ET.SubElement(model_element, "rotation").text = str(model_tmp.rot.tolist())
                        ET.SubElement(model_element, "scale").text = str(model_tmp.scale.tolist())
                    else:
                        pos = model.pos*10.
                        model_element = ET.SubElement(models_tag, "model", name=model.filename)
                        ET.SubElement(model_element, "extruder").text = str(model.extruder)
                        if model.is_multipart_model:
                            ET.SubElement(model_element, "group").text = str(model.multipart_parent.group_id)
                        ET.SubElement(model_element, "normalization").text = str(model.normalization_flag)
                        ET.SubElement(model_element, "position").text = str(pos.tolist())
                        ET.SubElement(model_element, "rotation").text = str(model.rot.tolist())
                        ET.SubElement(model_element, "scale").text = str(model.scale.tolist())


            #save xml file to new created zip file
            newXml = ET.tostring(root)
            zip_fh.writestr(self.xmlFilename, newXml)

            #write stl files to zip file
            for model in scene.models:
                if model.isVisible and not model.is_wipe_tower:
                    #transform data to stl file
                    mesh = model.get_mesh(False, False)

                    model_filename = scene.controller.app_config.tmp_place + model.filename
                    mesh.save(model_filename, mode=stl.Mode.BINARY, update_normals=False)
                    zip_fh.write(model_filename, model.filename)
                    os.remove(model_filename)

        return True


