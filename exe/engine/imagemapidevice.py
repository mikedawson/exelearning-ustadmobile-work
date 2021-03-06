'''
Created on Jan 29, 2014

@author: mike
'''

import logging
from exe.engine.idevice import Idevice
from exe.engine.field   import TextAreaField
from exe.engine.field   import ImageField
from exe.engine.field   import TextField
from exe.engine.path      import Path, toUnicode
from exe.engine.resource  import Resource
from exe.engine.extendedfieldengine import *

log = logging.getLogger(__name__)


# ===========================================================================
class ImageMapIdevice(Idevice):
    
    persistenceVersion = 5
    
    def __init__(self, content=""):
        Idevice.__init__(self, x_(u"Image Map"), 
             x_(u"Mike Dawson, Ustad Mobile"), 
             x_(u"""Image Map Idevice with tooltips, sound support."""), 
             "", "")
        self.emphasis = Idevice.SomeEmphasis
        self.message = ""
        
        mainFieldOrder = ["title", "instructions", "mapImg"]
        mainFieldsInfo = \
            {'title' : ['text', x_('Title'), x_('Title'),
                        {"default_prompt" : x_("Type your title here")}],
             'instructions' : ['textarea', x_('Instructions to show'), 
                               x_('Instructions'), 
                               {"default_prompt" : """Enter instructions
                                for the students here; e.g. click on the
                                areas below for more information to
                                 popup"""}],
             'mapImg' : ['image', x_('Image'), x_('Use for map background'),
                         {"defaultval" : "imagemap_defaultbg.png" } ]
             }
        
        self.mainFieldSet = ExtendedFieldSet(self, mainFieldOrder, mainFieldsInfo)
        self.mainFieldSet.makeFields()
        
        #The areas with coordinates
        self.map_areas = []
        
        self.add_map_area(num_areas_to_add=2)
        
        #use the new system_scripts method
        self.system_scripts = ["imagemapidevice.js", \
                                    "jquery.tooltipster.js",
                                    "tooltipster.css",
                                    "jquery.rwdImageMaps.js"]
        
    """
    Get the scripts that we need 
    """
    def uploadNeededScripts(self):
        pass
        
    def add_map_area(self, num_areas_to_add = 1):
        default_width = 100
        for count in range(0, num_areas_to_add):
            base_coord = (count * 100)+10
            coords = "%(b)s,%(b)s,%(x)s,%(x)s" % {'b' : str(base_coord),
                                          'x' : str(base_coord+100)}
            self.map_areas.append(ImageMapAreaField(self,coords=coords))
        
    def get_img_filename(self):
        """Return the filename of the image we use for area map, None if no image loaded
        """
        if self.mainFieldSet.fields['mapImg'].imageResource:
            return self.mainFieldSet.fields['mapImg'].imageResource.storageName
        else:
            return None
        
    def upgradeToVersion2(self):
        pass
    
    def upgradeToVersion3(self):
        """V3: Updated script and rendering here"""
        self.uploadNeededScripts()
    
    def upgradeToVersion4(self):
        self.system_scripts = ["imagemapidevice.js", \
                                    "jquery.imagemapster.js"] 
        
    def upgradeToVersion5(self):
        """move away from imagemapster due to bug using
        it with XHTML"""
        self.system_scripts = ["imagemapidevice.js", \
                                    "jquery.tooltipster.js",
                                    "tooltipster.css",
                                    "jquery.rwdImageMaps.js"]
   
class ImageMapAreaField(Field):
    
    persistenceVersion = 3
    
    def __init__(self, idevice, coords=""):
        Field.__init__(self, x_("Image Map Area"), x_("Image Map Area"))
        self.idevice = idevice
        
        main_field_order = ["tooltip", "activateon", "shape", "coords"]
        main_field_info = {\
           'tooltip' : ['textarea', x_('Popup tooltip'), x_('Popup tooltip'),
                        {"default_prompt" : """Enter the popup that 
                        will appear when the user clicks or hovers
                         over this area.  If you add a sound by 
                         using insert media it will play too."""}],\
           'shape' : ['choice', x_('Area Shape'), x_('Area Shape'),\
                                {'choices' : [['rect', x_('Rectangle')] ] }],\
           'activateon' : ['choice', x_('Activate When'), x_('Activate When'),\
                            {'choices' : [['click', x_("Only when user clicks or taps the area")],
                                          ['hover click', x_("User clicks, taps, or mouse hovers over area")]]
                                          } ],
           'coords' : ['text', "Coordinates", "Coordinates",
                       {"defaultval" : coords}]\
                       }
        
        self.main_fields = ExtendedFieldSet(self.idevice, \
                            main_field_order, main_field_info)
        
    def upgradeToVersion2(self):
        self.main_fields.fieldOrder = ["tooltip", "activateon", "shape", "coords"]
        self.main_fields.fieldInfoDict['activateon'] = ['choice', x_('Activate When'), x_('Activate When'),\
                            {'choices' : [['click', x_("Only when user clicks or taps the area")],
                                          ['hover click', x_("User clicks, taps, or mouse hovers over area")]],
                             'defaultVal' : 'hover click'} ]
        self.main_fields.makeFields()
        self.main_fields.fields['activateon'].content = "hover click"
        
    def upgradeToVersion3(self):
        self.main_fields.fields['activateon'].content = "click"
        