# -- coding: utf-8 --
# ===========================================================================
# eXe
# Copyright 2013, Pedro Peña Pérez, Open Phoenix IT
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
# ===========================================================================

import sys
import os
from exe.engine.path import Path
from exe.engine.config import Config
from exe                         import globals as G


class LocationButtons(object):
    def __init__(self):
        if G.application.config and G.application.config.appMode == Config.MODE_WEBAPP:
            self.names_map = {}
        elif sys.platform[:3] == "win":
            self.names_map = {0: x_('Desktop'),
                         5: x_('Documents'),
                         40: x_('Home Folder')}
        elif sys.platform[:6] == "darwin":
            self.names_map = {'kDesktopFolderType': x_('Desktop'),
                         'kDocumentsFolderType': x_('Documents'),
                         'kCurrentUserFolderType': x_('Home Folder')}
        else:
            self.names_map = {'DESKTOP': x_('Desktop'),
                         'DOCUMENTS': x_('Documents'),
                         'HOME': x_('Home Folder')}
            
            self.icon_map = {'DESKTOP':'/images/stock-open.png',    #Added
                         'DOCUMENTS': '/images/stock-panel-drawer.png',
                         'HOME': '/images/stock-open.png'}
        self.compute()
        
        
        
    def get_user_doc_path(self):
        for button in self.buttons:
            if button['text'] == self._get_button_text('Documents'):
                return button['location']
        
        #default to the middle button
        return self.buttons[0]['location']
            
    def _get_button_text(self, value):
        button_text = value
        try:
            button_text = _(value)
        except:
            #in bootup - care not
            pass
        
        return button_text
        
    def compute(self):
        self.buttons = []
        for key, value in self.names_map.items():
            #key is HOME DOCUMENTS DESKTOP
            try:
                button_text = self._get_button_text(value)
                
                button = {'xtype': 'button', 'text': button_text,
                          'icon': '/images/stock-open.png', #Added
                          #Ideally it should be:
                          #'icon': ,
                          'location': self.MapDir(key)}
                self.buttons.append(button)
            except:
                pass

    def updateText(self):
        i = 0
        for value in self.names_map.values():
            
            button = self.buttons[i]
            button['text'] = _(value)
            i = i + 1

    def MapDir(self, code):
        if sys.platform[:3] == "win":
            try:
                from ctypes import WinDLL, create_unicode_buffer
                dll = WinDLL('shell32')
                result = create_unicode_buffer(260)
                resource = dll.SHGetFolderPathW(None, code, None, 0, result)
                if resource != 0:
                    raise Exception
                else:
                    path = result.value
            except:
                if code == 0:
                    path = os.environ['HOMEPATH']
                else:
                    raise
        elif sys.platform[:6] == "darwin":
            try:
                from Carbon import Folder, Folders
                folderref = Folder.FSFindFolder(Folders.kUserDomain,
                    getattr(Folders, code), False)
                path = folderref.as_pathname()
            except:
                if code == 'kCurrentUserFolderType':
                    path = os.environ['HOME']
                else:
                    raise
        else:
            try:
                XDG_USER_DIR_CMD = 'xdg-user-dir'
                import subprocess
                p = subprocess.Popen([XDG_USER_DIR_CMD, code],
                                     stdout=subprocess.PIPE)
                path, _ = p.communicate()
                path = path.rstrip('\n')
            except:
                if code == 'HOME':
                    path = os.environ['HOME']
                else:
                    raise
        return Path(path).abspath()
