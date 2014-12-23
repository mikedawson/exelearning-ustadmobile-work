# -- coding: utf-8 --
# ===========================================================================
# eXe
# Copyright 2012, Pedro Peña Pérez, Open Phoenix IT
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
from exe.webui.webservice.exebackendservice import EXEBackEndService

"""
This is the main Javascript page.
"""

import os
import json
import sys
import logging
import traceback
import shutil
import tempfile

import urllib
import urllib2
import cookielib
from multipartposthandler import MultipartPostHandler
import base64
import time
from exe.export.wtkpreviewthread import WTKPreviewThread


from exe.engine.version import release, revision
from twisted.internet            import threads, reactor
from exe.webui.livepage          import RenderableLivePage,\
    otherSessionPackageClients, allSessionClients, allSessionPackageClients
from nevow                       import loaders, inevow, tags
from nevow.livepage              import handler, IClientHandle
from exe.jsui.idevicepane        import IdevicePane
from exe.jsui.outlinepane        import OutlinePane
from exe.jsui.recentmenu         import RecentMenu
from exe.jsui.stylemenu          import StyleMenu
from exe.jsui.propertiespage     import PropertiesPage
from exe.webui.authoringpage     import AuthoringPage
from exe.webui.renderable        import File
from exe.export.websiteexport    import WebsiteExport
from exe.export.textexport       import TextExport
from exe.export.singlepageexport import SinglePageExport
from exe.export.scormexport      import ScormExport
from exe.export.imsexport        import IMSExport
from exe.export.xliffexport      import XliffExport
from exe.importers.xliffimport   import XliffImport
from exe.importers.scanresources import Resources
from exe.engine.path             import Path, toUnicode, TempDirPath
from exe.engine.package          import Package
from exe                         import globals as G
from exe.engine.config import Config
from tempfile                    import mkdtemp
from exe.engine.mimetex          import compile
from urllib                      import unquote, urlretrieve
from exe.engine.locationbuttons import LocationButtons
from exe.export.epub3export import Epub3Export
from exe.export.xmlexport import XMLExport

from exe.engine.lom import lomsubs
from exe.engine.lom.lomclassification import Classification
import zipfile
import copy

log = logging.getLogger(__name__)


class MainPage(RenderableLivePage):
    """
    This is the main Javascript page.  Responsible for handling URLs.
    """
    
    _templateFileName = 'mainpage.html'
    name = 'to_be_defined'

    def __init__(self, parent, package, session, config):
        """
        Initialize a new Javascript page
        'package' is the package that we look after
        """
        self.name = package.name
        self.session = session
        RenderableLivePage.__init__(self, parent, package, config)
        self.putChild("resources", File(package.resourceDir))
		#styles directory
        #self.putChild("stylecss", File(self.config.stylesDir)
        
        mainjs = Path(self.config.jsDir).joinpath('templates', 'mainpage.html')
        self.docFactory  = loaders.htmlfile(mainjs)

        # Create all the children on the left
        self.outlinePane = OutlinePane(self)
        self.idevicePane = IdevicePane(self)
        self.styleMenu   = StyleMenu(self)
        self.recentMenu  = RecentMenu(self)

        # And in the main section
        self.propertiesPage = PropertiesPage(self)
        self.authoringPage = None
        self.previewDir = None
        self.authoringPages = {}
        self.classificationSources = {}

        G.application.resourceDir=Path(package.resourceDir);

        self.location_buttons = LocationButtons()
        self.exportDownloadPage = None
        
        self.handlers_name_to_fns = {}
        
        #change default timeouts to 15mins
        #time in secs = poll time * targetTimeoutCount
        self.targetTimeoutCount = 30


    def adjust_config_for_user(self):
        if G.application.config.appMode == Config.MODE_WEBAPP:
            import copy
            new_config = copy.copy(self.config)
            x = 0 

    def child_authoring_linklist(self, ctx):
        return json.dumps(self.package.get_internal_links())

    def child_authoring(self, ctx):
        """Returns the authoring page that corresponds to the url http://127.0.0.1:port/package_name/authoring"""
        request = inevow.IRequest(ctx)
        if 'clientHandleId' in request.args:
            clientid = request.args['clientHandleId'][0]
            if clientid not in self.authoringPages:
                self.authoringPages[clientid] = AuthoringPage(self)
                self.children.pop('authoring')
            return self.authoringPages[clientid]
        else:
            raise Exception('No clientHandleId in request')

    def child_preview(self, ctx):
        if not self.package.previewDir:
            stylesDir = self.config.stylesDir / self.package.style
            self.package.previewDir = TempDirPath()
            self.exportWebSite(None, self.package.previewDir, stylesDir)
            self.previewPage = File(self.package.previewDir / self.package.name)
        return self.previewPage
    
    def child_export_files(self, ctx):
        if not hasattr(self.package, "export_download_dir"):
            self.package.export_download_dir = None
        
        if not self.package.export_download_dir:
            self.package.export_download_dir = TempDirPath()
        
        if not self.exportDownloadPage:    
            self.exportDownloadPage = File(self.package.export_download_dir)
            
        return self.exportDownloadPage
    
    def child_previewmobile(self,ctx):
        """Render smartphone preview (UstadMobile)"""
        """
        
        NOTE: This should be using a separate directory to avoid
        interference
        
        if not hasattr(self.package, "previewMobileDir"):
            self.package.previewMobileDir = None
            if not 'previewMobileDir' in self.package.nonpersistant:
                self.package.nonpersistant.append('previewMobileDir')
        
        if not self.package.previewMobileDir:
            stylesDir = self.config.stylesDir / self.package.style
            self.package.previewMobileDir = TempDirPath()
            self.exportXML(None, self.package.previewMobileDir, stylesDir)
            self.previewPage = File(self.package.previewMobileDir / self.package.name)
        """
        
        if not self.package.previewDir:
            stylesDir = self.config.stylesDir / self.package.style
            self.package.previewDir = TempDirPath()
            self.exportXML(None, self.package.previewDir, stylesDir, 
                           preview_mode = True)
            self.previewPage = File(self.package.previewDir /"EPUB")
        
        return self.previewPage
    
    def child_readability_stats(self, ctx):
        result = {'level' : 'impossible'}
        from exe.engine.readabilityutil import ReadabilityUtil
        stat = ReadabilityUtil({}).get_package_readability_info(
                                                        self.package)
        return json.dumps(stat)


    def child_taxon(self, ctx):
        """
        Doc
        """
        request = inevow.IRequest(ctx)
        data = []
        if 'source' in request.args:
            if 'identifier' in request.args:
                source = request.args['source'][0]
                if source:
                    if not source in self.classificationSources:

                        self.classificationSources[source] = Classification()
                        try:
                            self.classificationSources[source].setSource(source, self.config.configDir)
                        except:
                            pass
                    identifier = request.args['identifier'][0]
                    if identifier == 'false':
                        identifier = False
                    if source.startswith("etb-lre_mec-ccaa"):
                        stype = 2
                    else:
                        stype = 1
                    try:
                        data = self.classificationSources[source].getDataByIdentifier(identifier, stype=stype)
                    except:
                        pass

        return json.dumps({'success': True, 'data': data})

    """
    def locateHandler(self, ctx, path, name):
        ### XXX TODO: Handle path
        if name in self.handlers_name_to_fns:
            return self.handlers_name_to_fns[name]
        else:
            return getattr(self, 'handle_%s' % (name, ))"""

    def locateHandler(self, ctx, path, name):
        ### XXX TODO: Handle path
        """
        if hasattr(self, 'handle_%s' % (name, )):
            return getattr(self, 'handle_%s' % (name, ))
        else:
            #adapt the naming convention
            name_adapted = name[0].upper() + name[1:]
            return getattr(self, "handle" + name_adapted)
        """
        if name in self.handlers_name_to_fns:
            return self.handlers_name_to_fns[name]
        
    def handleCloseFinalizer(self, client, callback = None):
        if callback:
            return _js(callback)

    def goingLive(self, ctx, client):
        """Called each time the page is served/refreshed"""
        
        #there is an instance of this for every client - might as well
        #keep the client handle available
        self.exeClientHandle = client
        
#        inevow.IRequest(ctx).setHeader('content-type', 'application/vnd.mozilla.xul+xml')
        # Set up named server side funcs that js can call
        def setUpHandler(func, name, *args, **kwargs):
            """
            Convience function link funcs to hander ids
            and store them
            """
            kwargs['identifier'] = name
            #hndlr = handler(func, *args, **kwargs)
            #hndlr(ctx, client) # Stores it
            self.handlers_name_to_fns[name] = CallableInstanceMethod(func, client)
            
        setUpHandler(self.handleCloseFinalizer, "close")
        setUpHandler(self.handle_ping, "ping")   
        setUpHandler(self.handle_foobar, "foobar")    
        setUpHandler(self.handleIsPackageDirty,  'isPackageDirty')
        setUpHandler(self.handlePackageFileName, 'getPackageFileName')
        setUpHandler(self.handleSavePackage,     'savePackage')
        setUpHandler(self.handleLoadPackage,     'loadPackage')
        setUpHandler(self.recentMenu.handleLoadRecent,      'loadRecent')
        setUpHandler(self.handleLoadTutorial,    'loadTutorial')
        setUpHandler(self.recentMenu.handleClearRecent,     'clearRecent')
        setUpHandler(self.handleImport,          'importPackage')
        setUpHandler(self.handleCancelImport,    'cancelImportPackage')
        setUpHandler(self.handleExport,          'exportPackage')
        setUpHandler(self.handleXliffExport,     'exportXliffPackage')
        setUpHandler(self.handleQuit,            'quit')
        setUpHandler(self.handleBrowseURL,       'browseURL')
        setUpHandler(self.handleMergeXliffPackage,   'mergeXliffPackage')
        setUpHandler(self.handleInsertPackage,   'insertPackage')
        setUpHandler(self.handleExtractPackage,  'extractPackage')
        setUpHandler(self.outlinePane.handleSetTreeSelection,  
                                                 'setTreeSelection')
        setUpHandler(self.handleClearAndMakeTempPrintDir,
                                                 'makeTempPrintDir')
        setUpHandler(self.handleRemoveTempDir,   'removeTempDir')
        setUpHandler(self.handleTinyMCEimageChoice,   'previewTinyMCEimage')
        setUpHandler(self.handleTinyMCEmath,     'generateTinyMCEmath')
        setUpHandler(self.handleTestPrintMsg,    'testPrintMessage')
        setUpHandler(self.handleReload,       'reload')
        setUpHandler(self.handleSourcesDownload, 'sourcesDownload')
        
        


        #For the new ExtJS 4.0 interface
        setUpHandler(self.outlinePane.handleAddChild, 'AddChild')
        setUpHandler(self.outlinePane.handleDelNode, 'DelNode')
        setUpHandler(self.outlinePane.handleRenNode, 'RenNode')
        setUpHandler(self.outlinePane.handlePromote, 'PromoteNode')
        setUpHandler(self.outlinePane.handleDemote, 'DemoteNode')
        setUpHandler(self.outlinePane.handleUp, 'UpNode')
        setUpHandler(self.outlinePane.handleDown, 'DownNode')
        setUpHandler(self.handleCreateDir, 'CreateDir')
        
        #For Enhanced Usability
        setUpHandler(self.startUSBExport,        'exportPackageToUSB')
        setUpHandler(self.setPackageTitle,        'setPackageTitle')

        #umcloud functions
        setUpHandler(self.handleUMUploadFileName, 'startUMUploadFileName')  
        setUpHandler(self.handleCheckUMCloudLogin, 'checkUMCloudLogin')  
        setUpHandler(self.handleAutoSavePackage,     'autoSavePackage') 
        
        #for j2me preview with Ustad Mobile
        setUpHandler(self.previewFeaturePhone, "previewFeaturePhone")
        
        #for saving readability boundaries
        setUpHandler(self.handleReadabilityBoundariesExport, 
                     "readabilityBoundariesExport")
        
        setUpHandler(self.handleReadabilityBoundariesImport,
                     "readabilityBoundariesImport")
        
        setUpHandler(self.handleLoadWebUserConfig,
                     "loadWebUserConfig")

        self.idevicePane.client = client
        self.styleMenu.client = client
        self.webServer.stylemanager.client = client
        

        if not self.webServer.monitoring:
            self.webServer.monitoring = True
            self.webServer.monitor()

    def previewFeaturePhone(self, client):
        canRunWTK = WTKPreviewThread.canRunWTK() 
        if canRunWTK:
            self._startWTKPreview()
        else:
            client.alert(_("""
            Sorry! It seems like your system is not setup for Feature Phone Preview.  
            You need to install Java and Java 2 Micro Edition WTK.  For help go to
            www.ustadmobile.com"""))

    def handleReadabilityBoundariesExport(self, client, path, boundaries_obj_str):
        """
        Export readability boundaries to a JSON file
        """
        if path.startswith("__base__"):
            import re
            import os
            basepath = G.application.config.readabilityPresetsDir + os.path.sep
            path = re.sub("__base__", basepath, path)
        
        if path.endswith(".erb") is False:
            path += ".erb"
            
        out_file = open(path, "wb")
        out_file.write(boundaries_obj_str)
        out_file.flush()
        out_file.close()
        client.alert(_("Saved Preset"))
        
    def handleReadabilityBoundariesImport(self, client, path):
        """
        Handle when the user has selected a new set of boundaries
        to import 
        """
        
        if path.startswith("__base__"):
            import re
            import os
            basepath = G.application.config.readabilityPresetsDir + os.path.sep
            path = re.sub("__base__", basepath, path)
        
        in_file = open(path)
        in_contents = in_file.read()
        in_file.close()
        
        import os
        basename = os.path.basename(path)
        if basename[-4:] == ".erb":
            basename = basename[0:len(basename)-4]
        
        if in_contents.find("'") != -1:
            raise ValueError("single quote ' not allowed in readability boundaries")
        
        client.sendScript(
              "eXeReadabilityHelper.importReadabilityBoundariesShow('"
              +basename + "','"
              +in_contents+"')")
    
    def get_current_webuser(self):
        return self.session.webservice_user

    def handleLoadWebUserConfig(self, client):
        """
        Load the configuration for this specific user using the
        backend.
        """
        self.config = EXEBackEndService.get_instance().adjust_config_for_user(
                               self.get_current_webuser(), self.config)
        self.session.webservice_config = self.config
        
        client.sendScript(
            'eXe.app.getController("Toolbar").updateAppConfig(%s)' % \
            json.dumps(self.get_config_dict()))

    def _startWTKPreview(self):
        if not self.package.previewDir:
            stylesDir = self.config.stylesDir / self.package.style
            self.package.previewDir = TempDirPath()
            self.exportXML(None, self.package.previewDir, stylesDir)
            self.previewPage = File(self.package.previewDir / self.package.name)
        
        self._startFileWTK(Path(self.package.previewDir / self.package.name))
                    
    # run the mobile emulator (j2me)
    def _startFileWTK(self, filename):
        wtkPreviewThread = WTKPreviewThread(filename, self.package.name)
        wtkPreviewThread.start()

    def get_config_dict(self, ctx = None):
        """
        Return a dict of configuration keys needed by the ExtJS app
        """
        myLastDir = self.config.lastDir
        if G.application.config.appMode != Config.MODE_DESKTOP:
            if self.session.webservice_config and self.session.webservice_config.lastDir:
                myLastDir =  self.session.webservice_config.lastDir
        
        config = {'lastDir': myLastDir,
                  'locationButtons': self.location_buttons.buttons,
                  'lang': G.application.config.locale.split('_')[0],
                  'showPreferences': G.application.config.showPreferencesOnStart == '1' and not G.application.preferencesShowed,
                  'loadErrors': G.application.loadErrors,
                  'showIdevicesGrouped': G.application.config.showIdevicesGrouped == '1',
                  'pathSep': os.path.sep,
                  'appMode' : G.application.config.appMode,
                  'authoringIFrameSrc' : '%s/authoring' % self.package.name
                 }
        #if ctx is not None:
            #clientHandleId = IClientHandle(ctx).handleId
            #upgrade to nevow attempt
        #    clientHandleId = "0"
            #config['authoringIFrameSrc'] = '%s/authoring?clientHandleId=%s' % \
            #    (self.package.name, clientHandleId)
        
        if G.application.config.appMode == "WEBAPP":
            if self.session.webservice_user is not None:
                config['webservice_user'] = self.session.webservice_user
            else:
                config['webservice_user'] = ""
                
        return config
    
    def handle_close(self, client, callback):
        client.close(callback)
    
    def handle_foobar(self, client, data=None):
        print "the meaning of life is 42"
        life = 42
        from nevow.livepage import _js as js
        client.send(js("alert('hello world')"))
    
        
        
        
    
    def render_config(self, ctx, data):
        """
        Render ExtJS configuration keys needed inside a script tag
        """
        config = self.get_config_dict(ctx)
        G.application.preferencesShowed = True
        G.application.loadErrors = []
        return tags.script(type="text/javascript")["var config = %s" % json.dumps(config)]

    def render_jsuilang(self, ctx, data):
        return ctx.tag(src="../jsui/i18n/" + unicode(G.application.config.locale) + ".js")

    def render_extjslang(self, ctx, data):
        return ctx.tag(src="../jsui/extjs/locale/ext-lang-" + unicode(G.application.config.locale) + ".js")

    def render_htmllang(self, ctx, data):
        lang = G.application.config.locale.replace('_', '-').split('@')[0]
        attribs = {'lang': unicode(lang), 'xml:lang': unicode(lang), 'xmlns': 'http://www.w3.org/1999/xhtml'}
        return ctx.tag(**attribs)

    def render_version(self, ctx, data):
        return [tags.p()["Version: %s" % release],tags.p()["Revision: %s" % revision]] 

    def handleTestPrintMsg(self, client, message): 
        """ 
        Prints a test message, and yup, that's all! 
        """ 
        print "Test Message: ", message, " [eol, eh!]"

    def handleIsPackageDirty(self, client, ifClean, ifDirty):
        """
        Called by js to know if the package is dirty or not.
        ifClean is JavaScript to be evaled on the client if the package has
        been changed 
        ifDirty is JavaScript to be evaled on the client if the package has not
        been changed
        """
        if self.package.isChanged:
            client.sendScript(ifDirty)
        else:
            #client.sendScript(ifClean)
            client.sendScript(ifClean)


    def handlePackageFileName(self, client, onDone, onDoneParam):
        """
        Calls the javascript func named by 'onDone' passing as the
        only parameter the filename of our package. If the package
        has never been saved or loaded, it passes an empty string
        'onDoneParam' will be passed to onDone as a param after the
        filename
        """
        client.call(onDone, unicode(self.package.filename), onDoneParam)

    def handleCheckUMCloudLogin (self, client, onDone, onDoneParam, filepath, username, password, url):   #Added
        """
        Testing file upload in Python..
        """
        
        print username
        print url
        credentials = {'username': username, 'password': password} #Can be used in params=credentials in the request.

        #Login for TINCAN Login
        cred = username + ":" + password
        encode = base64.b64encode(cred)
        encoded = "Basic " + encode
        headers = {'X-Experience-API-Version': '1.0.1', 'Authorization': encoded}
        #End of logic
        
        c = urllib.urlencode(credentials)
        
        req2 = urllib2.Request(url, c)
        try:
            response = urllib2.urlopen(req2)
        
            if (response.code == 403):
                client.alert("Error: Wrong username and password combination. Try again")
                #return "Error: Wrong username and password combination. Try again"
            elif (response.code == 200):
                client.alert("Your login was a success.")
                client.sendScript("Ext.getCmp('loginumcloudtwin').close()")
            elif (response.code == 500):
                client.alert("Error: Cannot connect to the server. Make sure the server is active and you have network access.")
                #Trigger something on the client..
                #I think nothing needs to be triggered.
            else:
                client.alert("Something went wrong. could not identify.")
                #Trigger something on the client..
        except urllib2.HTTPError, e:
            print (e.code)
            if (e.code == 403):
                client.alert("Error: Wrong username and password combination. Try again")
                #return "Error: Wrong username and password combination. Try again"
            elif (e.code == 200):
                client.alert("Your login was a success.")
                client.sendScript("Ext.getCmp('loginumcloudtwin').close()")
            elif (e.code == 500):
                client.alert("Error: Cannot connect to the server. Make sure the server is active and you have network access.")
                #Trigger something on the client..
                #I think nothing needs to be triggered.
            else:
                client.alert("Something went wrong. could not identify.")
                #Trigger something on the client..
     
    def handleAutoSavePackage(self, client, filename=None, onDone=None):    #Added
        """
        Save the current package
        'filename' is the filename to save the package to
        'onDone' will be evaled after saving instead or redirecting
        to the new location (in cases of package name changes).
        (This is used where the user goes file|open when their 
        package is changed and needs saving)
        """
        filename = Path(filename, 'utf-8')
        saveDir  = filename.dirname()
        if saveDir and not saveDir.isdir():
            client.alert(_(u'Cannot access directory named ') + unicode(saveDir) + _(u'. Please use ASCII names.'))
            return
        oldName = self.package.name
        # If the script is not passing a filename to us,
        # Then use the last filename that the package was loaded from/saved to
        if not filename:
            filename = self.package.filename
            assert filename, 'Somehow save was called without a filename on a package that has no default filename.'
        # Add the extension if its not already there and give message if not saved
        filename = self.b4save(client, filename, '.elp', _(u'SAVE FAILED!'))
        try:
            self.package.save(filename) # This can change the package name
        except Exception, e:
            client.alert(_('SAVE FAILED!\n%s') % str(e))
            raise
        # Tell the user and continue
        if onDone:
            buffer="blah" #Random
            #client.alert(_(u'Package saved to: %s') % filename, onDone)
            #Basically dont alert the customer of anything -VS
        elif self.package.name != oldName:
            # Redirect the client if the package name has changed
            self.webServer.root.putChild(self.package.name, self)
            log.info('Package saved, redirecting client to /%s' % self.package.name)
            #client.alert(_(u'Package saved to: %s') % filename, 'eXe.app.gotoUrl("/%s")' % self.package.name.encode('utf8'), \
            #            filter_func=otherSessionPackageClients)
            #Basically don't alert the customer of anything while auto saving -VS
        else:
            buffer="blah2"
            #client.alert(_(u'Package saved to: %s') % filename, filter_func=otherSessionPackageClients)
            #Basically don't alert the customer of anything while auto saving -VS




    def handleUMUploadFileName (self, client, onDone, onDoneParam, filepath, username, password, url):   #Added
        """
        Testing file upload in Python..
        """
        credentials = {'username': username, 'password': password} #Can be used in params=credentials in the request.

        #Login for TINCAN Login
        cred = username + ":" + password
        encode = base64.b64encode(cred)
        encoded = "Basic " + encode
        headers = {'X-Experience-API-Version': '1.0.1', 'Authorization': encoded}
        #End of logic
        
        
        files={'exeuploadelp': (filepath, open(filepath, 'rb'))}
        
        fields = [('username', username), ('password', password)]
        files2 = [('exeuploadelp', filepath, open(filepath, 'rb'))]
        
        
        """
        Example:
          import MultipartPostHandler, urllib2, cookielib
        
          cookies = cookielib.CookieJar()
          opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookies),
                                        MultipartPostHandler.MultipartPostHandler)
          params = { "username" : "bob", "password" : "riviera",
                     "file" : open("filename", "rb") }
          opener.open("http://wwww.bobsite.com/upload/", params)

        """
        
        cookies = cookielib.CookieJar()
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookies), 
                                      MultipartPostHandler.MultipartPostHandler)
        params = { 'username': username, 'password': password, 'exeuploadelp': open(filepath, 'rb')}
        
        
        
        try:
            response = opener.open(url, params)

            if (response.code == 403):
                client.alert("Error: Wrong username and password combination. Try again")
                
                #return "Error: Wrong username and password combination. Try again"
            elif (response.code == 200):
                courseid = response.info().getheader('courseid')
                coursename = response.info().getheader('coursename')
                
                #Trigger something on the client..
                client.sendScript("Ext.getCmp('loginumcloudpwin').close()")
                client.sendScript("Ext.getCmp('exportustadmobilepwin').close()")
                
                client.alert("Your course: " + coursename + " has uploaded. Course id: " + courseid )
            elif (response.code == 500):
                error = response.info().getheader('error')
                if (error == "Grunt test failed"):
                    client.alert("Server Error: Your course did not pass server tests. Your project uploaded but cannot be set as active")
                elif (error == "Exe export failed"):
                    client.alert("Server Error: Your course failed to finish exporting on the server. Your project uploaded but cannot be set as active.")
                elif (error == "Exe export failed to start"):
                    client.alert("Server Error: Your course failed to export on the server. Please get in touch.")
                elif (error == "Request is not POST"):
                    client.alert("eXe error: eXe failed to connect with the server by POST request")
                else:
                    client.alert("Error: Cannot connect to the server. Make sure the server is active and you have network access.")
                #Trigger something on the client..
                #I think nothing needs to be triggered.
            else:
                client.alert("Something went wrong. could not identify.")
                #Trigger something on the client..
            
            
        except urllib2.HTTPError, response:
            pass
        
        if (response.code == 403):
            client.alert("Error: Wrong username and password combination. Try again")
            
            #return "Error: Wrong username and password combination. Try again"
        elif (response.code == 200):
            courseid = response.info().getheader('courseid')
            coursename = response.info().getheader('coursename')
            client.alert("Your course: " + coursename + " has uploaded. Course id: " + courseid )
            #Trigger something on the client..
            #client.sendScript("Ext.getCmp('loginumcloudpwin').close()")
            #client.sendScript("Ext.getCmp('exportustadmobilepwin').close()")
        elif (response.code == 500):
            error = response.info().getheader('error')
            if (error == "Grunt test failed"):
                client.alert("Server Error: Your course did not pass server tests. Your project uploaded but cannot be set as active")
            elif (error == "Exe export failed"):
                client.alert("Server Error: Your course failed to finish exporting on the server. Your project uploaded but cannot be set as active.")
            elif (error == "Exe export failed to start"):
                client.alert("Server Error: Your course failed to export on the server. Please get in touch.")
            elif (error == "Request is not POST"):
                client.alert("eXe error: eXe failed to connect with the server by POST request")
            else:
                client.alert("Error: Cannot connect to the server. Make sure the server is active and you have network access.")
            #Trigger something on the client..
            #I think nothing needs to be triggered.
        else:
            client.alert("Something went wrong. could not identify.")
            #Trigger something on the client..
     

    def b4save(self, client, inputFilename, ext, msg):
        """
        Call this before saving a file to get the right filename.
        Returns a new filename or 'None' when attempt to overide
        'inputFilename' is the filename given by the user
        'ext' is the extension that the filename should have
        'msg' will be shown if the filename already exists
        """
        if not inputFilename.lower().endswith(ext):
            inputFilename += ext
            if Path(inputFilename).exists():
                explanation = _(u'"%s" already exists.\nPlease try again with a different filename') % inputFilename
                msg = u'%s\n%s' % (msg, explanation)
                client.alert(msg)
                raise Exception(msg)
        
        is_tmp_export_path = False
        
        #except if we are actually exporting to the download directory
        if G.application.config.appMode == Config.MODE_WEBAPP and hasattr(self.package, 'export_download_dir'):
            if inputFilename.parent == self.package.export_download_dir:
                is_tmp_export_path = True
        
        if not is_tmp_export_path:
            inputFilename = self.adjust_path_for_user(inputFilename)
            
        return inputFilename

    def adjust_path_for_user(self, path):
        """
        Adjusts the path if running in webapp mode to be for the
        user's directory.  In desktop mode returns path as is.
        """
        if G.application.config.appMode != Config.MODE_WEBAPP:
            return path
        else:
            return EXEBackEndService.get_instance(
                           ).adjust_relative_path_for_user(
                           self.session.webservice_user, path)
    
    def abs_path_to_user_path(self, abs_path):
        if G.application.config.appMode != Config.MODE_WEBAPP:
            return abs_path
        else:
            return EXEBackEndService.get_instance(\
                          ).abs_path_to_user_path(
                          self.session.webservice_user, abs_path)
    
    def handle_ping(self, client, data=None):
        """
        Reply to the client so it knows it still has an active connection
        """
        client.sendScript("eXe.app.pong();");
    
    def handleSavePackage(self, client, filename=None, onDone=None):
        """
        Save the current package
        'filename' is the filename to save the package to
        'onDone' will be evaled after saving instead or redirecting
        to the new location (in cases of package name changes).
        (This is used where the user goes file|open when their 
        package is changed and needs saving)
        """
        filename = Path(filename, 'utf-8')
        saveDir  = filename.dirname()
        if saveDir and not saveDir.isdir():
            client.alert(_(u'Cannot access directory named ') + unicode(saveDir) + _(u'. Please use ASCII names.'))
            return
        oldName = self.package.name
        # If the script is not passing a filename to us,
        # Then use the last filename that the package was loaded from/saved to
        if not filename:
            filename = self.package.filename
            filename = self.abs_path_to_user_path(filename)
            assert filename, 'Somehow save was called without a filename on a package that has no default filename.'
        # Add the extension if its not already there and give message if not saved
        filename = self.b4save(client, filename, '.elp', _(u'SAVE FAILED!'))
        try:
            self.package.save(filename) # This can change the package name
            user_info = ""
            if self.session.webservice_user:
                user_info = "user=%s" % self.session.webservice_user
            
            log.info("User SavePackage %s to %s" % (user_info, str(filename)))
        except Exception, e:
            client.alert(_('SAVE FAILED!\n%s') % str(e))
            raise
        # Tell the user and continue
        if onDone:
            client.alert(_(u'Package saved to: %s') % filename, onDone)
        elif self.package.name != oldName:
            # Redirect the client if the package name has changed
            self.webServer.root.putChild(self.package.name, self)
            log.info('Package saved, redirecting client to /%s' % self.package.name)
            client.alert(_(u'Package saved to: %s') % filename, 'eXe.app.gotoUrl("/%s")' % self.package.name.encode('utf8'), \
                         filter_func=otherSessionPackageClients)
        else:
            client.alert(_(u'Package saved to: %s') % filename, filter_func=otherSessionPackageClients)


    def handleLoadPackage(self, client, filename, filter_func=None):
        """Load the package named 'filename'"""
        filename = self.adjust_path_for_user(filename)
        
        package = self._loadPackage(client, filename, newLoad=True)
        self.session.packageStore.addPackage(package)
        self.webServer.root.bindNewPackage(package, self.session)
        client.sendScript((u'eXe.app.gotoUrl("/%s")' % \
                          package.name).encode('utf8'), filter_func=filter_func)
 
    def handleLoadTutorial(self, client):
        """
        Loads the tutorial file, from the Help menu
        """
        filename = self.config.webDir.joinpath("docs")\
                .joinpath("eXe-tutorial.elp")
        self.handleLoadPackage(client, filename)

    def progressDownload(self, numblocks, blocksize, filesize, client):
        try:
            percent = min((numblocks * blocksize * 100) / filesize, 100)
        except:
            percent = 100
        client.sendScript('Ext.MessageBox.updateProgress(%f, "%d%%", "Downloading...")' % (float(percent) / 100, percent))
        log.info('%3d' % (percent))

    def handleSourcesDownload(self, client):
        """
        Download taxon sources from url and deploy in $HOME/.exe/classification_sources
        """
        url = 'http://forja.cenatic.es/frs/download.php/file/1624/classification_sources.zip'
        client.sendScript('Ext.MessageBox.progress("Sources Download", "Connecting to classification sources repository...")')
        d = threads.deferToThread(urlretrieve, url, None, lambda n, b, f: self.progressDownload(n, b, f, client))

        def successDownload(result):
            filename = result[0]
            if not zipfile.is_zipfile(filename):
                return None

            zipFile = zipfile.ZipFile(filename, "r")
            try:
                zipFile.extractall(G.application.config.configDir)
                client.sendScript('Ext.MessageBox.updateProgress(1, "100%", "Success!")')
            finally:
                Path(filename).remove()

        d.addCallback(successDownload)
        
    def handleReload(self, client):
        self.location_buttons.updateText()
        client.sendScript('eXe.app.gotoUrl()', filter_func=allSessionClients)
 
    def handleRemoveTempDir(self, client, tempdir, rm_top_dir):
        """
        Removes a temporary directory and any contents therein
        (from the bottom up), and yup, that's all!
        
        #
        # swiped from an example on:
        #     http://docs.python.org/lib/os-file-dir.html
        ################################################################
        # Delete everything reachable from the directory named in 'top',
        # assuming there are no symbolic links.
        # CAUTION:  This is dangerous!  For example, if top == '/', it
        # could delete all your disk files.
        """
        top = tempdir
        for root, dirs, files in os.walk(top, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        ##################################################################
        # and finally, go ahead and remove the top-level tempdir itself:
        if (int(rm_top_dir) != 0):
            os.rmdir(tempdir)
      
        
    def get_printdir_relative2web(self, exported_dir):
        """
        related to the following ClearParentTempPrintDirs(), return a
        local URL corresponding to the exported_dir
        """
        rel_name = exported_dir[len(G.application.tempWebDir):]
        if sys.platform[:3] == "win":
            rel_name = rel_name.replace('\\', '/')
        if rel_name.startswith('/'):
            rel_name = rel_name[1:]
        http_relative_pathname = "http://127.0.0.1:" + str(self.config.port) \
                                     + '/' + rel_name
        log.debug('printdir http_relative_pathname=' + http_relative_pathname)
        return http_relative_pathname

    def ClearParentTempPrintDirs(self, client, log_dir_warnings):
        """
        Determine the parent temporary printing directory, and clear them 
        if safe to do so (i.e., if not the config dir itself, for example)
        Makes (if necessary), and clears out (if applicable) the parent 
        temporary directory.
        The calling handleClearAndMakeTempPrintDir() shall then make a 
        specific print-job subdirectory.
        """
        #
        # Create the parent temp print dir as hardcoded under the webdir, as:
        #           http://temp_print_dirs
        # (eventually may want to allow this information to be configured by
        #  the user, stored in globals, etc.)
        web_dirname = G.application.tempWebDir
        under_dirname = os.path.join(web_dirname,"temp_print_dirs")
        clear_tempdir = 0
        dir_warnings = ""

        # but first need to ensure that under_dirname itself is available; 
        # if not, create it:
        if cmp(under_dirname,"") != 0:
            if os.path.exists(under_dirname):
                if (os.path.isdir(under_dirname)):
                    # Yes, this directory already exists.  
                    # pre-clean it, keeping the clutter down:
                    clear_tempdir = 1
                else:
                    dir_warnings = "WARNING: The desired Temporary Print " \
                            + "Directory, \"" + under_dirname \
                            + "\", already exists, but as a file!\n"
                    if log_dir_warnings:
                        log.warn("ClearParentTempPrintDirs(): The desired " \
                                + "Temporary Print Directory, \"%s\", " \
                                + "already exists, but as a file!", \
                                under_dirname)
                    under_dirname = web_dirname
                    # but, we can't just put the tempdirs directly underneath
                    # the webDir, since no server object exists for it.
                    # So, as a quick and dirty solution, go ahead and put 
                    # them in the images folder:
                    under_dirname = os.path.join(under_dirname,"images")

                    dir_warnings += "    RECOMMENDATION: please " \
                            + "remove/rename this file to allow eXe easier "\
                            + "management of its temporary print files.\n"
                    dir_warnings += "     eXe will create the temporary " \
                           + "printing directory directly under \"" \
                           + under_dirname + "\" instead, but this might "\
                           +"leave some files around after eXe terminates..."
                    if log_dir_warnings:
                        log.warn("    RECOMMENDATION: please remove/rename "\
                            + "this file to allow eXe easier management of "\
                            + "its temporary print files.")
                        log.warn("     eXe will create the temporary " \
                            + "printing directory directly under \"%s\" " \
                            + "instead, but this might leave some files " \
                            + "around after eXe terminates...", \
                            under_dirname)
                    # and note that we do NOT want to clear_tempdir 
                    # on the config dir itself!!!!!
            else:
                os.makedirs(under_dirname)
                # and while we could clear_tempdir on it, there's no need to.
        if clear_tempdir : 
            # before making this particular print job's temporary print 
            # directory underneath the now-existing temp_print_dirs, 
            # go ahead and clear out temp_print_dirs such that we have 
            # AT MOST one old temporary set of print job files still existing
            # once eXe terminates:
            rm_topdir = "0"  
            # note: rm_topdir is passed in as a STRING since 
            # handleRemoveTempDir expects as such from nevow's 
            # clientToServerEvent() call:
            self.handleRemoveTempDir(client, under_dirname, rm_topdir)

        return under_dirname, dir_warnings

    def handleClearAndMakeTempPrintDir(self, client, suffix, prefix, \
                                        callback):
        """
        Makes a temporary printing directory, and yup, that's pretty much it!
        """

        # First get the name of the parent temp directory, after making it 
        # (if necessary) and clearing (if applicable):
        log_dir_warnings = 1  
        (under_dirname, dir_warnings) = self.ClearParentTempPrintDirs( \
                                             client, log_dir_warnings)

        # Next, go ahead and create this particular print job's temporary 
        # directory under the parent temp directory:
        temp_dir = mkdtemp(suffix, prefix, under_dirname) 

        # Finally, pass the created temp_dir back to the expecting callback:
        client.call(callback, temp_dir, dir_warnings)

    def handleTinyMCEimageChoice(self, client, tinyMCEwin, tinyMCEwin_name, \
                             tinyMCEfield, local_filename, preview_filename):
        """
        Once an image is selected in the file browser that is spawned by the 
        TinyMCE image dialog, copy this file (which is local to the user's 
        machine) into the server space, under a preview directory 
        (after checking if this exists, and creating it if necessary).
        Note that this IS a "cheat", in violation of the client-server 
        separation, but can be done since we know that the eXe server is 
        actually sitting on the client host.
        """
        server_filename = ""
        callback_errors = ""
        errors = 0

        log.debug('handleTinyMCEimageChoice: image local = ' + local_filename 
                + ', base=' + os.path.basename(local_filename))
        local_filename = self.adjust_path_for_user(
                                             local_filename)

        webDir     = Path(G.application.tempWebDir)
        previewDir  = webDir.joinpath('previews')

        if not previewDir.exists():
            log.debug("image previews directory does not yet exist; " \
                    + "creating as %s " % previewDir)
            previewDir.makedirs()
        elif not previewDir.isdir():
            client.alert( \
                _(u'Preview directory %s is a file, cannot replace it') \
                % previewDir)
            log.error("Couldn't preview tinyMCE-chosen image: "+
                      "Preview dir %s is a file, cannot replace it" \
                      % previewDir)
            callback_errors =  "Preview dir is a file, cannot replace"
            errors += 1

        if errors == 0:
            log.debug('handleTinyMCEimageChoice: originally, local_filename='
                    + local_filename)
            try:
                local_filename = unicode(local_filename, 'utf-8')
            except:
                #string would already be unicode in this case...
                pass
            log.debug('handleTinyMCEimageChoice: in unicode, local_filename='
                    + local_filename)

            localImagePath = Path(local_filename)
            log.debug('handleTinyMCEimageChoice: after Path, localImagePath= '
                    + localImagePath);
            if not localImagePath.exists() or not localImagePath.isfile():
                client.alert( \
                     _(u'Local file %s is not found, cannot preview it') \
                     % localImagePath)
                log.error("Couldn't find tinyMCE-chosen image: %s" \
                        % localImagePath)
                callback_errors = "Image file %s not found, cannot preview" \
                        % localImagePath
                errors += 1

        try:
            # joinpath needs its join arguments to already be in Unicode:
            #preview_filename = toUnicode(preview_filename);
            # but that's okay, cuz preview_filename is now URI safe, right?
            log.debug('URIencoded preview filename=' + preview_filename);
            
            server_filename = previewDir.joinpath(preview_filename);
            log.debug("handleTinyMCEimageChoice copying image from \'"\
                    + local_filename + "\' to \'" \
                    + server_filename.abspath() + "\'.");
            shutil.copyfile(local_filename, \
                    server_filename.abspath());
            shutil.copystat(local_filename, \
                    server_filename.abspath())

            # new optional description file to provide the 
            # actual base filename, such that once it is later processed
            # copied into the resources directory, it can be done with
            # only the basename.   Otherwise the resource filenames
            # are too long for some users, preventing them from making
            # backup CDs of the content, for example.
            # 
            # Remember that the full path of the
            # file is only used here as an easy way to keep the names
            # unique WITHOUT requiring a roundtrip call from the Javascript
            # to this server, and back again, a process which does not
            # seem to work with tinyMCE in the mix.  BUT, once tinyMCE's
            # part is done, and this image processed, it can be returned
            # to just its basename, since the resource parts have their
            # own unique-ification mechanisms already in place.

            descrip_file_path = Path(server_filename+".exe_info")
            log.debug("handleTinyMCEimageChoice creating preview " \
                    + "description file \'" \
                    + descrip_file_path.abspath() + "\'.");
            descrip_file = open(descrip_file_path, 'wb')

            # safety measures against TinyMCE, otherwise it will 
            # later take ampersands and entity-escape them into '&amp;',
            # and filenames with hash signs will not be found, etc.:
            unspaced_filename  = local_filename.replace(' ','_')
            unhashed_filename  = unspaced_filename.replace('#', '_num_')
            unamped_local_filename  = unhashed_filename.replace('&', '_and_')
            log.debug("and setting new file basename as: " 
                    + unamped_local_filename);
            my_basename = os.path.basename(unamped_local_filename)
            
            descrip_file.write((u"basename="+my_basename).encode('utf-8'))
            descrip_file.flush()
            descrip_file.close()

        except Exception, e:
            client.alert(_('SAVE FAILED!\n%s') % str(e))
            log.error("handleTinyMCEimageChoice unable to copy local image "\
                    +"file to server prevew, error = " + str(e))
            raise

    def handleTinyMCEmath(self, client, tinyMCEwin, tinyMCEwin_name, \
                             tinyMCEfield, latex_source, math_fontsize, \
                             preview_image_filename, preview_math_srcfile):
        """
        Based off of handleTinyMCEimageChoice(), 
        handleTinyMCEmath() is similar in that it places a .gif math image 
        (and a corresponding .tex LaTeX source file) into the previews dir.
        Rather than copying the image from a user-selected directory, though,
        this routine actually generates the math image using mimetex.
        """
        server_filename = ""
        callback_errors = ""
        errors = 0

        webDir     = Path(G.application.tempWebDir)
        previewDir  = webDir.joinpath('previews')

        if not previewDir.exists():
            log.debug("image previews directory does not yet exist; " \
                    + "creating as %s " % previewDir)
            previewDir.makedirs()
        elif not previewDir.isdir():
            client.alert( \
                _(u'Preview directory %s is a file, cannot replace it') \
                % previewDir)
            log.error("Couldn't preview tinyMCE-chosen image: "+
                      "Preview dir %s is a file, cannot replace it" \
                      % previewDir)
            callback_errors =  "Preview dir is a file, cannot replace"
            errors += 1

        #if errors == 0:
        #    localImagePath = Path(local_filename)
        #    if not localImagePath.exists() or not localImagePath.isfile():
        #        client.alert( \
        #             _(u'Image file %s is not found, cannot preview it') \
        #             % localImagePath)
        #        log.error("Couldn't find tinyMCE-chosen image: %s" \
        #                % localImagePath)
        #        callback_errors = "Image file %s not found, cannot preview" \
        #                % localImagePath
        #        errors += 1

        # the mimetex usage code was swiped from the Math iDevice:
        if latex_source <> "":

            # first write the latex_source out into the preview_math_srcfile,
            # such that it can then be passed into the compile command:
            math_filename = previewDir.joinpath(preview_math_srcfile)
            math_filename_str = math_filename.abspath().encode('utf-8')
            log.info("handleTinyMCEmath: using LaTeX source: " + latex_source)
            log.debug("writing LaTeX source into \'" \
                    + math_filename_str + "\'.")
            math_file = open(math_filename, 'wb')
            # do we need to append a \n here?:
            math_file.write(latex_source)
            math_file.flush()
            math_file.close()


            try: 
                use_latex_sourcefile = math_filename_str
                tempFileName = compile(use_latex_sourcefile, math_fontsize, \
                        latex_is_file=True)
            except Exception, e:
                client.alert(_('MimeTeX compile failed!\n%s') % str(e))
                log.error("handleTinyMCEmath unable to compile LaTeX using "\
                    +"mimetex, error = " + str(e))
                raise

            # copy the file into previews
            server_filename = previewDir.joinpath(preview_image_filename);
            log.debug("handleTinyMCEmath copying math image from \'"\
                    + tempFileName + "\' to \'" \
                    + server_filename.abspath().encode('utf-8') + "\'.");
            shutil.copyfile(tempFileName, \
                    server_filename.abspath().encode('utf-8'));

            # Delete the temp file made by compile 
            Path(tempFileName).remove()
        return
    
    def getResources(self,dirname,html,client):
        Resources.cancel = False
        self.importresources = Resources(dirname,self.package.findNode(client.currentNodeId),client)
#        import cProfile
#        import lsprofcalltree
#        p = cProfile.Profile()
#        p.runctx( "resources.insertNode()",globals(),locals())
#        k = lsprofcalltree.KCacheGrind(p)
#        data = open('exeprof.kgrind', 'w+')
#        k.output(data)
#        data.close()
        self.importresources.insertNode([html.partition(dirname + os.sep)[2]])
        

    def handleImport(self, client, importType, path, html=None):
        if importType == 'html':
            if (not html):
                client.call('eXe.app.getController("Toolbar").importHtml2', path)
            else:
                d = threads.deferToThread(self.getResources, path, html, client)
                d.addCallback(self.handleImportCallback, client)
                d.addErrback(self.handleImportErrback, client)
                client.call('eXe.app.getController("Toolbar").initImportProgressWindow', _(u'Importing HTML...'))
        if importType.startswith('lom'):
            try:
                setattr(self.package, importType, lomsubs.parse(path))
                client.call('eXe.app.getController("MainTab").lomImportSuccess', importType)
            except Exception, e:
                client.alert(_('LOM Metadata import FAILED!\n%s') % str(e))

    def handleImportErrback(self, failure, client):
        client.alert(_(u'Error importing HTML:\n') + unicode(failure.getBriefTraceback()), \
                     (u'eXe.app.gotoUrl("/%s")' % self.package.name).encode('utf8'), filter_func=otherSessionPackageClients)

    def handleImportCallback(self,resources,client):
        client.call('eXe.app.getController("Toolbar").closeImportProgressWindow')
        client.sendScript((u'eXe.app.gotoUrl("/%s")' % \
                      self.package.name).encode('utf8'), filter_func=allSessionPackageClients)

    def handleCancelImport(self, client):
        log.info('Cancel import')
        Resources.cancelImport()
        
    def setPackageTitle(self, client, new_title):
        """Handle when user clicks on title bar"""
        self.package.set_title(new_title)
        
    def handleRenameNode(self):
        """Handle when user double clicks on page title"""
        pass

        
    def startUSBExport(self, client, exportType, filename):
        """Handle export to a USB disk"""
        if not os.path.exists(filename):
            os.makedirs(filename)
            print("Made directory: " + filename)
        self.handleExport(client, exportType, filename)
        x = 10
        
    def handleExport(self, client, exportType, filename):
        """
        Called by js. 
        Exports the current package to one of the above formats
        'exportType' can be one of 'singlePage' 'webSite' 'zipFile' 
                     'textFile' or 'scorm'            
        'filename' is a file for scorm pages, and a directory for websites
        """ 
        webDir     = Path(self.config.webDir)
        #stylesDir  = webDir.joinpath('style', self.package.style)
        stylesDir  = self.config.stylesDir/self.package.style
        
        if G.application.config.appMode == Config.MODE_WEBAPP:
            if not hasattr(self.package, "export_download_dir"):
                self.package.export_download_dir = None
            
            if not self.package.export_download_dir:
                self.package.export_download_dir = TempDirPath()
            
            filename = self.package.export_download_dir/self.package.name
        else:
            filename = Path(filename, 'utf-8')
        
        exportDir  = Path(filename).dirname()
        if exportDir and not exportDir.exists():
            client.alert(_(u'Cannot access directory named ') +
                         unicode(exportDir) +
                         _(u'. Please use ASCII names.'))
            return

        """ 
        adding the print feature in using the same export functionality:
        """
        if exportType == 'singlePage' or exportType == 'printSinglePage':
            printit = 0
            if exportType == 'printSinglePage':
                printit = 1
            exported_dir = self.exportSinglePage(client, filename, webDir, \
                                                 stylesDir, printit)
            if printit == 1 and not exported_dir is None:
                web_printdir = self.get_printdir_relative2web(exported_dir)
                G.application.config.browser.open(web_printdir)

        elif exportType == 'webSite':
            self.exportWebSite(client, filename, stylesDir)
        elif exportType == 'csvReport':
            self.exportReport(client, filename, stylesDir)
        elif exportType == 'zipFile':
            filename = self.b4save(client, filename, '.zip', _(u'EXPORT FAILED!'))
            self.exportWebZip(client, filename, stylesDir)
            client.sendScript("alert('your export is ready sir');")
        elif exportType == 'textFile':
            self.exportText(client, filename)
        elif exportType == 'scorm1.2':
            filename = self.b4save(client, filename, '.zip', _(u'EXPORT FAILED!'))
            self.exportScorm(client, filename, stylesDir, "scorm1.2")
        elif exportType == "scorm2004":
            filename = self.b4save(client, filename, '.zip', _(u'EXPORT FAILED!'))
            self.exportScorm(client, filename, stylesDir, "scorm2004")
        elif exportType == "agrega":
            filename = self.b4save(client, filename, '.zip', _(u'EXPORT FAILED!'))
            self.exportScorm(client, filename, stylesDir, "agrega")
        elif exportType == 'epub3':
            filename = self.b4save(client, filename, '.epub', _(u'EXPORT FAILED!'))
            self.exportEpub3(client, filename, stylesDir)
        elif exportType == "commoncartridge":
            filename = self.b4save(client, filename, '.zip', _(u'EXPORT FAILED!'))
            self.exportScorm(client, filename, stylesDir, "commoncartridge")
        elif exportType == 'mxml':
            self.exportXML(client, filename, stylesDir)
        else:
            filename = self.b4save(client, filename, '.zip', _(u'EXPORT FAILED!'))
            self.exportIMS(client, filename, stylesDir)

    def handleQuit(self, client):
        """
        Stops the server
        """
        # first, go ahead and clear out any temp job files still in 
        # the temporary print directory:
        log_dir_warnings = 0  
        # don't warn of any issues with the directories at quit, 
        # since already warned at initial directory creation
        (parent_temp_print_dir, dir_warnings) = \
                self.ClearParentTempPrintDirs(client, log_dir_warnings)

        client.close("window.location = \"quit\";")

        if len(self.clientHandleFactory.clientHandles) <= 1:
            self.webServer.monitoring = False
            G.application.config.configParser.set('user', 'lastDir', G.application.config.lastDir)
            try:
                shutil.rmtree(G.application.tempWebDir, True)
                shutil.rmtree(G.application.resourceDir, True)                
            except:
                log.debug('Don\'t delete temp directorys. ')
            
            if G.application.config.appMode != Config.MODE_WEBAPP:
                log.info("Closing because there are no active clients left")
                reactor.callLater(2, reactor.stop)
        else:
            log.debug("Not quiting. %d clients alive." % len(self.clientHandleFactory.clientHandles))

    def handleBrowseURL(self, client, url):
        """visit the specified URL using the system browser
        
        if the URL contains %s, substitute the local webDir
        if the URL contains %t, show a temp file containing NEWS and README """
        if url.find('%t') > -1:
            release_notes = os.path.join(G.application.tempWebDir,
                    'Release_Notes.html')
            f = open(release_notes, 'wt')
            f.write('''<html><head><title>eXe Release Notes</title></head>
                <body><h1>News</h1><pre>\n''')
            try:
                news = open(os.path.join(self.config.webDir, 'NEWS'),
                        'rt').read()
                readme = open(os.path.join(self.config.webDir, 'README'),
                        'rt').read()
                f.write(news)
                f.write('</pre><hr><h1>Read Me</h1><pre>\n')
                f.write(readme)
            except IOError:
                # fail silently if we can't read either of the files
                pass
            f.write('</pre></body></html>')
            f.close()
            url = url.replace('%t', release_notes)
        else:
            url = url.replace('%s', self.config.webDir)
        log.debug(u'browseURL: ' + url)
        if hasattr(os, 'startfile'):
            os.startfile(url)
        else:
            G.application.config.browser.open(url, new=True)

    def handleMergeXliffPackage(self, client, filename, from_source):
        """
        Parse the XLIFF file and import the contents based on
        translation-unit id-s
        """
        from_source = True if from_source == "true" else False
        try:
            importer = XliffImport(self.package, unquote(filename))
            importer.parseAndImport(from_source)
            client.alert(_(u'Correct XLIFF import'), (u'eXe.app.gotoUrl("/%s")' % \
                           self.package.name).encode('utf8'), filter_func=otherSessionPackageClients)
        except Exception,e:
            client.alert(_(u'Error importing XLIFF: %s') % e, (u'eXe.app.gotoUrl("/%s")' % \
                           self.package.name).encode('utf8'), filter_func=otherSessionPackageClients)


    def handleInsertPackage(self, client, filename):
        """
        Load the package and insert in current node
        """
        filename = self.adjust_path_for_user(filename)
        package = self._loadPackage(client, filename, newLoad=True)
        tmpfile = Path(tempfile.mktemp())
        package.save(tmpfile)
        loadedPackage = self._loadPackage(client, tmpfile, newLoad=False,
                                          destinationPackage=self.package)
        newNode = loadedPackage.root.copyToPackage(self.package, 
                                                   self.package.currentNode)
        # trigger a rename of all of the internal nodes and links,
        # and to add any such anchors into the dest package via isMerge:
        newNode.RenamedNodePath(isMerge=True)
        try:
            tmpfile.remove()
        except:
            pass
        client.sendScript((u'eXe.app.gotoUrl("/%s")' % \
                          self.package.name).encode('utf8'), filter_func=allSessionPackageClients)


    def handleExtractPackage(self, client, filename, existOk):
        """
        Create a new package consisting of the current node and export
        'existOk' means the user has been informed of existance and ok'd it
        """
        filename = self.adjust_path_for_user(filename)
        filename  = Path(filename, 'utf-8')
        saveDir = filename.dirname()
        if saveDir and not saveDir.exists():
            client.alert(_(u'Cannot access directory named ') + unicode(saveDir) + _(u'. Please use ASCII names.'))
            return

        # Add the extension if its not already there
        if not filename.lower().endswith('.elp'):
            filename += '.elp'

        if Path(filename).exists() and existOk != 'true':
            msg = _(u'"%s" already exists.\nPlease try again with a different filename') % filename
            client.alert(_(u'EXTRACT FAILED!\n%s') % msg)
            return

        try:
            # Create a new package for the extracted nodes
            newPackage = self.package.extractNode()

            # trigger a rename of all of the internal nodes and links,
            # and to remove any old anchors from the dest package,
            # and remove any zombie links via isExtract:
            newNode = newPackage.root
            if newNode: 
                newNode.RenamedNodePath(isExtract=True)

            # Save the new package
            newPackage.save(filename)
        except Exception, e:
            client.alert(_('EXTRACT FAILED!\n%s') % str(e))
            raise
        client.alert(_(u'Package extracted to: %s') % filename)

    def handleCreateDir(self, client, currentDir, newDir):
        try:
            currentDir = self.adjust_path_for_user(currentDir)
            
            d = Path(currentDir, 'utf-8') / newDir
            d.makedirs()
            client.sendScript(u"""eXe.app.getStore('filepicker.DirectoryTree').load({ 
                callback: function() {
                    eXe.app.fireEvent( "dirchange", %s );
                }
            })""" % json.dumps(d))
        except OSError:
            client.alert(_(u"Directory exists"))
        except:
            log.exception("")

    # Public Methods

    """
    Exports to Ustad Mobile XML
    """
    def exportXML(self, client, filename, stylesDir, preview_mode = False):
        try:
            if not preview_mode:
                filename = self.b4save(client, filename, '.epub', _(u'EXPORT FAILED!'))
            
            xmlExport = XMLExport(self.config, stylesDir, filename)
            
            if not preview_mode: 
                xmlExport.export(self.package)
            else:
                xmlExport.export_to_dir(self.package, filename)
        except Exception, e:
            import traceback
            print traceback.format_exc()
            client.alert(_('EXPORT FAILED!\n%s') % str(e))
            raise
        if client:
            client.alert(_("Exported to\n%s") % filename)

    def exportSinglePage(self, client, filename, webDir, stylesDir, \
                         printFlag):
        """
        Export 'client' to a single web page,
        'webDir' is just read from config.webDir
        'stylesDir' is where to copy the style sheet information from
        'printFlag' indicates whether or not this is for print 
                    (and whatever else that might mean)
        """
        try:
            imagesDir    = webDir.joinpath('images')
            scriptsDir   = webDir.joinpath('scripts')
            cssDir       = webDir.joinpath('css')
            templatesDir = webDir.joinpath('templates')
            # filename is a directory where we will export the website to
            # We assume that the user knows what they are doing
            # and don't check if the directory is already full or not
            # and we just overwrite what's already there
            filename = Path(filename)
            # Append the package name to the folder path if necessary
            if filename.basename() != self.package.name:
                filename /= self.package.name
            if not filename.exists():
                filename.makedirs()
            elif not filename.isdir():
                client.alert(_(u'Filename %s is a file, cannot replace it') % 
                             filename)
                log.error("Couldn't export web page: "+
                          "Filename %s is a file, cannot replace it" % filename)
                return
            else:
                client.alert(_(u'Folder name %s already exists. '
                                'Please choose another one or delete existing one then try again.') % filename)           
                return 
            # Now do the export
            singlePageExport = SinglePageExport(stylesDir, filename, \
                                         imagesDir, scriptsDir, cssDir, templatesDir)
            singlePageExport.export(self.package, printFlag)
        except Exception, e:
            client.alert(_('SAVE FAILED!\n%s') % str(e))
            raise
        # Show the newly exported web site in a new window
        if not printFlag:
            self._startFile(filename)
            if client:
                client.alert(_(u'Exported to %s') % filename)

        # and return a string of the actual directory name, 
        # in case the package name was added, etc.:
        return filename.abspath().encode('utf-8')
        # WARNING: the above only returns the RELATIVE pathname

    def exportWebSite(self, client, filename, stylesDir):
        """
        Export 'client' to a web site,
        'webDir' is just read from config.webDir
        'stylesDir' is where to copy the style sheet information from
        """

        try:
            # filename is a directory where we will export the website to
            # We assume that the user knows what they are doing
            # and don't check if the directory is already full or not
            # and we just overwrite what's already there
            filename = Path(filename)
            # Append the package name to the folder path if necessary
            if filename.basename() != self.package.name:
                filename /= self.package.name
            if not filename.exists():
                filename.makedirs()
            elif not filename.isdir():
                if client:
                    client.alert(_(u'Filename %s is a file, cannot replace it') % 
                             filename)
                log.error("Couldn't export web page: "+
                          "Filename %s is a file, cannot replace it" % filename)
                return
            else:
                if client:
                    client.alert(_(u'Folder name %s already exists. '
                                'Please choose another one or delete existing one then try again.') % filename)           
                return 
            # Now do the export
            websiteExport = WebsiteExport(self.config, stylesDir, filename)
            websiteExport.export(self.package)
        except Exception, e:
            if client:
                client.alert(_('EXPORT FAILED!\n%s') % str(e))
            raise
        if client:
            client.alert(_(u'Exported to %s') % filename)
            # Show the newly exported web site in a new window
            self._startFile(filename)

    def exportWebZip(self, client, filename, stylesDir):
        try:
            log.debug(u"exportWebsite, filename=%s" % filename)
            filename = Path(filename)
            # Do the export
            filename = self.b4save(client, filename, '.zip', _(u'EXPORT FAILED!'))
            websiteExport = WebsiteExport(self.config, stylesDir, filename)
            websiteExport.exportZip(self.package)
        except Exception, e:
            client.alert(_('EXPORT FAILED!\n%s') % str(e))
            raise
        client.alert(_(u'Exported to %s') % filename)
        
    def exportText(self, client, filename):
        try:
            filename = Path(filename)
            log.debug(u"exportWebsite, filename=%s" % filename)
            # Append an extension if required
            if not filename.lower().endswith('.txt'):
                filename += '.txt'
                if Path(filename).exists():
                    msg = _(u'"%s" already exists.\nPlease try again with a different filename') % filename
                    client.alert(_(u'EXPORT FAILED!\n%s') % msg)
                    return
            # Do the export
            textExport = TextExport(filename)
            textExport.export(self.package)
        except Exception, e:
            client.alert(_('EXPORT FAILED!\n%s') % str(e))
            raise
        client.alert(_(u'Exported to %s') % filename)
        
    def handleXliffExport(self, client, filename, source, target, copy, cdata):
        """
        Exports this package to a XLIFF file
        """
        copy = True if copy == "true" else False
        cdata = True if cdata == "true" else False
        try:
            filename = Path(unquote(filename))
            log.debug(u"exportXliff, filename=%s" % filename)
            if not filename.lower().endswith('.xlf'):
                filename += '.xlf'
            xliffExport = XliffExport(self.config, filename, source, target, copy, cdata)
            xliffExport.export(self.package)
        except Exception,e:
            client.alert(_('EXPORT FAILED!\n%s') % str(e))
            raise
        client.alert(_(u'Exported to %s') % filename)


    def exportScorm(self, client, filename, stylesDir, scormType):
        """
        Exports this package to a scorm package file
        """
        try:
            filename = Path(filename)
            log.debug(u"exportScorm, filename=%s" % filename)
            # Append an extension if required
            if not filename.lower().endswith('.zip'):
                filename += '.zip'
                if Path(filename).exists():
                    msg = _(u'"%s" already exists.\nPlease try again with a different filename') % filename
                    client.alert(_(u'EXPORT FAILED!\n%s') % msg)
                    return
            # Do the export
            scormExport = ScormExport(self.config, stylesDir, filename, scormType)
            scormExport.export(self.package)
        except Exception, e:
            client.alert(_('EXPORT FAILED!\n%s') % str(e))
            raise
        client.alert(_(u'Exported to %s') % filename)

    def exportEpub3(self, client, filename, stylesDir):
        try:
            log.debug(u"exportEpub3, filename=%s" % filename)
            filename = Path(filename)
            # Do the export
            filename = self.b4save(client, filename, '.epub', _(u'EXPORT FAILED!'))
            epub3Export = Epub3Export(self.config, stylesDir, filename)
            epub3Export.export(self.package)
            # epub3Export.exportZip(self.package)
        except Exception, e:
            client.alert(_('EXPORT FAILED!\n%s' % str(e)))
            raise
        client.alert(_(u'Exported to %s') % filename)

    def exportReport(self, client, filename, stylesDir):
        """
        Generates this package report to a file
        """
        try:
            log.debug(u"exportReport")
            # Append an extension if required
            if not filename.lower().endswith('.csv'):
                filename += '.csv'
                if Path(filename).exists():
                    msg = _(u'"%s" already exists.\nPlease try again with a different filename') % filename
                    client.alert(_(u'EXPORT FAILED!\n%s' % msg))
                    return
            # Do the export
            websiteExport = WebsiteExport(self.config, stylesDir, filename, report=True)
            websiteExport.export(self.package)
        except Exception, e:
            client.alert(_('EXPORT FAILED!\n%s' % str(e)))
            raise
        client.alert(_(u'Exported to %s' % filename))

    def exportIMS(self, client, filename, stylesDir):
        """
        Exports this package to a ims package file
        """
        try:
            log.debug(u"exportIMS")
            # Append an extension if required
            if not filename.lower().endswith('.zip'):
                filename += '.zip'
                if Path(filename).exists():
                    msg = _(u'"%s" already exists.\nPlease try again with a different filename') % filename
                    client.alert(_(u'EXPORT FAILED!\n%s') % msg)
                    return
            # Do the export
            imsExport = IMSExport(self.config, stylesDir, filename)
            imsExport.export(self.package)
        except Exception, e:
            client.alert(_('EXPORT FAILED!\n%s') % str(e))
            raise
        client.alert(_(u'Exported to %s') % filename)

    # Utility methods
    def _startFile(self, filename):
        """
        Launches an exported web site or page
        """
        if hasattr(os, 'startfile'):
            try:
                os.startfile(filename)
            except UnicodeEncodeError:
                os.startfile(filename.encode(Path.fileSystemEncoding))
        else:
            filename /= 'index.html'
            G.application.config.browser.open('file://'+filename)

    def _loadPackage(self, client, filename, newLoad=True,
                     destinationPackage=None):
        """Load the package named 'filename'"""
        try:
            encoding = sys.getfilesystemencoding()
            if encoding is None:
                encoding = 'utf-8'
            filename2 = toUnicode(filename, encoding)
            log.debug("filename and path" + filename2)
            # see if the file exists AND is readable by the user
            try:
                open(filename2, 'rb').close()
            except IOError:
                filename2 = toUnicode(filename, 'utf-8')
                try:
                    open(filename2, 'rb').close()
                except IOError:
                    client.alert(_(u'File %s does not exist or is not readable.') % filename2)
                    return None
            package = Package.load(filename2, newLoad, destinationPackage)
            if package is None:
                raise Exception(_("Couldn't load file, please email file to bugs@exelearning.org"))
        except Exception, exc:
            if log.getEffectiveLevel() == logging.DEBUG:
                client.alert(_(u'Sorry, wrong file format:\n%s') % unicode(exc))
            else:
                client.alert(_(u'Sorry, wrong file format'))
            log.error(u'Error loading package "%s": %s' % (filename2, unicode(exc)))
            log.error(u'Traceback:\n%s' % traceback.format_exc())
            raise
        return package

    
class CallableInstanceMethod:
    
    def __init__(self, callme, client):
        self.client = client
        self.callme = callme
    
    def __call__(self, *args, **kwargs):
        arg_arr = list(args)
        
        #get rid of javascript context - replace with self
        arg_arr.pop(0)
        
        #most eXe functions have a blank placeholder string
        if len(arg_arr) > 0 and arg_arr[0] == "":
            del arg_arr[0] 
        
        #replace the blank string
        arg_arr.insert(0, self.client)
        
        args2 = tuple(arg_arr)
        return self.callme(*args2, **kwargs)

