#!/usr/bin/env python
#-*- coding: utf-8 -*-
# ===========================================================================
# eXe 
# Copyright 2004-2006, University of Auckland
# Copyright 2004-2008 eXe Project, http://eXeLearning.org/
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

"""
This unit provides a base class for something that is rendered, this can be
a page, a pane, a block, even part of JSUI like the outlinePane but not really
going down to the element level. We'll call them rendering components.

It provides a way to get at your parent rendering component, the top being the
mainpage, who has no parent. It also provides you with a config instance and
a package instance.  Finally it makes you a LivePage and a Resource descendant,
but you don't have to use that functionality. It means you can use a rendering
template to do your rendering, even if you're part of a bigger block.
"""

from twisted.web.resource import Resource
from nevow import loaders
from twisted.web import static
from nevow.i18n import render as render_i18n
from datetime import datetime
import email.utils as eut
import time
from exe.engine.path             import Path

import logging
log = logging.getLogger(__name__)
import re

# Constants
# This constant is used as a special variable like None but this means that an
# attribute is Unset it tells __getattribute__ that it needs to really return
# this value.  We do all this complicated stuff to stop pylint complaining about
# our magically gotten variables.
Unset = object()
# This is a constant that means, we don't have an attribute of this name
DontHave = object()

class Renderable(object):
    """
    A base class for all things rendered
    """

    # Set this to a template filename if you are use a template page to do 
    # your rendering
    _templateFileName = ''
    name = None # Must provide a name in dervied classes, or pass one to
    #__init__

    # Default attribute values
    docFactory = None

    # Translates messages in templates with nevow:render="i18n" attrib
    render_i18n = render_i18n()

    def __init__(self, parent, package=None, webServer=None, name=None):
        """
        Pass me a 'parent' rendering component,
        a 'package' that I'm rendering for
        and a 'webServer' instance reference (from webServer.py)
        If you don't pass 'webServer' and 'package' I'll
        get them from 'parent'
        'name' is a identifier to distuniguish us from the other children of our
        parent
        """
        self.parent = parent # This is the same for both blocks and pages
        if name:
            self.name = name
        elif not self.name:
            raise AssertionError('Element of class "%s" created with no name.' %
                                 self.__class__.__name__)
            
        # Make pylint happy. These attributes will be gotten from
        # self.application
        self.config = Unset
        self.ideviceStore = Unset

        # Overwrite old instances with same name
        if parent:
            parent.renderChildren[self.name] = self
        self.renderChildren = {}
        if package:
            self.package = package
        elif parent:
            self.package = parent.package
        else:
            self.package = None
        if webServer:
            self.webServer = webServer
        elif parent:
            self.webServer = parent.webServer
        else:
            self.webServer = None
        if self._templateFileName:
            if hasattr(self, 'config') and self.config:
                pth = self.config.webDir/'templates'/self._templateFileName
                self.docFactory = loaders.xmlfile(pth)
            else:
                # Assume directory is included in the filename
                self.docFactory = loaders.xmlfile(self._templateFileName)

    # Properties
    def getRoot(self):
        """
        Returns the highest renderable in the tree
        that doesn't have a parent.
        Basically 'PackageRedirector'
        """
        renderable = self
        while renderable.parent:
            renderable = renderable.parent
        return renderable
    root = property(getRoot)

    def delete(self):
        """
        Removes our self from our parents tree
        """
        del self.parent.renderChildren[self.name]

    def __getattribute__(self, attr):
        """
        Sets unset attributes.
        """
        def baseget(name):
            """
            Gets values the old proper way
            but instead of raising AttributeErro
            returns the constant 'DontHave'
            """
            try:
                return object.__getattribute__(self, name)
            except AttributeError:
                return DontHave
        res = baseget(attr)
        if res is Unset or res is DontHave:
            if attr.startswith('render_'):
                name = attr.split('_', 1)[-1]
                res = baseget('renderChildren')[name].render
            elif baseget('webServer'):
                # If not, see if what they're looking for is in the app object
                res = getattr(baseget('webServer').application, attr)
            setattr(self, attr, res)
        return res


    def process(self, request):
        """
        Called when a request comes in.
        This implementation automatically
        passes on the request to all our
        child renderables
        """
        # Pass the request on to each rendering component
        # child that is not a separate page in itself
        for rc in self.renderChildren.values():
            if not isinstance(rc, _RenderablePage):
                # Only sub pages need to have process passed to them
                rc.process(request)


class _RenderablePage(Renderable):
    """
    For internal use only
    """
    def __init__(self, parent, package=None, config=None):
        """
        Same as Renderable.__init__ but uses putChild to put ourselves
        in our parents sub-page tree
        """
        Renderable.__init__(self, parent, package, config)
        if parent:
            self.parent.putChild(self.name, self)


class RenderableResource(_RenderablePage, Resource):
    """
    It is a page and renderable, but not live
    """
    
    
    

    def __init__(self, parent, package=None, config=None):
        """
        See Renderable.__init__ docstring
        """
        Resource.__init__(self)
        _RenderablePage.__init__(self, parent, package, config)

    def render(self, request):
        "Disable cache of renderable resources"
        request.setHeader('Expires', 'Fri, 25 Nov 1966 08:22:00 EST')
        request.setHeader("Cache-Control", "no-store, no-cache, must-revalidate")
        request.setHeader("Pragma", "no-cache")
        request.setHeader("X-XSS-Protection", "0")
        return Resource.render(self, request)

class File(static.File):
    
    """
    Dictionary of regular expressions to cache info mapped 
    as regular expression object to HTTP headers dictionary
    """
    cache_headers = []
    
    @classmethod
    def append_regex_headerset(cls, regex_str, headerset):
        """
        Append to our cache_headers list for the list
        regex_str : str
            Regular expression to be matched for sending this headerset
        headerset : dict
            Dictionary in the form of Header-name : Value
        """
        cls.cache_headers.append([re.compile(regex_str), headerset])
    
    @classmethod
    def get_cache_headers_by_path(cls, uri):
        """
        Return the HTTP caching headers to use according to the
        URI using cache_headers
        
        Parameters
        ----------
        uri : str
            The request path to find headers for
        """
        for regex_arr in cls.cache_headers:
            regex = regex_arr[0]
            if regex.match(uri):
                return regex_arr[1]
        
        return None
    
    def render(self, request):
        """Send a static file
        """
        
        cache_info = File.get_cache_headers_by_path(request.path)
        
        if cache_info is None:
            cache_info = {}
        
        
        if "Expires" not in cache_info:
            request.setHeader('Expires', 'Fri, 25 Nov 1966 08:22:00 EST')
        elif "Expires" in cache_info and cache_info["Expires"] != "":
            request.setHeader('Expires', cache_info["expires"])
       
        if "Cache-Control" not in cache_info:
            request.setHeader("Cache-Control", "no-store, no-cache, must-revalidate")
        elif "Cache-Control" in cache_info and cache_info["Cache-Control"] != "":
            request.setHeader("Cache-Control", cache_info["Cache-Control"])
        
        if "Pragma" not in cache_info and "Cache-Control" not in cache_info:
            request.setHeader("Pragma", "no-cache")
        elif "Pragma" in cache_info and cache_info['Pragma'] != "": 
            request.setHeader("Pragma", cache_info['Pragma'])
        
        etag_checked = False
        if "ETag" in cache_info:
            md5sum = Path(self.path).md5
            etag_checked = True
            
            etag_matched = False
            if "if-none-match" in request.received_headers:
                if md5sum == request.received_headers['if-none-match']:
                    etag_matched = True
            
            if etag_matched is True:
                request.setResponseCode(304)
                return ""
            else:
                request.received_headers.pop("if-modified-since", None)
                request.setHeader("ETag", md5sum)
        
        if "if-modified-since" in request.received_headers and etag_checked is False:
            #client_date_str = request.received_headers['if-modified-since']
            
            #client_utime = time.mktime(client_time.timetuple())
            file_mod_time = self.getmtime()
            client_date_str = request.received_headers['if-modified-since']
            time_tpl = eut.parsedate(client_date_str)
            client_mtime = time.mktime(time_tpl)
            
            #mktime is always local time - bring it back to GMT by  
            # taking out timezone modifier
            client_mtime -= time.timezone
            
            if not file_mod_time > client_mtime:
                request.setResponseCode(304)
                return ""
        
        
            
        return static.File.render(self, request)
