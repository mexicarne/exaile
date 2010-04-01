#!/usr/bin/env python

# Bookmark plugin for Exaile media player
# Copyright (C) 2009 Brian Parma
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.



from __future__ import with_statement
from xl.nls import gettext as _
from xl import event, xdg, trax, settings
from xlgui import commondialogs, guiutil, icons
import gtk
import gobject
import gio
import os
import logging
import bookmarksprefs
logger = logging.getLogger(__name__)


MENU_ITEM                   = None

#TODO: to dict or not to dict.  dict prevents duplicates, list of tuples preserves order (using tuples atm)

def error(text):
    logger.error("%s: %s" % ('Bookmarks', text))
    commondialogs.error(None, exaile.gui.main, text)

class Bookmarks:
    def __init__(self, exaile):
        self.bookmarks = []
#        self.auto_db = {}
        self.exaile = exaile
        self.use_covers = settings.get_option('plugin/bookmarks/use_covers', False)

        # TODO: automatic bookmarks, not yet possible
        #  - needs a way to get the time a file is inturrupted at
        # set events - not functional yet
        #event.add_callback(self.on_start_track, 'playback_start')
        #event.add_callback(self.on_stop_track, 'playback_end')
        #playback_end, playback_pause, playback_resume, stop_track


    def do_bookmark(self, widget, data):
        """
            This is called to resume a bookmark.
        """
        key, pos = data
        exaile = self.exaile

        if not (key and pos):
            return

        # check if it's already playing
        track = exaile.player.current
        if track:
            if track.get_loc_for_io() == key:
                exaile.player.unpause()
                exaile.player.seek(pos)
                return
        else:
            # use currently selected playlist (as opposed to current playlist)
            track = trax.Track(key)
            if track:   # make sure we got one
                pl = exaile.gui.main.get_selected_playlist().playlist
                exaile.queue.set_current_playlist(pl)
                exaile.queue.current_playlist.add(track)

        # try and play/seek
        if track:
#            print 'bk: seeking to ', pos,type(pos)
            idx = exaile.queue.current_playlist.index(track)
            exaile.queue.current_playlist.set_current_pos(idx)
            #exaile.player.stop()   # prevents crossfading
            exaile.queue.play(track)
            exaile.player.unpause()
            exaile.player.seek(pos)


    def add_bookmark(self, widget, menus):
        """
            Create bookmark for current track/position.
        """
        # get currently playing track
        track = self.exaile.player.current
        if track is None:
            error('Need a playing track to Bookmark.')
            return

        pos = self.exaile.player.get_time()
        key = track.get_loc_for_io()
        self.bookmarks.append((key,pos))
        self.display_bookmark(key, pos, menus)
        menus[0].get_children()[1].set_sensitive(True)
        menus[0].get_children()[2].set_sensitive(True)

    def display_bookmark(self, key, pos, menus):
        """
            Create menu entrees for this bookmark.
        """
        pix = None
        # add menu item
        try:
            item = trax.Track(key)
            title = item.get_tag_display('title')
            if self.use_covers:
                image = self.exaile.covers.get_cover(item, set_only=True)
                if image:
                    try:
                        pix = icons.MANAGER.pixbuf_from_data(image, size=(16,16))
                    except gobject.GError:
                        logger.warn('Could not load cover')
                        pix = None
                        # no cover
                else:
                    pix = None
        except:
            import traceback, sys
            traceback.print_exc(file=sys.stdout)
            logger.debug('BM: Cannot open %s' % key)
            # delete offending key?
            return
        time = '%d:%02d' % (pos/60, pos%60)
        label = '%s @ %s' % ( title , time )

        menu_item = gtk.ImageMenuItem(label)
        if pix:
            menu_item.set_image(gtk.image_new_from_pixbuf(pix))
        menu_item.connect('activate', self.do_bookmark, (key,pos))
        menus[0].append_item(menu_item)
        menu_item.show_all()

        menu_item = gtk.ImageMenuItem(label)
        if pix:
            menu_item.set_image(gtk.image_new_from_pixbuf(pix))
        menu_item.connect('activate', self.delete_bookmark, (menus,label,key,pos))
        menus[1].append_item(menu_item)

        # save addition
        self.save_db()

    def clear(self, widget, menus):
        """
            Delete all bookmarks.
        """
        # how to remove widgets?
        for x in menus[0].get_children()[3:]:
            x.destroy()
        for x in menus[1].get_children():
            x.destroy()

        self.bookmarks = []
        self.save_db()
        menus[0].get_children()[1].set_sensitive(False)
        menus[0].get_children()[2].set_sensitive(False)

    def delete_bookmark(self, widget, targets):
        """
            Delete a bookmark.
        """
        #print targets
        menus, label, key, pos = targets

        if (key, pos) in self.bookmarks:
            self.bookmarks.remove((key,pos))

        if menus[0]:
            item = [x for x in menus[0].get_children() if (x.get_name() == 'GtkImageMenuItem') and (unicode(x.get_child().get_text(), 'utf-8') == label)]
            item[0].destroy()

        if menus[1]:
            item = [x for x in menus[1].get_children() if (x.get_name() == 'GtkImageMenuItem') and (unicode(x.get_child().get_text(), 'utf-8') == label)]
            item[0].destroy()

        self.save_db()
        self.set_sensitive_items(menus)

    def load_db(self, menus):
        """
            Load previously saved bookmarks from a file.
        """
        path = os.path.join(xdg.get_data_dirs()[0],'bookmarklist.dat')
        try:
            # Load Bookmark List from file.
            with open(path,'rb') as f:
                line = f.read()
                try:
                    db = eval(line,{'__builtin__':None})
                    self.bookmarks += db
                    for (key,pos) in db:
                        self.display_bookmark(key, pos, menus)
                except Exception, s:
                    logger.error('BM: bad bookmark file: %s'%s)
                    return None

        except IOError, (e,s):  # File might not exist
            logger.error('BM: could not open file: %s'%s)


    def save_db(self):
        """
            Save list of bookmarks to a file.
        """
        # Save List
        path = os.path.join(xdg.get_data_dirs()[0],'bookmarklist.dat')
        with open(path,'wb') as f:
            f.write(str(self.bookmarks))

    def set_sensitive_items(self, menus):
        try:
            foo = menus[0].get_children()[4].get_name() == 'GtkSeparatorMenuItem'
        except IndexError:
            menus[0].get_children()[1].set_sensitive(False)
            menus[0].get_children()[2].set_sensitive(False)


def __enb(eventname, exaile, nothing):
    gobject.idle_add(_enable, exaile)

def enable(exaile):
    """
        Dummy initialization function, calls _enable when exaile is fully loaded.
    """

    if exaile.loading:
        event.add_callback(__enb, 'gui_loaded')
    else:
        __enb(None, exaile, None)

def _enable(exaile):
    """
        Called when plugin is enabled.  Set up the menus, create the bookmark class, and
        load any saved bookmarks.
    """
    global MENU_ITEM
    global SEP

    bm = Bookmarks(exaile)

    MENU_ITEM = gtk.ImageMenuItem(_('Bookmarks'))
    SEP = gtk.SeparatorMenuItem()

    exaile.gui.builder.get_object('tools_menu').append(SEP)
    exaile.gui.builder.get_object('tools_menu').append(MENU_ITEM)

    menus = [guiutil.Menu(), guiutil.Menu()]

    menu_item = gtk.ImageMenuItem(_('Bookmark This Track'))
    menu_item.connect('activate', bm.add_bookmark, menus)
    menu_item.set_image(gtk.image_new_from_icon_name('bookmark-new', gtk.ICON_SIZE_MENU))
    menus[0].append_item(menu_item)

    menu_item = gtk.MenuItem(_('Delete Bookmark'))
    menu_item.set_submenu(menus[1])
    menus[0].append_item(menu_item)

    menus[0].append(_('Clear Bookmarks'), bm.clear, 'gtk-clear', menus)

    menus[0].append_separator()

    bm.load_db(menus)
    bm.set_sensitive_items(menus)

    MENU_ITEM.set_submenu(menus[0])
    MENU_ITEM.set_image(gtk.image_new_from_icon_name('user-bookmarks', gtk.ICON_SIZE_MENU))

    SEP.show_all()
    MENU_ITEM.show_all()


def disable(exaile):
    """
        Called when the plugin is disabled.  Destroy menu.
    """
    global MENU_ITEM
    global SEP

    if MENU_ITEM:
        MENU_ITEM.hide()
        MENU_ITEM.destroy()
        MENU_ITEM = None

    if SEP:
        SEP.hide()
        SEP.destroy()
        SEP = None

if __name__ == '__main__':
    # test dialog outside of exaile
    print get_time()

# vi: et ts=4 sts=4 sw=4
def get_prefs_pane():
    return bookmarksprefs
