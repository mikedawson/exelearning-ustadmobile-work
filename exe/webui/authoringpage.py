# ===========================================================================
# eXe 
# Copyright 2004-2006, University of Auckland
# Copyright 2006-2007 eXe Project, New Zealand Tertiary Education Commission
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
AuthoringPage is responsible for creating the XHTML for the authoring
area of the eXe web user interface.  
"""
import os
import logging
import time
import exceptions
import sys
from twisted.web.resource    import Resource
from exe.webui               import common
from cgi                     import escape
import exe.webui.builtinblocks
from exe.webui.blockfactory  import g_blockFactory
from exe.engine.error        import Error
from exe.webui.renderable    import RenderableResource
from exe.engine.path         import Path
from exe                     import globals as G
import json

log = logging.getLogger(__name__)

# ===========================================================================
class AuthoringPage(RenderableResource):
    """
    AuthoringPage is responsible for creating the XHTML for the authoring
    area of the eXe web user interface.  
    """
    name = u'authoring'

    def __init__(self, parent):
        RenderableResource.__init__(self, parent)
        self.blocks  = []

    def getChild(self, name, request):
        """
        Try and find the child for the name given
        """
        if name == "":
            return self
        else:
            return Resource.getChild(self, name, request)


    def _process(self, request):
        """
        Delegates processing of args to blocks
        """  
        # Still need to call parent (mainpage.py) process
        # because the idevice pane needs to know that new idevices have been
        # added/edited..
        self.parent.process(request)
        for block in self.blocks:
            block.process(request)
        # now that each block and corresponding elements have been processed,
        # it's finally safe to remove any images/etc which made it into 
        # tinyMCE's previews directory, as they have now had their 
        # corresponding resources created:
        webDir     = Path(G.application.tempWebDir) 
        previewDir  = webDir.joinpath('previews')
        for root, dirs, files in os.walk(previewDir, topdown=False): 
            for name in files:
                if sys.platform[:3] == "win":
                    for i in range(3):
                        try:
                            os.remove(os.path.join(root, name))
                            break
                        except exceptions.WindowsError:
                            time.sleep(0.3)
                else:
                    os.remove(os.path.join(root, name))
        topNode = self.package.currentNode
        if "action" in request.args:
            if request.args["action"][0] == u"changeNode":
                topNode = self.package.findNode(request.args["object"][0])
            elif "currentNode" in request.args:
                topNode = self.package.findNode(request.args["currentNode"][0])
        elif "currentNode" in request.args:
            topNode = self.package.findNode(request.args["currentNode"][0])

        log.debug(u"After authoringPage process" + repr(request.args))
        return topNode

    def render_GET(self, request=None):
        """
        Returns an XHTML string for viewing this page
        if 'request' is not passed, will generate psedo/debug html
        """
        log.debug(u"render_GET "+repr(request))

        topNode = self.package.root
        is_ajax = "mode" in request.args and request.args['mode'][0] == "ajax"
        
        if request is not None and is_ajax is not True:
            # Process args
            for key, value in request.args.items():
                request.args[key] = [unicode(value[0], 'utf8')]
            topNode = self._process(request)

        #Update other authoring pages that observes the current package
        if "action" in request.args:
            if request.args['clientHandleId'][0] == "":
                raise(Exception("Not clientHandleId defined"))
            activeClient = None
            for client in self.parent.clientHandleFactory.clientHandles.values():
                if request.args['clientHandleId'][0] != client.handleId:
                    if client.handleId in self.parent.authoringPages:
                        destNode = None
                        if request.args["action"][0] == "move":
                            destNode = request.args["move" + request.args["object"][0]][0]
                        client.call('eXe.app.getController("MainTab").updateAuthoring', request.args["action"][0], \
                            request.args["object"][0], request.args["isChanged"][0], request.args["currentNode"][0], destNode)
                else:
                    activeClient = client

            if request.args["action"][0] == "done":
                if activeClient:
                    return "<body onload='location.replace(\"" + request.path + "?clientHandleId=" + activeClient.handleId + "\")'/>"
                else:
                    log.error("No active client")

        self.blocks = []
        self.__addBlocks(topNode)
        html  = self.__renderHeader()
        html += u'<body onload="onLoadHandler();" class="exe-authoring-page js">\n'
        html += u"""<div id='externalToolbarHolder' 
        style='z-index: 1000; position: fixed; top: 0px; width: 100%; left:0px; border-bottom: 2px solid gray; height: 0px'>"""
        
        #html += u"<div id='externalToolbarWrapper' class='defaultSkin'>&nbsp;</div>\n"
        html += u"</div>"
        
        html += u"<form method=\"post\" "

        if request is None:
            html += u'action="NO_ACTION"'
        else:
            html += u"action=\""+request.path+"#currentBlock\""
        html += u" id=\"contentForm\">"
        html += u'<div id="main">\n'
        html += common.hiddenField(u"action")
        html += common.hiddenField(u"object")
        html += common.hiddenField(u"isChanged", u"0")
        html += common.hiddenField(u"currentNode", unicode(topNode.id))
        html += common.hiddenField(u'clientHandleId', request.args['clientHandleId'][0])
        html += u'<!-- start authoring page -->\n'
        html += u'<div id="nodeDecoration">\n'
        html += u'<h1 id="nodeTitle">\n'
        html += escape(topNode.titleLong)
        html += u'</h1>\n'
        html += u'</div>\n'
        
        html += "<div class='authoring_button_row'>"
        #html += "<input value='%s' class='insert_button' type='button' onclick=\"submitLink('%s', '%s', %d);\"/>" % \
        #        (_("Insert Here"), "addidevice", "authoring", 1)
        
        html += "<input value='%s' class='insert_button' type='button' onclick=\"authoringInsertIdevice();\"/>" % \
                _("Add Content")
        html += "</div>"
        
        for block in self.blocks:
            html += block.render(self.package.style)
            
        
        
        

        html += u'</div>'
        html += '<script type="text/javascript">$exeAuthoring.ready()</script>\n'
        html += common.footer()

        html = html.encode('utf8')
        return html

    render_POST = render_GET


    def __renderHeader(self):
		#TinyMCE lang (user preference)
        myPreferencesPage = self.webServer.preferences
        
        """Generates the header for AuthoringPage"""
        html  = common.docType()
        #################################################################################
        #################################################################################
        
        html += u'<html xmlns="http://www.w3.org/1999/xhtml" lang="'+myPreferencesPage.getSelectedLanguage()+'">\n'
        html += u'<head>\n'
        html += u"<link rel=\"stylesheet\" type=\"text/css\" href=\"/css/exe.css\" />"
        
        # Use the Style's base.css file if it exists
        themePath = Path(G.application.config.stylesDir/self.package.style)
        themeBaseCSS = themePath.joinpath("base.css")
        if themeBaseCSS.exists():
            html += u"<link rel=\"stylesheet\" type=\"text/css\" href=\"/style/%s/base.css\" />" % self.package.style
        else:
            html += u"<link rel=\"stylesheet\" type=\"text/css\" href=\"/style/base.css\" />"
            
        html += u"<link rel=\"stylesheet\" type=\"text/css\" href=\"/css/exe_wikipedia.css\" />"
        html += u"<link rel=\"stylesheet\" type=\"text/css\" href=\"/css/imgAreaSelect/imgareaselect-default.css\" />"
        html += u"<link rel=\"stylesheet\" type=\"text/css\" href=\"/style/%s/content.css\" />" % self.package.style
        html += u"<link rel=\"stylesheet\" type=\"text/css\" href=\"/css/jquery-ui-1.10.4.custom/ui-lightness/jquery-ui-1.10.4.custom.min.css\" />"
        if G.application.config.tinyMCEVersion != "4":
            html += u"<link rel='stylesheet' type='text/css' href='/scripts/tinymce_3.5.7/jscripts/tiny_mce/themes/advanced/skins/default/ui.css' />"
        if G.application.config.assumeMediaPlugins: 
            html += u"<script type=\"text/javascript\">var exe_assume_media_plugins = true;</script>\n"
        #JR: anado una variable con el estilo
        estilo = u'/style/%s/content.css' % self.package.style
        html += common.getJavaScriptStrings()
        html += u"<script type=\"text/javascript\">"
        html += u"var exe_style = '%s';" % estilo
        html += u"var exe_package_name='"+self.package.name+"';"
        html += 'var exe_export_format="'+common.getExportDocType()+'".toLowerCase();'
        html += 'var exe_editor_mode="'+myPreferencesPage.getEditorMode()+'";'
                
        
        #MD Set the correct tinymce version to use
        tinymce_src = None
        
        if G.application.config.tinyMCEVersion == "3":
            tinymce_src = {"wysiwyg_path" : 
                                "/scripts/tinymce_3.5.7/jscripts/tiny_mce/tiny_mce.js",
                           "wysiwyg_settings_path" :
                                "/scripts/tinymce_3.5.7_settings.js"}
        else:
            tinymce_src = {"wysiwyg_path" :
                            "/scripts/tinymce/tinymce.full.min.js",
                           "wysiwyg_settings_path" :
                            "/scripts/tinymce_settings.js"}
        html += 'var eXeLearning_settings = '
        html += json.dumps(tinymce_src) + ";\n"
        
        html += '</script>\n'
        html += u'<script type="text/javascript" src="../jsui/native.history.js"></script>\n'
        html += u'<script type="text/javascript" src="/scripts/authoring.js"></script>\n'
        html += u'<script type="text/javascript" src="/scripts/exe_jquery.js"></script>\n'
        html += u'<script type="text/javascript" src="/scripts/jquery-ui-1.10.4.custom.min.js"></script>\n'
        html += u'<script type="text/javascript" src="/scripts/exe_lightbox.js"></script>\n'
        html += u'<script type="text/javascript" src="/scripts/common.js"></script>\n'
        html += u'<script type="text/javascript" src="/scripts/jquery.imgareaselect.js"></script>\n'
        html += u'<script type="text/javascript" src="/scripts/exe_imgmaparea.js"></script>\n'
        html += u'<script type="text/javascript" src="/scripts/authoring_defaultprompts.js"></script>\n'
        html += u'<script type="text/javascript" src="/scripts/authoring_feedback_checkboxes.js"></script>\n'
        html += '<script type="text/javascript">document.write(unescape("%3Cscript src=\'" + eXeLearning_settings.wysiwyg_path + "\' type=\'text/javascript\'%3E%3C/script%3E"));</script>';
        html += '<script type="text/javascript">document.write(unescape("%3Cscript src=\'" + eXeLearning_settings.wysiwyg_settings_path + "\' type=\'text/javascript\'%3E%3C/script%3E"));</script>';
        html += u'<title>"+_("eXe : elearning XHTML editor")+"</title>\n'
        html += u'<meta http-equiv="content-type" content="text/html; '
        html += u' charset=UTF-8" />\n'
        html += u'</head>\n'
        return html


    def __addBlocks(self, node):
        """
        Add All the blocks for the currently selected node
        """
        for idevice in node.idevices:
            block = g_blockFactory.createBlock(self, idevice)
            if not block:
                log.critical(u"Unable to render iDevice.")
                raise Error(u"Unable to render iDevice.")
            self.blocks.append(block)

# ===========================================================================
